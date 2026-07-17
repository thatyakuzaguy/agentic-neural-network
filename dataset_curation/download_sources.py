from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_curation.common import (
    CurationError,
    RAW_SOURCES_DIR,
    SOURCE_MANIFEST,
    add_common_args,
    clean_text,
    ensure_dir,
    read_json,
    resolve_public_path,
    write_json,
)

MAX_HTTP_BYTES = 8 * 1024 * 1024


def _request_json(url: str, token: str | None = None) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "product-agent-dataset-curation/1.0",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read(MAX_HTTP_BYTES + 1).decode("utf-8"))


def _download_github_issues(source: dict[str, Any], raw_dir: Path, limit: int) -> dict[str, Any]:
    repo = source.get("extra", {}).get("repo")
    if not repo:
        raise CurationError(f"Missing repo for {source['source']}")
    url = (
        f"https://api.github.com/repos/{repo}/issues?"
        + urllib.parse.urlencode(
            {
                "state": "all",
                "per_page": min(limit, 100),
                "sort": "updated",
                "direction": "desc",
            }
        )
    )
    payload = _request_json(url, os.environ.get("GITHUB_TOKEN"))
    issues = [
        issue
        for issue in payload[:limit]
        if "pull_request" not in issue and clean_text(issue.get("body"))
    ]
    output_path = raw_dir / f"{source['source']}.json"
    write_json(
        output_path,
        {"source": source, "downloaded_at": datetime.now(UTC).isoformat(), "items": issues},
    )
    return {"source": source["source"], "path": str(output_path), "items": len(issues)}


def _download_huggingface_sample(
    source: dict[str, Any], raw_dir: Path, limit: int
) -> dict[str, Any]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise CurationError("Install the optional 'datasets' package for SWE-bench samples.") from exc
    dataset_id = source.get("extra", {}).get("dataset_id")
    split = source.get("extra", {}).get("split", "train")
    if not dataset_id:
        raise CurationError(f"Missing dataset_id for {source['source']}")
    rows = [dict(row) for row in load_dataset(dataset_id, split=split, streaming=True).take(limit)]
    output_path = raw_dir / f"{source['source']}.json"
    write_json(
        output_path,
        {"source": source, "downloaded_at": datetime.now(UTC).isoformat(), "items": rows},
    )
    return {"source": source["source"], "path": str(output_path), "items": len(rows)}


def _generated_ears_examples(source: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
    examples = [
        {
            "task": "Add RBAC to a FastAPI admin endpoint for invoice exports.",
            "requirements": [
                "When an authenticated admin requests an invoice export, "
                "the API shall verify the user has the billing.export permission.",
                "If the permission is missing, the API shall return 403 without creating an export job.",
                "Where an export job is created, the service shall write an audit log entry "
                "with actor, tenant, filters, and request id.",
            ],
            "acceptance": [
                "A user without billing.export receives 403 and no job row is inserted.",
                "A user with billing.export receives 202 and an export job id.",
                "Audit log records include actor id, tenant id, filters, request id, and timestamp.",
            ],
            "ambiguities": [
                "It is unclear which roles should include billing.export by default.",
                "Retention requirements for generated invoice files are not specified.",
            ],
        },
        {
            "task": "Create a CLI command that validates data pipeline configuration before deployment.",
            "requirements": [
                "When a config file is provided, the CLI shall validate schema, "
                "required secrets references, and destination table names.",
                "If validation fails, the CLI shall exit non-zero and report all detected errors.",
                "While running in CI mode, the CLI shall emit machine-readable JSON output.",
            ],
            "acceptance": [
                "Invalid YAML, missing secrets, and malformed table names are reported together.",
                "CI mode emits JSON with error code, message, and config path for each error.",
                "A valid config exits with code 0 and prints a concise success message.",
            ],
            "ambiguities": [
                "The exact config schema version is not specified.",
                "The required destination naming convention needs confirmation.",
            ],
        },
    ]
    output_path = raw_dir / f"{source['source']}.json"
    write_json(
        output_path,
        {"source": source, "downloaded_at": datetime.now(UTC).isoformat(), "items": examples},
    )
    return {"source": source["source"], "path": str(output_path), "items": len(examples)}


def download_sources(data_root: Path, limit: int, confirm_large: bool) -> list[dict[str, Any]]:
    sources = read_json(resolve_public_path(SOURCE_MANIFEST, data_root), default=[])
    raw_dir = ensure_dir(resolve_public_path(RAW_SOURCES_DIR, data_root))
    results = []
    for source in sources:
        if source.get("license_status") != "clear":
            results.append({"source": source["source"], "skipped": True, "reason": "unclear license"})
            continue
        strategy = source.get("download_strategy")
        sample_limit = min(limit, int(source.get("max_sample_rows") or limit))
        if strategy == "github_issues":
            results.append(_download_github_issues(source, raw_dir, sample_limit))
        elif strategy == "huggingface_sample" and confirm_large:
            results.append(_download_huggingface_sample(source, raw_dir, sample_limit))
        elif strategy == "huggingface_sample":
            results.append(
                {
                    "source": source["source"],
                    "skipped": True,
                    "reason": "requires --confirm-large for external dataset sample",
                }
            )
        elif strategy == "generated_examples":
            results.append(_generated_ears_examples(source, raw_dir))
        else:
            results.append({"source": source["source"], "skipped": True, "reason": "metadata-only"})
    write_json(raw_dir / "download_report.json", results)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Download bounded public-source samples.")
    add_common_args(parser)
    parser.add_argument("--limit", type=int, default=25, help="Maximum rows per source.")
    parser.add_argument("--confirm-large", action="store_true")
    args = parser.parse_args()
    for result in download_sources(args.data_root, args.limit, args.confirm_large):
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

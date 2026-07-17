from __future__ import annotations

import argparse
import hashlib
import re
import sys
import warnings
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_curation.common import (
    GOLD_JSONL,
    SCORED_CANDIDATES,
    add_common_args,
    ensure_dir,
    read_jsonl,
    resolve_public_path,
    write_jsonl,
)

FRONTMATTER_ID = re.compile(r"^candidate_id:\s*([A-Za-z0-9_-]+)\s*$", re.MULTILINE)
FRONTMATTER_BLOCK = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*", re.DOTALL)
HEADING_BLOCK = re.compile(
    r"^## (?P<title>.+?)\s*\n(?P<body>.*?)(?=^## |\Z)",
    re.DOTALL | re.MULTILINE,
)
FENCED_TEXT_BLOCK = re.compile(r"\A```(?:text)?\s*\n(?P<body>.*?)\n```\s*\Z", re.DOTALL)
BODY_FIELD = re.compile(r"^(?P<name>[A-Za-z ]+):\s*(?P<value>.+?)\s*$", re.MULTILINE)


def _markdown_for_candidate(row: dict) -> str:
    flags = ", ".join(row.get("risk_flags") or [])
    return f"""---
candidate_id: {row["candidate_id"]}
source: {row["source"]}
quality_score: {row["quality_score"]}
decision: pending
---

# {row["source"]} / {row["candidate_id"]}

License: {row["license"]}

URL: {row["url"]}

Quality score: {row["quality_score"]}

Risk flags: {flags or "none"}

## Candidate Task

{row["candidate_task"]}

## Candidate Response

```text
{row["candidate_response"]}
```

## Raw Input

```text
{row["raw_input"]}
```

## Raw Output

```text
{row["raw_output"]}
```

## Review Checklist

- License and provenance are acceptable for training use.
- The response only structures information supported by the raw material.
- The task is software-engineering/product-agent relevant.
- Acceptance criteria are concrete enough to train against.
- Ambiguities, assumptions, and risks are useful rather than filler.
"""


def export_markdown_review(data_root: Path, top_n: int) -> list[Path]:
    review_root = resolve_public_path("review", data_root)
    pending_dir = ensure_dir(review_root / "pending")
    ensure_dir(review_root / "approved")
    ensure_dir(review_root / "rejected")
    rows = sorted(
        read_jsonl(resolve_public_path(SCORED_CANDIDATES, data_root)),
        key=lambda row: row.get("quality_score", 0),
        reverse=True,
    )
    exported = []
    for row in rows[:top_n]:
        path = pending_dir / f"{row['quality_score']:03d}_{row['source']}_{row['candidate_id']}.md"
        path.write_text(_markdown_for_candidate(row), encoding="utf-8", newline="\n")
        exported.append(path)
    (review_root / "README.md").write_text(
        "# Product Agent Public Candidate Review\n\n"
        "Move candidate markdown files from `pending/` to `approved/` or `rejected/`.\n"
        "Only files in `approved/` are exported to `product_agent_public_gold_v1.jsonl`.\n",
        encoding="utf-8",
        newline="\n",
    )
    return exported


def _approved_candidate_ids(review_root: Path) -> set[str]:
    ids = set()
    for path in sorted((review_root / "approved").glob("*.md")):
        match = FRONTMATTER_ID.search(path.read_text(encoding="utf-8"))
        if match:
            ids.add(match.group(1))
    return ids


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_BLOCK.search(text)
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _body_fields(text: str) -> dict[str, str]:
    return {
        match.group("name").strip().lower(): match.group("value").strip()
        for match in BODY_FIELD.finditer(text)
    }


def _markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for match in HEADING_BLOCK.finditer(text):
        sections[match.group("title").strip()] = match.group("body").strip()
    return sections


def _unfence_text(text: str) -> str:
    match = FENCED_TEXT_BLOCK.match(text.strip())
    if match:
        return match.group("body").strip()
    return text.strip()


def _risk_flags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(flag).strip() for flag in value if str(flag).strip()]
    text = str(value).strip()
    if not text or text.lower() == "none":
        return []
    return [flag.strip() for flag in text.split(",") if flag.strip()]


def _quality_score(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _normalized_pair_fingerprint(instruction: str, response: str) -> str:
    normalized = "\n".join(
        (
            re.sub(r"\s+", " ", instruction).strip().lower(),
            re.sub(r"\s+", " ", response).strip().lower(),
        )
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _scored_rows_by_id(data_root: Path) -> dict[str, dict]:
    return {
        str(row.get("candidate_id")): row
        for row in read_jsonl(resolve_public_path(SCORED_CANDIDATES, data_root))
        if row.get("candidate_id")
    }


def approved_markdown_to_gold_row(path: Path, scored_by_id: dict[str, dict] | None = None) -> dict | None:
    text = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)
    body_fields = _body_fields(text)
    sections = _markdown_sections(text)
    scored_by_id = scored_by_id or {}

    candidate_id = frontmatter.get("candidate_id", "").strip()
    if not candidate_id:
        warnings.warn(f"Skipping {path}: missing candidate_id frontmatter.", stacklevel=2)
        return None

    candidate_task = sections.get("Candidate Task", "").strip()
    candidate_response = _unfence_text(sections.get("Candidate Response", ""))
    if not candidate_task:
        warnings.warn(f"Skipping {path}: missing Candidate Task.", stacklevel=2)
        return None
    if not candidate_response:
        warnings.warn(f"Skipping {path}: missing Candidate Response.", stacklevel=2)
        return None

    scored = scored_by_id.get(candidate_id, {})
    risk_flags = _risk_flags(frontmatter.get("risk_flags"))
    if not risk_flags:
        risk_flags = _risk_flags(body_fields.get("risk flags"))
    if not risk_flags:
        risk_flags = _risk_flags(scored.get("risk_flags"))

    return {
        "instruction": candidate_task,
        "response": candidate_response,
        "candidate_id": candidate_id,
        "source": frontmatter.get("source") or scored.get("source", ""),
        "quality_score": _quality_score(
            frontmatter.get("quality_score", scored.get("quality_score", 0))
        ),
        "license": frontmatter.get("license")
        or body_fields.get("license")
        or scored.get("license", ""),
        "url": frontmatter.get("url") or body_fields.get("url") or scored.get("url", ""),
        "risk_flags": risk_flags,
    }


def export_approved_gold(data_root: Path) -> list[dict]:
    review_root = resolve_public_path("review", data_root)
    scored_by_id = _scored_rows_by_id(data_root)
    seen_ids: set[str] = set()
    seen_pairs: set[str] = set()
    gold_rows = []
    for path in sorted((review_root / "approved").glob("*.md")):
        row = approved_markdown_to_gold_row(path, scored_by_id)
        if row is None:
            continue
        candidate_id = row["candidate_id"]
        pair_fingerprint = _normalized_pair_fingerprint(row["instruction"], row["response"])
        if candidate_id in seen_ids or pair_fingerprint in seen_pairs:
            continue
        seen_ids.add(candidate_id)
        seen_pairs.add(pair_fingerprint)
        gold_rows.append(row)
    write_jsonl(resolve_public_path(GOLD_JSONL, data_root), gold_rows)
    return gold_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Export candidates for manual review and gold JSONL.")
    add_common_args(parser)
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--gold-only", action="store_true")
    args = parser.parse_args()
    if not args.gold_only:
        exported = export_markdown_review(args.data_root, top_n=args.top_n)
        print(f"Exported {len(exported)} markdown review files.")
    gold_rows = export_approved_gold(args.data_root)
    print(f"Wrote {len(gold_rows)} approved gold candidates.")


if __name__ == "__main__":
    main()

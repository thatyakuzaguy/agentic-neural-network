"""Review raw Product Agent examples and split approved/rejected data."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from agentic_network.agents.reviewer_agent import _has_blocking_static_findings
from agentic_network.pipeline.static_sanity_checker import (
    StaticSanityInput,
    run_static_sanity_checker,
)

DEFAULT_RAW_DIR = Path("training/datasets/product_agent/raw")
DEFAULT_APPROVED_DIR = Path("training/datasets/product_agent/approved")
DEFAULT_REJECTED_DIR = Path("training/datasets/product_agent/rejected")

REQUIRED_SECTIONS = (
    "REQUIREMENTS",
    "AMBIGUITIES",
    "ASSUMPTIONS",
    "ACCEPTANCE CRITERIA",
    "RISKS",
    "CONFIDENCE",
)
SECTION_BULLET_LIMITS = {
    "REQUIREMENTS": 7,
    "AMBIGUITIES": 5,
    "ASSUMPTIONS": 5,
    "ACCEPTANCE CRITERIA": 7,
    "RISKS": 5,
}
CONFIDENCE_VALUES = {"High", "Medium", "Low"}


@dataclass(frozen=True)
class ProductReview:
    """Review result for one Product Agent example."""

    approved: bool
    findings: list[str]
    static_sanity: str


def review_response(instruction: str, response: str) -> ProductReview:
    """Run deterministic checks for Product Agent dataset suitability."""

    findings: list[str] = []
    static_sanity = run_static_sanity_checker(
        StaticSanityInput(task=instruction, architecture=response)
    )
    if _has_blocking_static_findings(static_sanity):
        findings.append("Static sanity checker reported blocking findings.")

    if re.search(r"</?think\b[^>]*>", response, flags=re.IGNORECASE):
        findings.append("Response contains DeepSeek reasoning tags.")

    if "```" in response:
        findings.append("Response contains markdown code fences.")

    sections = _parse_sections(response, findings)
    if sections:
        _review_section_content(sections, findings)

    return ProductReview(
        approved=not findings,
        findings=findings,
        static_sanity=static_sanity,
    )


def review_raw_directory(
    raw_dir: Path,
    approved_dir: Path,
    rejected_dir: Path,
    *,
    limit: int | None = None,
) -> tuple[int, int]:
    """Review raw examples and write approved/rejected JSON files."""

    approved_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(raw_dir.glob("*.json"))
    if limit is not None:
        raw_files = raw_files[:limit]

    approved_count = 0
    rejected_count = 0
    for raw_file in raw_files:
        payload = json.loads(raw_file.read_text(encoding="utf-8"))
        review = review_response(
            str(payload.get("instruction", "")),
            str(payload.get("response", "")),
        )
        reviewed_payload = {
            **payload,
            "review": {
                "approved": review.approved,
                "findings": review.findings,
                "static_sanity": review.static_sanity,
            },
        }
        target_dir = approved_dir if review.approved else rejected_dir
        stale_dir = rejected_dir if review.approved else approved_dir
        (target_dir / raw_file.name).write_text(
            json.dumps(reviewed_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        stale_path = stale_dir / raw_file.name
        if stale_path.exists():
            stale_path.unlink()
        if review.approved:
            approved_count += 1
        else:
            rejected_count += 1
    return approved_count, rejected_count


def _parse_sections(response: str, findings: list[str]) -> dict[str, list[str]]:
    heading_positions: list[tuple[str, int]] = []
    seen: dict[str, int] = {}
    lines = response.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped in REQUIRED_SECTIONS:
            heading_positions.append((stripped, index))
            seen[stripped] = seen.get(stripped, 0) + 1

    missing = [section for section in REQUIRED_SECTIONS if section not in seen]
    repeated = [section for section, count in seen.items() if count > 1]
    observed_order = [section for section, _index in heading_positions]
    if missing:
        findings.append(f"Missing required sections: {', '.join(missing)}.")
    if repeated:
        findings.append(f"Repeated required sections: {', '.join(repeated)}.")
    if observed_order != list(REQUIRED_SECTIONS):
        findings.append("Required sections are not in the exact expected order.")
    if missing or repeated or observed_order != list(REQUIRED_SECTIONS):
        return {}

    sections: dict[str, list[str]] = {}
    for position, (section, start_index) in enumerate(heading_positions):
        end_index = (
            heading_positions[position + 1][1]
            if position + 1 < len(heading_positions)
            else len(lines)
        )
        sections[section] = lines[start_index + 1 : end_index]
    return sections


def _review_section_content(sections: dict[str, list[str]], findings: list[str]) -> None:
    for section, limit in SECTION_BULLET_LIMITS.items():
        lines = [line.strip() for line in sections[section] if line.strip()]
        bullet_count = sum(1 for line in lines if line.startswith("- "))
        if bullet_count == 0:
            findings.append(f"{section} must contain at least one bullet.")
        if bullet_count > limit:
            findings.append(f"{section} exceeds the {limit}-bullet limit.")

    confidence = "\n".join(line.strip() for line in sections["CONFIDENCE"] if line.strip())
    if confidence not in CONFIDENCE_VALUES:
        findings.append("CONFIDENCE must be exactly High, Medium, or Low.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review raw Product Agent dataset examples.")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help="Raw examples directory.")
    parser.add_argument(
        "--approved-dir",
        type=Path,
        default=DEFAULT_APPROVED_DIR,
        help="Approved examples directory.",
    )
    parser.add_argument(
        "--rejected-dir",
        type=Path,
        default=DEFAULT_REJECTED_DIR,
        help="Rejected examples directory.",
    )
    parser.add_argument("--limit", type=int, help="Optional maximum number of raw files to review.")
    return parser.parse_args()


def _reject_c_drive(path: Path) -> None:
    resolved = path.resolve()
    if resolved.drive.upper() == "C:":
        raise ValueError(f"Refusing to write dataset artifacts on C: {resolved}")


def main() -> int:
    args = parse_args()
    _reject_c_drive(args.approved_dir)
    _reject_c_drive(args.rejected_dir)
    approved_count, rejected_count = review_raw_directory(
        args.raw_dir,
        args.approved_dir,
        args.rejected_dir,
        limit=args.limit,
    )
    print(f"Approved: {approved_count}")
    print(f"Rejected: {rejected_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

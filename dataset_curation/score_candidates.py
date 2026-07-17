from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_curation.common import (
    ACCEPTANCE_TERMS,
    AMBIGUITY_TERMS,
    NORMALIZED_CANDIDATES,
    PREFERRED_TERMS,
    PUBLIC_CANDIDATES_JSONL,
    REJECTED_CANDIDATES,
    SCORED_CANDIDATES,
    SOFTWARE_TERMS,
    TARGET_SECTIONS,
    add_common_args,
    candidate_from_dict,
    is_license_clear,
    read_jsonl,
    resolve_public_path,
    text_has_any,
    write_jsonl,
)


def _looks_like_invented_requirements(row) -> bool:
    if "synthetic" in set(row.risk_flags):
        return False
    response = row.candidate_response.lower()
    raw = f"{row.raw_input}\n{row.raw_output}".lower()
    suspicious_phrases = (
        "stakeholders want",
        "the product should also",
        "additionally, build",
        "new dashboard",
    )
    return any(phrase in response and phrase not in raw for phrase in suspicious_phrases)


def _uses_generic_boilerplate(row) -> bool:
    lowered = row.candidate_response.lower()
    generic_phrases = (
        "clarify and implement the software behavior requested",
        "preserve existing public api behavior",
        "the issue text may omit exact acceptance criteria",
        "maintainer intent should be confirmed",
        "behavior described by the issue is reproducible or verifiable",
    )
    return any(phrase in lowered for phrase in generic_phrases)


def score_candidate(row) -> tuple[int, list[str], list[str]]:
    rejection_reasons: list[str] = []
    risk_flags = list(row.risk_flags)
    source_text = f"{row.raw_input}\n{row.raw_output}\n{row.candidate_task}"
    combined = f"{source_text}\n{row.candidate_response}"
    response = row.candidate_response

    if not is_license_clear(row.license):
        rejection_reasons.append("unclear_or_restricted_license")
    if "copyright_reuse_unclear" in risk_flags:
        rejection_reasons.append("copyright_docs_without_reuse_permission")
    if not text_has_any(source_text, SOFTWARE_TERMS):
        rejection_reasons.append("non_software_engineering_content")
    if _looks_like_invented_requirements(row):
        rejection_reasons.append("appears_to_invent_requirements")
    if _uses_generic_boilerplate(row):
        rejection_reasons.append("generic_boilerplate_response")
    if "promotional_or_spam" in risk_flags:
        rejection_reasons.append("promotional_or_spam")

    score = 25
    if text_has_any(combined, PREFERRED_TERMS):
        score += 18
    if text_has_any(response, ACCEPTANCE_TERMS):
        score += 18
    if text_has_any(combined, AMBIGUITY_TERMS):
        score += 14
    if all(section in response for section in TARGET_SECTIONS):
        score += 15
    if len(row.raw_input) >= 120:
        score += 5
    if "manual_content_review" in risk_flags or "github_user_generated_content" in risk_flags:
        score -= 7
    if "derived_summary_requires_review" in risk_flags:
        score -= 5
    if "synthetic" in risk_flags:
        score -= 3
    if "promotional_or_spam" in risk_flags:
        score -= 40

    score = max(0, min(100, score))
    if rejection_reasons:
        risk_flags = list(dict.fromkeys(risk_flags + rejection_reasons))
        score = min(score, 10 if "promotional_or_spam" in rejection_reasons else 39)
    return score, risk_flags, rejection_reasons


def score_candidates(data_root: Path, min_score: int) -> tuple[list[dict], list[dict]]:
    normalized_path = resolve_public_path(NORMALIZED_CANDIDATES, data_root)
    accepted = []
    rejected = []
    seen = set()
    for payload in read_jsonl(normalized_path):
        row = candidate_from_dict(payload)
        score, risk_flags, rejection_reasons = score_candidate(row)
        row.quality_score = score
        row.risk_flags = risk_flags
        serial = asdict(row)
        serial["candidate_id"] = row.stable_id()
        if serial["candidate_id"] in seen:
            rejected.append({**serial, "rejection_reasons": ["duplicate"]})
            continue
        seen.add(serial["candidate_id"])
        if rejection_reasons or score < min_score:
            rejected.append(
                {
                    **serial,
                    "rejection_reasons": rejection_reasons or [f"quality_below_{min_score}"],
                }
            )
        else:
            accepted.append(serial)

    write_jsonl(resolve_public_path(PUBLIC_CANDIDATES_JSONL, data_root), accepted)
    write_jsonl(resolve_public_path(SCORED_CANDIDATES, data_root), accepted)
    write_jsonl(resolve_public_path(REJECTED_CANDIDATES, data_root), rejected)
    return accepted, rejected


def main() -> None:
    parser = argparse.ArgumentParser(description="Score and filter Product Agent public candidates.")
    add_common_args(parser)
    parser.add_argument("--min-score", type=int, default=60)
    args = parser.parse_args()
    accepted, rejected = score_candidates(args.data_root, min_score=args.min_score)
    print(f"Accepted {len(accepted)} candidates; rejected {len(rejected)} candidates.")


if __name__ == "__main__":
    main()

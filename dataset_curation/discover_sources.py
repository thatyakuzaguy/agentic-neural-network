from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_curation.common import (
    SOURCE_MANIFEST,
    SourceDefinition,
    add_common_args,
    resolve_public_path,
    write_json,
)


def built_in_sources() -> list[SourceDefinition]:
    return [
        SourceDefinition(
            source="PROMISE_NFR",
            url="https://github.com/AleksandarMitrevski/se-requirements-classification",
            license="PROMISE public research dataset; reuse permission unclear",
            license_status="unclear",
            source_type="requirements_classification",
            description="Classic functional/non-functional software requirements examples.",
            download_strategy="metadata_only",
            risk_flags=["unclear_license", "research_dataset", "manual_license_review"],
            notes="Candidate only. Do not export until upstream rights are confirmed.",
        ),
        SourceDefinition(
            source="PURE",
            url="https://zenodo.org/records/7118517",
            license="public, rights unclear",
            license_status="unclear",
            source_type="requirements_documents",
            description="Public requirements documents gathered from web sources.",
            download_strategy="metadata_only",
            risk_flags=["unclear_license", "copyright_reuse_unclear", "manual_license_review"],
            notes="Known upstream license/IP uncertainty. Keep blocked unless reviewed.",
        ),
        SourceDefinition(
            source="PURE_REQUIREMENTS_EXTRACTION",
            url="https://arxiv.org/abs/2202.02135",
            license="unknown",
            license_status="unclear",
            source_type="requirements_extraction",
            description="Annotated PURE-derived requirements extraction data.",
            download_strategy="metadata_only",
            risk_flags=["unclear_license", "derived_from_unclear_rights"],
        ),
        SourceDefinition(
            source="REQuestA",
            url="https://arxiv.org/abs/2302.04793",
            license="unknown",
            license_status="unclear",
            source_type="requirements_question_answering",
            description="Requirements Engineering Question-Answering dataset.",
            download_strategy="metadata_only",
            risk_flags=["unclear_license", "manual_license_review"],
            notes="Keep blocked until a permissive dataset license is verified.",
        ),
        SourceDefinition(
            source="SWE-bench_Lite",
            url="https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite",
            license="MIT",
            license_status="clear",
            source_type="software_issues",
            description="Real GitHub issues and patches from popular Python projects.",
            download_strategy="huggingface_sample",
            risk_flags=["github_user_generated_content", "patch_context_not_needed"],
            max_sample_rows=50,
            extra={"dataset_id": "SWE-bench/SWE-bench_Lite", "split": "test"},
        ),
        SourceDefinition(
            source="GitHub_Issues_FastAPI",
            url="https://api.github.com/repos/fastapi/fastapi/issues",
            license="MIT",
            license_status="clear",
            source_type="github_issues",
            description="FastAPI public issues, sampled through GitHub API.",
            download_strategy="github_issues",
            risk_flags=["github_user_generated_content", "manual_content_review"],
            max_sample_rows=40,
            extra={"repo": "fastapi/fastapi"},
        ),
        SourceDefinition(
            source="GitHub_Issues_Django",
            url="https://api.github.com/repos/django/django/issues",
            license="BSD-3-Clause",
            license_status="clear",
            source_type="github_issues",
            description="Django public issues, sampled through GitHub API.",
            download_strategy="github_issues",
            risk_flags=["github_user_generated_content", "manual_content_review"],
            max_sample_rows=40,
            extra={"repo": "django/django"},
        ),
        SourceDefinition(
            source="EARS_STYLE_REQUIREMENTS",
            url="https://alistairmavin.com/ears/",
            license="CC0 original synthetic examples; template reference only",
            license_status="clear",
            source_type="synthetic_requirements_examples",
            description="EARS syntax guidance used only to generate original examples.",
            download_strategy="generated_examples",
            risk_flags=["synthetic", "template_reference_only"],
            max_sample_rows=30,
        ),
    ]


def discover_sources(data_root: Path, include_unclear: bool) -> list[dict]:
    sources = built_in_sources()
    if not include_unclear:
        sources = [source for source in sources if source.license_status == "clear"]
    payload = [asdict(source) for source in sources]
    write_json(resolve_public_path(SOURCE_MANIFEST, data_root), payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover public Product Agent source candidates.")
    add_common_args(parser)
    parser.add_argument(
        "--include-unclear",
        action="store_true",
        help="Keep unclear sources in the manifest as blocked candidates.",
    )
    args = parser.parse_args()
    payload = discover_sources(args.data_root, include_unclear=args.include_unclear)
    print(f"Wrote {len(payload)} source definitions.")


if __name__ == "__main__":
    main()

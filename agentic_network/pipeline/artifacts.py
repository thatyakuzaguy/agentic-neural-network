"""Artifact persistence for pipeline runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


STAGE_FILES = {
    "user": "00_user_request.md",
    "context": "00_context.md",
    "repository_intelligence": "repository_intelligence/project_summary.json",
    "repository_context": "26_repository_context.md",
    "product": "01_product_requirements.md",
    "architect": "02_architecture_plan.md",
    "code": "03_code.md",
    "test": "04_tests.md",
    "security": "05_security.md",
    "code_revised": "03_code_revised.md",
    "test_revised": "04_tests_revised.md",
    "security_revised": "05_security_revised.md",
    "static_sanity": "05a_static_sanity.md",
    "reviewer": "06_review.md",
    "failure_context": "06a_failure_context.md",
    "fixer": "07_fix_plan.md",
    "post_fix_static_sanity": "07a_post_fix_static_sanity.md",
    "final": "08_final_review.md",
    "execution": "11_execution_plan.md",
    "patch_quality": "25_patch_quality.md",
    "patch_approval": "12_patch_approval.md",
    "patch_apply": "13_patch_apply.md",
    "test_runner": "14_test_run.md",
    "self_healing": "21_self_healing.md",
    "autonomous_loop": "27_autonomous_loop.md",
    "merge_readiness": "15_merge_readiness.md",
    "human_approval": "16_human_approval.md",
    "revision": "10_revision_summary.md",
    "knowledge": "10_knowledge_capture.md",
    "handoff": "09_handoff_bundle.md",
}


@dataclass
class RunArtifacts:
    """Manages a single timestamped output folder."""

    root: Path
    task: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    output_files: dict[str, str] = field(default_factory=dict)
    stage_files: dict[str, str] = field(default_factory=lambda: dict(STAGE_FILES))

    @classmethod
    def create(
        cls,
        output_root: Path,
        task: str,
        *,
        architect_output: str | None = None,
        security_output: str | None = None,
        reviewer_output: str | None = None,
        fixer_output: str | None = None,
        final_output: str | None = None,
    ) -> "RunArtifacts":
        artifact = cls(root=output_root, task=task)
        if architect_output:
            artifact.stage_files["architect"] = architect_output
        if security_output:
            artifact.stage_files["security"] = security_output
        if reviewer_output:
            artifact.stage_files["reviewer"] = reviewer_output
        if fixer_output:
            artifact.stage_files["fixer"] = fixer_output
        if final_output:
            artifact.stage_files["final"] = final_output
        artifact.root = output_root / artifact.timestamp
        artifact.root.mkdir(parents=True, exist_ok=True)
        return artifact

    def save_stage(self, stage: str, content: str) -> Path:
        filename = self.stage_files[stage]
        path = self.root / filename
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        self.output_files[stage] = str(path)
        return path

    def save_summary(self, summary: dict[str, Any]) -> Path:
        path = self.root / "summary.json"
        payload = {**summary, "output_files": self.output_files}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.output_files["summary"] = str(path)
        return path

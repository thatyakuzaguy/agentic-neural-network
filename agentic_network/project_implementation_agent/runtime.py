"""Deterministic project implementation kickoff for ANN v8.4.

The agent creates implementation artifacts and patch proposals inside the
selected project's outputs/runs directory. It never executes terminal commands,
installs packages, uses network access, or applies patches.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_network.desktop_app.project_manager import normalize_workspace_path


RUN_ID_FORMAT = "%Y%m%d_%H%M%S"
PROTECTED_PARTS = {
    ".git",
    "adapters",
    "datasets",
    "knowledge",
    "memory",
    "models",
    "training",
    "unsloth_compiled_cache",
}


@dataclass(frozen=True)
class ProjectImplementationResult:
    """Result of an implementation kickoff run."""

    status: str
    project_root: str
    objective: str
    features_planned: list[str]
    features_selected: list[str]
    backlog_items: list[dict[str, Any]]
    patches_generated: list[str]
    artifacts: list[str]
    consensus: dict[str, Any]
    next_action: str
    skill_evidence_used: bool
    skill_evidence_recommendations: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def start_project_implementation(
    project_root: str | Path,
    objective: str,
    max_features: int = 5,
    *,
    skill_evidence_used: bool = False,
    skill_evidence_recommendations: list[str] | None = None,
) -> ProjectImplementationResult:
    """Start a deterministic implementation run inside a scaffolded project."""

    cleaned_objective = objective.strip()
    root = normalize_workspace_path(project_root)
    errors, warnings = _validate_project_root(project_root, root)
    if not cleaned_objective:
        errors.append("objective is required.")
    selected_count = max(1, min(max_features, 10))
    features = _planned_features(cleaned_objective)
    selected = features[:selected_count]
    backlog = _backlog_for(selected)
    status = "BLOCKED" if _blocked(errors) else ("INVALID" if errors else "PLANNED")
    run_dir = _run_dir(root)
    artifacts: list[str] = []
    patches: list[str] = []
    consensus = _consensus(status, selected)
    evidence_recommendations = list(skill_evidence_recommendations or [])
    next_action = "review_generated_patch_set" if status == "PLANNED" else "fix_project_implementation_inputs"

    if status != "BLOCKED":
        run_dir.mkdir(parents=True, exist_ok=True)
        artifacts.extend(_write_implementation_artifacts(run_dir, cleaned_objective, selected, backlog, status))
        patches = _write_patch_set(run_dir, selected)
        artifacts.append(str(run_dir / "46_generated_patch_set.md"))
        artifacts.extend(patches)
        artifacts.extend(_write_consensus_and_action_plan(run_dir, consensus, next_action, patches))

    result = ProjectImplementationResult(
        status=status,
        project_root=str(root),
        objective=cleaned_objective,
        features_planned=features,
        features_selected=selected,
        backlog_items=backlog,
        patches_generated=patches,
        artifacts=artifacts,
        consensus=consensus,
        next_action=next_action,
        skill_evidence_used=skill_evidence_used,
        skill_evidence_recommendations=evidence_recommendations,
        validation_errors=_dedupe(errors),
        validation_warnings=_dedupe(warnings),
    )
    if status != "BLOCKED":
        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        artifacts.append(str(summary_path))
        result = ProjectImplementationResult(**{**result.to_dict(), "artifacts": artifacts})
    return result


def _validate_project_root(raw_root: str | Path, root: Path) -> tuple[list[str], list[str]]:
    raw = str(raw_root).strip()
    errors: list[str] = []
    warnings: list[str] = []
    if not raw:
        return ["project_root is required."], warnings
    if any(part == ".." for part in re.split(r"[\\/]+", raw)):
        errors.append("Path traversal is not allowed.")
    if _is_blocked_system_root(raw, root) and not _allow_temp_targets(root):
        errors.append("C: and /mnt/c project roots are blocked by default.")
    if _has_protected_part(root):
        errors.append("Protected ANN directories cannot be implemented as projects.")
    if not root.exists():
        warnings.append("Project root does not exist yet; kickoff artifacts will not be generated if blocked.")
    elif not root.is_dir():
        errors.append("project_root must be a directory.")
    return errors, warnings


def _planned_features(objective: str) -> list[str]:
    lowered = objective.lower()
    if "crm" in lowered:
        return [
            "Account management",
            "Contact management",
            "Deal pipeline",
            "Activity timeline",
            "Dashboard metrics",
            "Role-aware access",
        ]
    if "ecommerce" in lowered or "shop" in lowered:
        return ["Product catalog", "Cart", "Checkout", "Orders", "Admin inventory"]
    if "game" in lowered or "videojuego" in lowered:
        return ["Game loop", "Input controls", "Scoring", "Pause and restart", "Visual polish"]
    return ["Domain model", "Primary workflow", "Dashboard", "API contract", "Test plan"]


def _backlog_for(features: list[str]) -> list[dict[str, Any]]:
    backlog: list[dict[str, Any]] = []
    for index, feature in enumerate(features, start=1):
        backlog.append(
            {
                "id": f"BL-{index:03d}",
                "title": feature,
                "priority": "P1" if index <= 3 else "P2",
                "acceptance_criteria": [
                    f"{feature} has a typed data model.",
                    f"{feature} exposes a visible UI or API boundary.",
                    f"{feature} has at least one verification path.",
                ],
            }
        )
    return backlog


def _write_implementation_artifacts(
    run_dir: Path,
    objective: str,
    selected: list[str],
    backlog: list[dict[str, Any]],
    status: str,
) -> list[str]:
    plan_json = run_dir / "44_project_implementation_plan.json"
    plan_md = run_dir / "44_project_implementation_plan.md"
    backlog_json = run_dir / "45_feature_backlog.json"
    backlog_md = run_dir / "45_feature_backlog.md"
    plan_payload = {
        "status": status,
        "objective": objective,
        "features_selected": selected,
        "implementation_mode": "patch_proposal_only",
        "safety": {
            "terminal_execution": False,
            "package_installation": False,
            "network": False,
            "patch_apply": False,
        },
    }
    plan_json.write_text(json.dumps(plan_payload, indent=2), encoding="utf-8")
    plan_md.write_text(_plan_markdown(plan_payload), encoding="utf-8")
    backlog_json.write_text(json.dumps({"backlog_items": backlog}, indent=2), encoding="utf-8")
    backlog_md.write_text(_backlog_markdown(backlog), encoding="utf-8")
    return [str(plan_md), str(plan_json), str(backlog_md), str(backlog_json)]


def _write_patch_set(run_dir: Path, selected: list[str]) -> list[str]:
    patches_dir = run_dir / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)
    patch_paths: list[str] = []
    patch_summary = run_dir / "46_generated_patch_set.md"
    summary_lines = ["# Generated Patch Set", "", "These patches are proposals only and are not applied."]
    for index, feature in enumerate(selected, start=1):
        patch_path = patches_dir / f"patch_{index:03d}.diff"
        relative = f"docs/features/{_slug(feature)}.md"
        content = "\n".join(
            [
                f"diff --git a/{relative} b/{relative}",
                "new file mode 100644",
                "index 0000000..1111111",
                "--- /dev/null",
                f"+++ b/{relative}",
                "@@ -0,0 +1,6 @@",
                f"+# {feature}",
                "+",
                "+Status: proposed",
                "+",
                "+This starter feature spec was generated by ANN v8.4.",
                "+Patch is not applied automatically.",
                "",
            ]
        )
        patch_path.write_text(content, encoding="utf-8")
        patch_paths.append(str(patch_path))
        summary_lines.append(f"- {patch_path.name}: proposes `{relative}`")
    patch_summary.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return patch_paths


def _write_consensus_and_action_plan(
    run_dir: Path,
    consensus: dict[str, Any],
    next_action: str,
    patches: list[str],
) -> list[str]:
    consensus_path = run_dir / "38_consensus_decision.json"
    action_path = run_dir / "39_action_plan.json"
    consensus_path.write_text(json.dumps(consensus, indent=2), encoding="utf-8")
    action = {
        "status": "VALID",
        "recommended_next_action": next_action,
        "user_message": "Review generated implementation patches before any apply step.",
        "blocked": False,
        "executable": False,
        "requires_human": True,
        "requires_terminal": False,
        "requires_approval": True,
        "requires_apply": False,
        "planned_steps": [
            {
                "order": 1,
                "description": "Review backlog and generated patches.",
                "subsystem": "Project Implementation Agent",
                "action_type": "review",
            },
            {
                "order": 2,
                "description": "Run Parallel Review before any patch application.",
                "subsystem": "Parallel Review",
                "action_type": "gate",
            },
        ],
        "allowed_actions": ["inspect_artifacts", "inspect_patches", "request_parallel_review"],
        "blocked_actions": ["execute_terminal", "install_packages", "apply_patch", "deploy"],
        "expected_artifacts": patches,
        "responsible_subsystems": ["Project Implementation Agent", "Consensus", "Action Planner"],
    }
    action_path.write_text(json.dumps(action, indent=2), encoding="utf-8")
    return [str(consensus_path), str(action_path)]


def _consensus(status: str, selected: list[str]) -> dict[str, Any]:
    return {
        "status": "PASSED" if status == "PLANNED" else status,
        "consensus_decision": "PROCEED_TO_REVIEW" if status == "PLANNED" else "BLOCKED",
        "confidence": "Medium",
        "summary": "Implementation kickoff produced patch proposals only.",
        "features_reviewed": selected,
        "safety": {
            "terminal_execution": False,
            "package_installation": False,
            "network": False,
            "patch_apply": False,
        },
    }


def _run_dir(root: Path) -> Path:
    run_id = datetime.now(timezone.utc).strftime(RUN_ID_FORMAT)
    return root / "outputs" / "runs" / run_id


def _plan_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Project Implementation Plan",
        "",
        f"Status: {payload['status']}",
        f"Objective: {payload['objective']}",
        "",
        "## Selected Features",
        *[f"- {feature}" for feature in payload["features_selected"]],
        "",
        "Mode: patch proposal only.",
    ]
    return "\n".join(lines) + "\n"


def _backlog_markdown(backlog: list[dict[str, Any]]) -> str:
    lines = ["# Feature Backlog", ""]
    for item in backlog:
        lines.extend([f"## {item['id']} {item['title']}", f"Priority: {item['priority']}", ""])
        lines.extend(f"- {criterion}" for criterion in item["acceptance_criteria"])
        lines.append("")
    return "\n".join(lines)


def _is_blocked_system_root(raw_path: str, normalized: Path) -> bool:
    raw = raw_path.replace("\\", "/").lower()
    if raw.startswith("/mnt/c") or raw.startswith("c:/"):
        return True
    return normalized.anchor.lower().replace("\\", "/").startswith("c:")


def _allow_temp_targets(path: Path) -> bool:
    if os.environ.get("ANN_ALLOW_TEMP_IMPLEMENTATION_TARGETS") != "1":
        return False
    try:
        path.relative_to(Path(os.environ.get("TEMP", "")).resolve())
        return True
    except ValueError:
        return False


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _blocked(errors: list[str]) -> bool:
    return any(
        "blocked" in error.lower()
        or "protected" in error.lower()
        or "traversal" in error.lower()
        for error in errors
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "feature"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result

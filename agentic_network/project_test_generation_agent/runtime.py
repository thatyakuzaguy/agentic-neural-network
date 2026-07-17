"""Safe test generation for generated ANN projects.

The agent proposes test patches only. It never applies patches, executes a
terminal command, installs dependencies, or uses network access.
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


REPO_ROOT = Path(__file__).resolve().parents[2]
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
SAFE_TARGETS = {
    "readme",
    "package_json",
    "pyproject",
    "fastapi_main",
    "schema_sql",
}


@dataclass(frozen=True)
class ProjectTestGenerationResult:
    """Result of generating project test patches."""

    status: str
    project_root: str
    run_dir: str
    test_targets: list[str]
    tests_planned: list[dict[str, Any]]
    test_patch_files: list[str]
    artifacts: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]
    next_action: str
    skill_evidence_used: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_project_tests(
    project_root: str | Path,
    run_dir: str | Path,
    test_targets: list[str] | None = None,
    max_tests: int = 5,
    *,
    skill_evidence_used: bool = False,
) -> ProjectTestGenerationResult:
    """Generate safe test patches for a project that lacks initial tests."""

    root = normalize_workspace_path(project_root)
    errors, warnings = _validate_project_root(project_root, root)
    resolved_run_dir = _resolve_run_dir(root, run_dir, errors)
    selected_targets = _select_targets(root, test_targets, max_tests)
    if max_tests < 1:
        errors.append("max_tests must be at least 1.")

    if errors:
        return ProjectTestGenerationResult(
            status="BLOCKED" if _blocked(errors) else "INVALID",
            project_root=str(root),
            run_dir=str(resolved_run_dir),
            test_targets=selected_targets,
            tests_planned=[],
            test_patch_files=[],
            artifacts=[],
            validation_errors=_dedupe(errors),
            validation_warnings=_dedupe(warnings),
            next_action="fix_project_test_generation_inputs",
            skill_evidence_used=skill_evidence_used,
        )

    resolved_run_dir.mkdir(parents=True, exist_ok=True)
    tests_planned = _tests_for_targets(root, selected_targets)
    if not tests_planned:
        artifacts = _write_artifacts(resolved_run_dir, root, selected_targets, tests_planned, [])
        return ProjectTestGenerationResult(
            status="NO_TARGETS",
            project_root=str(root),
            run_dir=str(resolved_run_dir),
            test_targets=selected_targets,
            tests_planned=[],
            test_patch_files=[],
            artifacts=artifacts,
            validation_errors=[],
            validation_warnings=_dedupe([*warnings, "No safe project test targets were detected."]),
            next_action="add_project_tests_manually",
            skill_evidence_used=skill_evidence_used,
        )

    patches = _write_test_patches(resolved_run_dir, tests_planned)
    artifacts = _write_artifacts(resolved_run_dir, root, selected_targets, tests_planned, patches)
    trivial_errors = _trivial_test_errors(patches)
    status = "INVALID" if trivial_errors else "VALID"
    return ProjectTestGenerationResult(
        status=status,
        project_root=str(root),
        run_dir=str(resolved_run_dir),
        test_targets=selected_targets,
        tests_planned=tests_planned,
        test_patch_files=patches if status == "VALID" else [],
        artifacts=artifacts,
        validation_errors=trivial_errors,
        validation_warnings=_dedupe(warnings),
        next_action="review_and_apply_generated_test_patches" if status == "VALID" else "review_generated_tests",
        skill_evidence_used=skill_evidence_used,
    )


def _validate_project_root(raw_root: str | Path, root: Path) -> tuple[list[str], list[str]]:
    raw = str(raw_root).strip()
    errors: list[str] = []
    warnings: list[str] = []
    if not raw:
        errors.append("project_root is required.")
    if any(part == ".." for part in re.split(r"[\\/]+", raw)):
        errors.append("Path traversal is not allowed.")
    if _is_blocked_system_root(raw, root) and not _allow_temp_targets(root):
        errors.append("C: and /mnt/c project roots are blocked by default.")
    if _has_protected_part(root):
        errors.append("Protected ANN directories cannot be used for test generation.")
    if (root == REPO_ROOT or _is_relative_to(root, REPO_ROOT)) and not _is_allowed_repo_project_root(root):
        errors.append("ANN repository cannot be used as project_root for test generation.")
    if not root.exists():
        errors.append("project_root must exist.")
    elif not root.is_dir():
        errors.append("project_root must be a directory.")
    return errors, warnings


def _resolve_run_dir(root: Path, run_dir: str | Path, errors: list[str]) -> Path:
    raw = str(run_dir).strip()
    if not raw:
        errors.append("run_dir is required.")
        return root / "outputs" / "runs" / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if any(part == ".." for part in re.split(r"[\\/]+", raw)):
        errors.append("Path traversal is not allowed for run_dir.")
        return root / "outputs" / "runs" / "blocked_test_generation"
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not _is_relative_to(resolved, root):
        errors.append("run_dir must stay inside project_root.")
    if _has_protected_part(resolved.relative_to(root)) if _is_relative_to(resolved, root) else False:
        errors.append("run_dir cannot target protected project paths.")
    return resolved


def _select_targets(root: Path, requested: list[str] | None, max_tests: int) -> list[str]:
    detected = _detect_targets(root)
    if requested is not None:
        allowed = {target for target in requested if target in SAFE_TARGETS}
        detected = [target for target in detected if target in allowed]
    return detected[: max(0, max_tests)]


def _detect_targets(root: Path) -> list[str]:
    targets: list[str] = []
    if (root / "README.md").is_file():
        targets.append("readme")
    if (root / "package.json").is_file() or (root / "apps" / "web" / "package.json").is_file():
        targets.append("package_json")
    if (root / "pyproject.toml").is_file():
        targets.append("pyproject")
    if _fastapi_main_is_testable(root / "apps" / "api" / "app" / "main.py"):
        targets.append("fastapi_main")
    if any(root.rglob("*.sql")):
        targets.append("schema_sql")
    return targets


def _fastapi_main_is_testable(path: Path) -> bool:
    if not path.is_file():
        return False
    source = path.read_text(encoding="utf-8", errors="replace")
    return "FastAPI" in source or "APIRouter" in source or re.search(r"\bapp\s*=", source) is not None


def _tests_for_targets(root: Path, targets: list[str]) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    for target in targets:
        if target == "readme":
            tests.append(
                {
                    "name": "readme_documents_project",
                    "relative_path": "tests/python/test_project_contract.py",
                    "target": "README.md",
                    "assertion": "README exists and contains project documentation markers.",
                    "source": _readme_test_source(),
                }
            )
        elif target == "package_json":
            package_path = "apps/web/package.json" if (root / "apps" / "web" / "package.json").is_file() else "package.json"
            tests.append(
                {
                    "name": "package_manifest_has_metadata",
                    "relative_path": "tests/python/test_project_manifest.py",
                    "target": package_path,
                    "assertion": "package manifest exists and declares name/version or privacy metadata.",
                    "source": _package_test_source(package_path),
                }
            )
        elif target == "pyproject":
            tests.append(
                {
                    "name": "pyproject_has_project_metadata",
                    "relative_path": "tests/python/test_python_project_metadata.py",
                    "target": "pyproject.toml",
                    "assertion": "pyproject exists and contains project/tool metadata.",
                    "source": _pyproject_test_source(),
                }
            )
        elif target == "fastapi_main":
            tests.append(
                {
                    "name": "fastapi_main_declares_app",
                    "relative_path": "tests/python/test_api_smoke.py",
                    "target": "apps/api/app/main.py",
                    "assertion": "FastAPI entrypoint file declares an app boundary.",
                    "source": _fastapi_file_test_source(),
                }
            )
        elif target == "schema_sql":
            schema = sorted(root.rglob("*.sql"))[0].relative_to(root).as_posix()
            tests.append(
                {
                    "name": "schema_contains_sql_structure",
                    "relative_path": "tests/python/test_database_schema_contract.py",
                    "target": schema,
                    "assertion": "SQL schema file contains table or migration structure.",
                    "source": _schema_test_source(schema),
                }
            )
    return tests


def _write_test_patches(run_dir: Path, tests_planned: list[dict[str, Any]]) -> list[str]:
    patches_dir = run_dir / "patches"
    patches_dir.mkdir(parents=True, exist_ok=True)
    patches: list[str] = []
    for index, test in enumerate(tests_planned, start=1):
        relative = str(test["relative_path"])
        patch = patches_dir / f"test_patch_{index:03d}.diff"
        patch.write_text(_new_file_patch(relative, str(test["source"])), encoding="utf-8")
        patches.append(str(patch))
    return patches


def _write_artifacts(
    run_dir: Path,
    root: Path,
    targets: list[str],
    tests_planned: list[dict[str, Any]],
    patches: list[str],
) -> list[str]:
    plan_md = run_dir / "67_project_test_generation_plan.md"
    plan_json = run_dir / "67_project_test_generation_plan.json"
    patch_set = run_dir / "68_generated_test_patch_set.md"
    summary = run_dir / "69_project_test_generation_summary.md"
    plan_payload = {
        "project_root": str(root),
        "test_targets": targets,
        "tests_planned": tests_planned,
        "safety": {
            "terminal_execution": False,
            "package_installation": False,
            "network": False,
            "patch_apply": False,
        },
    }
    plan_json.write_text(json.dumps(plan_payload, indent=2), encoding="utf-8")
    plan_md.write_text(_plan_markdown(root, targets, tests_planned), encoding="utf-8")
    patch_set.write_text(_patch_set_markdown(patches), encoding="utf-8")
    summary.write_text(_summary_markdown(tests_planned, patches), encoding="utf-8")
    return [str(plan_md), str(plan_json), str(patch_set), *patches, str(summary)]


def _new_file_patch(relative: str, content: str) -> str:
    lines = [
        f"diff --git a/{relative} b/{relative}",
        "new file mode 100644",
        "index 0000000..1111111",
        "--- /dev/null",
        f"+++ b/{relative}",
        f"@@ -0,0 +1,{len(content.splitlines())} @@",
    ]
    lines.extend(f"+{line}" for line in content.splitlines())
    lines.append("")
    return "\n".join(lines)


def _readme_test_source() -> str:
    return '''"""Generated project contract tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_readme_documents_project_setup() -> None:
    readme = PROJECT_ROOT / "README.md"
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8").lower()
    markers = ("purpose", "generated by ann", "setup", "starter project")
    assert any(marker in text for marker in markers)
'''


def _package_test_source(package_path: str) -> str:
    return f'''"""Generated package manifest contract tests."""

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_package_manifest_declares_project_metadata() -> None:
    manifest_path = PROJECT_ROOT / "{package_path}"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(manifest.get("name"), str) and manifest["name"].strip()
    assert manifest.get("private") is True or isinstance(manifest.get("version"), str)
'''


def _pyproject_test_source() -> str:
    return '''"""Generated Python project metadata contract tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_contains_metadata_or_tooling() -> None:
    pyproject = PROJECT_ROOT / "pyproject.toml"
    assert pyproject.is_file()
    text = pyproject.read_text(encoding="utf-8").lower()
    assert "[project]" in text or "[tool." in text
'''


def _fastapi_file_test_source() -> str:
    return '''"""Generated API entrypoint contract tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_fastapi_entrypoint_declares_app_boundary() -> None:
    main_py = PROJECT_ROOT / "apps" / "api" / "app" / "main.py"
    assert main_py.is_file()
    source = main_py.read_text(encoding="utf-8")
    assert "app" in source
    assert "FastAPI" in source or "APIRouter" in source or "def " in source
'''


def _schema_test_source(schema: str) -> str:
    return f'''"""Generated database schema contract tests."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_database_schema_contains_structure() -> None:
    schema = PROJECT_ROOT / "{schema}"
    assert schema.is_file()
    text = schema.read_text(encoding="utf-8").lower()
    assert "create table" in text or "migration" in text or "schema" in text
'''


def _trivial_test_errors(patches: list[str]) -> list[str]:
    errors: list[str] = []
    trivial_patterns = ("assert True", "assert 1 == 1", 'assert "x"', "assert 'x'")
    for patch in patches:
        text = Path(patch).read_text(encoding="utf-8", errors="replace")
        if any(pattern in text for pattern in trivial_patterns):
            errors.append(f"Generated test patch contains trivial assertion: {patch}")
    return errors


def _plan_markdown(root: Path, targets: list[str], tests: list[dict[str, Any]]) -> str:
    lines = [
        "# Project Test Generation Plan",
        "",
        f"Project root: {root}",
        "",
        "## Targets",
        *[f"- {target}" for target in targets],
        "",
        "## Tests Planned",
        *[f"- {test['name']}: {test['assertion']}" for test in tests],
        "",
        "Mode: patch proposal only. No tests executed.",
    ]
    return "\n".join(lines) + "\n"


def _patch_set_markdown(patches: list[str]) -> str:
    lines = ["# Generated Test Patch Set", "", "These patches are proposals only."]
    lines.extend(f"- {patch}" for patch in patches)
    return "\n".join(lines) + "\n"


def _summary_markdown(tests: list[dict[str, Any]], patches: list[str]) -> str:
    return "\n".join(
        [
            "# Project Test Generation Summary",
            "",
            f"Tests planned: {len(tests)}",
            f"Patch files: {len(patches)}",
            "Next action: review and apply generated test patches with approval.",
            "",
        ]
    )


def _is_blocked_system_root(raw_path: str, normalized: Path) -> bool:
    raw = raw_path.replace("\\", "/").lower()
    if raw.startswith("/mnt/c") or raw.startswith("c:/"):
        return True
    return normalized.anchor.lower().replace("\\", "/").startswith("c:")


def _allow_temp_targets(path: Path) -> bool:
    if os.environ.get("ANN_ALLOW_TEMP_PROJECT_TEST_GENERATION_TARGETS") != "1":
        return False
    temp = os.environ.get("TEMP")
    if not temp:
        return False
    return _is_relative_to(path, Path(temp).resolve())


def _is_allowed_repo_project_root(root: Path) -> bool:
    allowed_roots = [
        REPO_ROOT / "generated-projects",
        REPO_ROOT / "outputs" / "autonomous_capability_projects",
    ]
    return any(root == allowed.resolve() or _is_relative_to(root, allowed.resolve()) for allowed in allowed_roots)


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _blocked(errors: list[str]) -> bool:
    return any(
        "blocked" in error.lower()
        or "protected" in error.lower()
        or "traversal" in error.lower()
        or "ann repository" in error.lower()
        for error in errors
    )


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

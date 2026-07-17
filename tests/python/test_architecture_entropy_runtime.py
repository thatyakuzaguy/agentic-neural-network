import json
from pathlib import Path

from agentic_network.architecture_entropy.runtime import (
    STATUS_ARCHITECTURE_REVIEW_REQUIRED,
    STATUS_ENTROPY_OK,
    STATUS_ENTROPY_WARNING,
    STATUS_REFACTOR_RECOMMENDED,
    evaluate_architecture_entropy,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _patch(path: str, added: list[str]) -> str:
    return "\n".join(
        [
            f"diff --git a/{path} b/{path}",
            f"--- a/{path}",
            f"+++ b/{path}",
            "@@ -1,1 +1,2 @@",
            " def existing():",
            *[f"+{line}" for line in added],
        ]
    )


def test_entropy_ok_without_patch_pressure(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_001"
    run_dir.mkdir(parents=True)

    result = evaluate_architecture_entropy(run_dir, runs_root=run_dir.parent, project_root=tmp_path)

    assert result["status"] == STATUS_ENTROPY_OK
    assert result["entropy_score"] == 0
    assert result["fix_policy"]["no_more_localized_fixes_when_refactor_required"] is False


def test_control_flow_accretion_warns_before_spaghetti(tmp_path: Path) -> None:
    run_dir = tmp_path / "outputs" / "runs" / "run_001"
    _write(
        run_dir / "patches" / "patch_001.diff",
        _patch("app/service.py", ["if a:", "    return 1", "elif b:", "    return 2", "else:", "    return 3"]),
    )

    result = evaluate_architecture_entropy(run_dir, runs_root=run_dir.parent, project_root=tmp_path)

    assert result["status"] in {STATUS_ENTROPY_WARNING, STATUS_REFACTOR_RECOMMENDED}
    assert "control_flow_accretion" in result["signals"]
    assert result["fix_policy"]["prefer_design_refactor_over_if_else_patch"] is True


def test_repeated_hotspot_churn_recommends_refactor(tmp_path: Path) -> None:
    runs_root = tmp_path / "outputs" / "runs"
    for index in range(1, 5):
        old_run = runs_root / f"old_{index:03d}"
        _write(old_run / "patches" / "patch_001.diff", _patch("app/hotspot.py", [f"VALUE_{index} = {index}"]))
        _write(old_run / "summary.json", json.dumps({"output_files": {}}, indent=2))
    current = runs_root / "current"
    _write(
        current / "patches" / "patch_001.diff",
        _patch("app/hotspot.py", ["if edge_case:", "    return handle(edge_case)", "elif other:", "    return handle(other)"]),
    )

    result = evaluate_architecture_entropy(current, runs_root=runs_root, project_root=tmp_path)

    assert result["status"] in {STATUS_REFACTOR_RECOMMENDED, STATUS_ARCHITECTURE_REVIEW_REQUIRED}
    assert "repeated_hotspot_churn" in result["signals"]
    assert result["fix_policy"]["no_more_localized_fixes_when_refactor_required"] is True
    assert result["recommended_next_action"] == "run_architecture_refactor_review"


def test_complex_python_hotspot_requires_architecture_review(tmp_path: Path) -> None:
    source = "\n".join(
        [
            "def process(value):",
            *[
                f"    if value == {index}:\n        return {index}"
                for index in range(14)
            ],
            "    return value",
        ]
    )
    _write(tmp_path / "app" / "complex.py", source)
    run_dir = tmp_path / "outputs" / "runs" / "run_001"
    _write(
        run_dir / "patches" / "patch_001.diff",
        _patch("app/complex.py", ["if new_case:", "    return 99", "elif fallback:", "    return 0"]),
    )

    result = evaluate_architecture_entropy(run_dir, runs_root=run_dir.parent, project_root=tmp_path)

    assert result["status"] == STATUS_ARCHITECTURE_REVIEW_REQUIRED
    assert "complex_function_hotspot" in result["signals"]

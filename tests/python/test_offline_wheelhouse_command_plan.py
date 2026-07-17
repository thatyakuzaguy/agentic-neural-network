from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def test_offline_wheelhouse_command_plan_is_reproducible_and_non_executing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        activation,
        "build_embedded_runtime_package_audit",
        lambda *_args, **_kwargs: {
            "status": "PACKAGE_AUDIT_INCOMPLETE",
            "missing_packages": ["PySide6", "llama_cpp"],
        },
    )
    monkeypatch.setattr(
        activation,
        "validate_wheelhouse_integrity",
        lambda *_args, **_kwargs: {"status": "INCOMPLETE", "missing": ["PySide6.whl"]},
    )

    plan = activation.build_offline_wheelhouse_command_plan(tmp_path)

    assert plan["status"] == "WHEELHOUSE_COMMAND_PLAN_READY"
    assert plan["requirements_file_exists"] is True
    assert plan["missing_runtime_packages"] == ["PySide6", "llama_cpp"]
    assert plan["manual_external_execution_required"] is True
    assert plan["downloads_executed"] is False
    assert plan["installs_executed"] is False
    assert plan["model_load_attempted"] is False
    assert any("pip download" in command for command in plan["commands"])
    assert any("pip wheel" in command and "llama-cpp-python" in command for command in plan["commands"])
    assert any("Get-FileHash" in command for command in plan["commands"])


def test_offline_wheelhouse_command_plan_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        activation,
        "build_offline_wheelhouse_command_plan",
        lambda *_args, **_kwargs: {"status": "WHEELHOUSE_COMMAND_PLAN_READY"},
    )

    artifacts = activation.write_offline_wheelhouse_command_plan_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "356_offline_wheelhouse_command_plan.json",
        "357_offline_wheelhouse_command_plan.md",
    }

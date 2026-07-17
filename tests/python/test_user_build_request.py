from __future__ import annotations

from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation


def _fake_pipeline(*_args, **_kwargs):
    return {
        "status": "FINAL_ENGINEERING_PIPELINE_PASSED",
        "active_models_after": 0,
        "parallel_llm_loads_after": 0,
    }


def test_user_build_request_artifact_only_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path / "outputs")
    monkeypatch.setattr(activation, "run_final_engineering_pipeline", _fake_pipeline)

    result = activation.run_user_build_request("Create a todo API")

    assert result["status"] == "USER_BUILD_REQUEST_READY"
    assert result["mode"] == "artifact_only"
    assert result["routes_to"] == "run_final_engineering_pipeline"
    assert result["direct_source_writes_performed"] is False
    assert result["patch_apply_requires_existing_approval_gates"] is True


def test_user_build_request_validates_project_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path / "outputs")
    monkeypatch.setattr(activation, "run_final_engineering_pipeline", _fake_pipeline)
    project = tmp_path / "project"
    project.mkdir()

    result = activation.run_user_build_request("Fix tests", project_root=project)

    assert result["status"] == "USER_BUILD_REQUEST_READY"
    assert result["mode"] == "project_root_validated"
    assert result["project_root"] == str(project.resolve())


def test_user_build_request_blocks_real_models_without_token(monkeypatch, tmp_path: Path) -> None:
    called = {"pipeline": False}

    def fail_if_called(*_args, **_kwargs):
        called["pipeline"] = True
        return {}

    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path / "outputs")
    monkeypatch.setattr(activation, "run_final_engineering_pipeline", fail_if_called)

    result = activation.run_user_build_request("Build", confirm_real_models=True, approval_token=None)

    assert result["status"] == "USER_BUILD_REQUEST_BLOCKED"
    assert "real_models_require_local_test_token" in result["errors"]
    assert called["pipeline"] is False


def test_user_build_request_blocks_protected_roots(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(activation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(activation, "DEFAULT_ARTIFACT_ROOT", tmp_path / "outputs")
    protected = tmp_path / "models"
    protected.mkdir()

    result = activation.run_user_build_request("Build", project_root=protected)

    assert result["status"] == "USER_BUILD_REQUEST_BLOCKED"
    assert any(error.startswith("protected_project_root_blocked") for error in result["errors"])

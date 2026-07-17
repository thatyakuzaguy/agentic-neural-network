from pathlib import Path

from agentic_network.safety.filesystem_policy import load_filesystem_policy


def _policy(**kwargs):
    return load_filesystem_policy(**kwargs)


def test_mnt_d_and_mnt_e_are_allowed_by_default() -> None:
    policy = _policy()

    assert policy.is_path_allowed("/mnt/d/AgenticEngineeringNetwork/README.md")
    assert policy.is_path_allowed("/mnt/e/scratch/file.txt")


def test_c_paths_are_blocked_by_default() -> None:
    policy = _policy()

    assert policy.is_path_blocked("/mnt/c/Users/example/file.txt")
    assert policy.is_path_blocked(r"C:\Users\example\file.txt")
    assert "forbidden_c_path_present" in policy.validate_read_path("/mnt/c/Users/example/file.txt")
    assert "forbidden_c_path_present" in policy.validate_read_path(r"C:\Users\example\file.txt")


def test_project_root_is_allowed_by_default() -> None:
    policy = _policy()

    assert policy.is_path_allowed("/mnt/d/AgenticEngineeringNetwork")


def test_protected_paths_are_blocked_for_write() -> None:
    policy = _policy()

    assert "protected_path_modified:outputs/run.md" in policy.validate_write_path(
        "/mnt/d/AgenticEngineeringNetwork/outputs/run.md"
    )
    assert "protected_path_modified:training/datasets/data.jsonl" in policy.validate_write_path(
        "/mnt/d/AgenticEngineeringNetwork/training/datasets/data.jsonl"
    )
    assert "protected_path_modified:/mnt/d/Models/model.gguf" in policy.validate_write_path(
        "/mnt/d/Models/model.gguf"
    )


def test_path_traversal_is_rejected() -> None:
    policy = _policy()

    errors = policy.validate_write_path("/mnt/d/AgenticEngineeringNetwork/../other/file.py")

    assert any(error.startswith("path_traversal_present:") for error in errors)


def test_external_paths_require_policy_enablement() -> None:
    policy = _policy(allowed_roots=("/mnt/d/AgenticEngineeringNetwork",))

    assert not policy.is_path_allowed("/tmp/ann/file.txt")
    assert "path_outside_allowed_roots:/tmp/ann/file.txt" in policy.validate_read_path(
        "/tmp/ann/file.txt"
    )


def test_external_paths_can_be_enabled_without_extra_approval() -> None:
    policy = _policy(
        allowed_roots=("/mnt/d/AgenticEngineeringNetwork",),
        allow_external_paths=True,
        require_explicit_external_path_approval=False,
    )

    assert policy.is_path_allowed("/tmp/ann/file.txt")


def test_external_paths_can_require_explicit_approval() -> None:
    policy = _policy(
        allowed_roots=("/mnt/d/AgenticEngineeringNetwork",),
        allow_external_paths=True,
        require_explicit_external_path_approval=True,
    )
    approved = _policy(
        allowed_roots=("/mnt/d/AgenticEngineeringNetwork",),
        allow_external_paths=True,
        require_explicit_external_path_approval=True,
        external_path_approved=True,
    )

    assert "external_path_approval_required:/tmp/ann/file.txt" in policy.validate_read_path(
        "/tmp/ann/file.txt"
    )
    assert approved.is_path_allowed("/tmp/ann/file.txt")


def test_patch_target_validation() -> None:
    policy = _policy()

    assert policy.validate_patch_target(
        "/mnt/d/AgenticEngineeringNetwork/agentic_network/example.py"
    ) == []
    assert "forbidden_c_path_present" in policy.validate_patch_target("/mnt/c/tmp/file.py")
    assert "protected_path_modified:.git/config" in policy.validate_patch_target(
        "/mnt/d/AgenticEngineeringNetwork/.git/config"
    )


def test_env_configuration(monkeypatch) -> None:
    monkeypatch.setenv("ANN_PROJECT_ROOT", "/mnt/e/custom/project")
    monkeypatch.setenv("ANN_ALLOWED_ROOTS", "/mnt/e")
    monkeypatch.setenv("ANN_BLOCKED_ROOTS", "/mnt/d/blocked")
    monkeypatch.setenv("ANN_PROTECTED_PATHS", ".git,private")
    monkeypatch.setenv("ANN_ALLOW_EXTERNAL_PATHS", "true")
    monkeypatch.setenv("ANN_REQUIRE_EXTERNAL_PATH_APPROVAL", "false")

    policy = load_filesystem_policy()

    assert policy.project_root == Path("/mnt/e/custom/project")
    assert policy.is_path_allowed("/tmp/external.txt")
    assert policy.is_path_blocked("/mnt/d/blocked/file.txt")
    assert "protected_path_modified:private/config.txt" in policy.validate_write_path(
        "/mnt/e/custom/project/private/config.txt"
    )

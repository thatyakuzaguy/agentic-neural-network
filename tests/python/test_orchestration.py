from pathlib import Path

from agentic_engineering_network.logs.audit import AuditLogger
from agentic_engineering_network.orchestration.engine import AgenticEngineeringNetwork
from agentic_engineering_network.security.approvals import ApprovalCenter
from agentic_engineering_network.shared.config import Settings


def test_network_submit_creates_tasks_agents_and_approvals() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\orchestration")
    scratch.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    run = network.submit("Build me a SaaS CRM")

    assert len(run.tasks) == 15
    assert len(run.agent_results) == 15
    assert len(run.proposed_files) >= 25
    proposed_paths = {file.path for file in run.proposed_files}
    assert any(path.endswith(r"apps\api\app\main.py") for path in proposed_paths)
    assert any(path.endswith(r"apps\web\src\app\page.tsx") for path in proposed_paths)
    assert any(path.endswith(r"docker-compose.yml") for path in proposed_paths)
    assert any(path.endswith(r"database\schema.sql") for path in proposed_paths)
    assert len(approvals.list()) >= 5
    assert run.security_review["passed"] is True


def test_network_submit_uses_custom_workspace_directory() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\custom-workspace")
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    workspace = r"D:\AgenticEngineeringNetwork\tests\.tmp\exact-project-root"
    run = network.submit("Build me an ecommerce platform", workspace_directory=workspace)

    assert run.workspace_directory == workspace
    assert all(file.path.startswith(workspace) for file in run.proposed_files)


def test_network_submit_routes_game_prompts_to_game_artifacts() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\game-orchestration")
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    run = network.submit("Build me a fully functional 3d pong game with score and an ai player")

    page = next(file.content for file in run.proposed_files if file.path.endswith(r"apps\web\src\app\page.tsx"))
    assert "3D PONG ARENA" in page
    assert "requestAnimationFrame" in page
    assert "Generated SaaS App" not in page
    assert "New deal" not in page


def test_network_submit_uses_external_d_drive_workspace() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\external-workspace")
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        generated_projects_path=scratch / "generated-projects",
        workspace_drive_mount=Path(r"D:\AENHostDriveMount"),
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    run = network.submit("Build me a social app", workspace_directory=r"D:\TesT")

    assert run.workspace_directory == r"D:\TesT"
    assert all(file.path.startswith(r"D:\TesT") for file in run.proposed_files)


def test_network_rejects_windows_drive_path_outside_app_root() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\outside-drive-workspace")
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    try:
        network.submit("Build me a CRM", workspace_directory=r"C:\Temp\aen-outside")
    except ValueError as exc:
        assert "Workspace must be on" in str(exc)
    else:
        raise AssertionError("Expected Windows drive path outside root to be rejected")

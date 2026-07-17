from pathlib import Path
import json
import os
from threading import Event
import time
from uuid import uuid4

from agentic_engineering_network.logs.audit import AuditLogger
from agentic_engineering_network.orchestration.engine import AgenticEngineeringNetwork
from agentic_engineering_network.security.approvals import ApprovalCenter
from agentic_engineering_network.shared.config import Settings

from app.core.run_store import RunStore


def test_run_store_lists_runs_by_created_at_not_file_mtime() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-order") / uuid4().hex
    run_state_path = scratch / "runs"
    run_state_path.mkdir(parents=True)
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=run_state_path,
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    old_path = run_state_path / "old.json"
    new_path = run_state_path / "new.json"
    base = {
        "idea": "test ordering",
        "workspace_directory": str(scratch / "project"),
        "approval_mode": "full",
        "status": "completed",
        "updated_at": "2026-07-16T12:00:00+00:00",
    }
    old_path.write_text(
        json.dumps({**base, "run_id": "old", "created_at": "2026-06-01T12:00:00+00:00"}),
        encoding="utf-8",
    )
    new_path.write_text(
        json.dumps({**base, "run_id": "new", "created_at": "2026-07-16T12:00:00+00:00"}),
        encoding="utf-8",
    )
    now = time.time()
    os.utime(old_path, (now, now))
    os.utime(new_path, (now - 86400, now - 86400))

    store = RunStore(settings, network)

    assert [run["run_id"] for run in store.list(limit=2)] == ["new", "old"]


def test_run_store_recovers_legacy_creation_order_from_audit_log() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-audit-order") / uuid4().hex
    run_state_path = scratch / "runs"
    run_state_path.mkdir(parents=True)
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=run_state_path,
        generated_projects_path=scratch / "generated-projects",
    )
    base = {
        "idea": "legacy run",
        "workspace_directory": str(scratch / "project"),
        "approval_mode": "full",
        "status": "completed",
    }
    (run_state_path / "old.json").write_text(json.dumps({**base, "run_id": "old"}), encoding="utf-8")
    (run_state_path / "new.json").write_text(json.dumps({**base, "run_id": "new"}), encoding="utf-8")
    settings.audit_log_path.write_text(
        "\n".join(
            [
                json.dumps({"created_at": "2026-06-01T10:00:00+00:00", "metadata": {"run_id": "old"}}),
                json.dumps({"created_at": "2026-07-16T10:00:00+00:00", "metadata": {"run_id": "new"}}),
            ]
        ),
        encoding="utf-8",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    store = RunStore(settings, network)

    assert [run["run_id"] for run in store.list(limit=2)] == ["new", "old"]


def test_run_store_blocks_orphaned_waiting_run_on_load() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-orphaned-waiting") / uuid4().hex
    run_state_path = scratch / "runs"
    run_state_path.mkdir(parents=True)
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=run_state_path,
        generated_projects_path=scratch / "generated-projects",
    )
    result = {
        "status": "waiting_for_approval",
        "pending_approvals": 12,
        "tasks": [
            {"task_id": "qa_verification", "status": "pending"},
            {"task_id": "code_review", "status": "pending"},
        ],
        "agent_results": [],
    }
    (run_state_path / "orphaned.json").write_text(
        json.dumps(
            {
                "run_id": "orphaned",
                "idea": "legacy run",
                "workspace_directory": str(scratch / "project"),
                "approval_mode": "supervised",
                "status": "waiting_for_approval",
                "result": result,
            }
        ),
        encoding="utf-8",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    loaded = RunStore(settings, network).get("orphaned")

    assert loaded is not None
    assert loaded["status"] == "blocked"
    assert loaded["pending_approvals"] == 0
    assert loaded["error"] == "Approval state is no longer available; start a new run."
    statuses = {task["task_id"]: task["status"] for task in loaded["tasks"]}
    assert statuses["qa_verification"] == "blocked"
    assert statuses["code_review"] == "blocked"


def test_run_store_blocks_interrupted_running_run_on_load() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-interrupted") / uuid4().hex
    run_state_path = scratch / "runs"
    run_state_path.mkdir(parents=True)
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=run_state_path,
        generated_projects_path=scratch / "generated-projects",
    )
    (run_state_path / "interrupted.json").write_text(
        json.dumps(
            {
                "run_id": "interrupted",
                "idea": "interrupted run",
                "workspace_directory": str(scratch / "project"),
                "approval_mode": "full",
                "status": "running",
                "result": {
                    "status": "running",
                    "pending_approvals": 0,
                    "tasks": [{"task_id": "qa_verification", "status": "running"}],
                    "agent_results": [],
                },
            }
        ),
        encoding="utf-8",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    loaded = RunStore(settings, network).get("interrupted")

    assert loaded is not None
    assert loaded["status"] == "blocked"
    assert loaded["pending_approvals"] == 0
    assert "previous backend shutdown" in loaded["error"]
    assert loaded["tasks"][0]["status"] == "blocked"


def test_run_store_returns_running_then_completed() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store")
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=scratch / "runs",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)
    store = RunStore(settings, network)

    started = store.start("Build me a SaaS CRM", r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-project", "full")

    assert started["status"] == "running"
    assert started["agent_results"] == []

    deadline = time.time() + 5
    latest = started
    while time.time() < deadline:
        latest = store.get(str(started["run_id"])) or latest
        if latest["status"] == "completed":
            break
        time.sleep(0.05)

    assert latest["status"] == "completed"
    assert len(latest["agent_results"]) == 15


def test_run_store_supervised_waits_then_continues_after_approvals() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-supervised")
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=scratch / "runs",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)
    store = RunStore(settings, network)

    started = store.start(
        "Build me a supervised SaaS CRM",
        r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-supervised-project",
        "supervised",
    )

    deadline = time.time() + 5
    latest = started
    while time.time() < deadline:
        latest = store.get(str(started["run_id"])) or latest
        if latest["status"] == "waiting_for_approval":
            break
        time.sleep(0.05)

    assert latest["status"] == "waiting_for_approval"
    assert latest["pending_approvals"] >= 5

    for approval in approvals.list():
        if approval.payload.get("run_id") == started["run_id"]:
            resolved = approvals.resolve(approval.approval_id, approved=True)
            store.handle_approval_resolution(resolved)

    deadline = time.time() + 5
    while time.time() < deadline:
        latest = store.get(str(started["run_id"])) or latest
        if latest["status"] == "completed":
            break
        time.sleep(0.05)

    assert latest["status"] == "completed"
    assert latest["pending_approvals"] == 0


def test_run_store_full_mode_auto_approves_run_gates() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-full")
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=scratch / "runs",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)
    applied: list[str] = []
    store = RunStore(settings, network, lambda item: applied.append(item.approval_id))

    started = store.start(
        "Build me an auto-approved SaaS CRM",
        r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-full-project",
        "full",
    )

    deadline = time.time() + 5
    latest = started
    while time.time() < deadline:
        latest = store.get(str(started["run_id"])) or latest
        if latest["status"] == "completed":
            break
        time.sleep(0.05)

    run_approvals = [approval for approval in approvals.list() if approval.payload.get("run_id") == started["run_id"]]
    assert latest["status"] == "completed"
    assert latest["pending_approvals"] == 0
    assert run_approvals
    assert all(str(approval.status) == "approved" for approval in run_approvals)
    assert len(applied) == len(run_approvals)


def test_run_store_marks_planner_complete_and_qa_failed_after_lifecycle_failure() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-task-status") / uuid4().hex
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=scratch / "runs",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    def failing_lifecycle(run_id, idea, approvals):  # noqa: ANN001, ARG001
        return {
            "status": "failed",
            "steps": [{"name": "docker_compose_config", "status": "failed", "detail": "compose failed"}],
        }

    store = RunStore(settings, network, lifecycle_runner=failing_lifecycle)
    started = store.start(
        "Build a task API",
        str(scratch / "project"),
        "full",
    )

    deadline = time.time() + 5
    latest = started
    while time.time() < deadline:
        latest = store.get(str(started["run_id"])) or latest
        if latest["status"] == "failed":
            break
        time.sleep(0.05)

    statuses = {task["task_id"]: task["status"] for task in latest["tasks"]}
    assert statuses["implementation_plan"] == "complete"
    assert statuses["qa_verification"] == "failed"
    assert statuses["code_review"] == "blocked"

    reloaded = RunStore(settings, network, lifecycle_runner=failing_lifecycle)
    loaded = reloaded.get(str(started["run_id"]))
    assert loaded is not None
    loaded_statuses = {task["task_id"]: task["status"] for task in loaded["tasks"]}
    assert loaded_statuses["implementation_plan"] == "complete"
    assert loaded_statuses["qa_verification"] == "failed"


def test_run_store_marks_qa_running_while_lifecycle_is_executing() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-qa-running") / uuid4().hex
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=scratch / "runs",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)
    lifecycle_started = Event()
    release_lifecycle = Event()

    def waiting_lifecycle(run_id, idea, approvals):  # noqa: ANN001, ARG001
        lifecycle_started.set()
        assert release_lifecycle.wait(timeout=5)
        return {"status": "passed", "steps": []}

    store = RunStore(settings, network, lifecycle_runner=waiting_lifecycle)
    started = store.start("Build a task API", str(scratch / "project"), "full")

    assert lifecycle_started.wait(timeout=5)
    during = store.get(str(started["run_id"]))
    assert during is not None
    statuses = {task["task_id"]: task["status"] for task in during["tasks"]}
    assert during["status"] == "running"
    assert statuses["qa_verification"] == "running"
    assert statuses["code_review"] == "pending"

    release_lifecycle.set()
    deadline = time.time() + 5
    while time.time() < deadline:
        finished = store.get(str(started["run_id"]))
        if finished and finished["status"] == "completed":
            break
        time.sleep(0.05)
    assert finished is not None
    assert finished["status"] == "completed"


def test_run_store_marks_legacy_docker_cli_failure_as_blocked_for_rerun() -> None:
    result = {
        "tasks": [
            {"task_id": "implementation_plan", "status": "pending"},
            {"task_id": "qa_verification", "status": "pending"},
            {"task_id": "code_review", "status": "pending"},
            {"task_id": "meta_review", "status": "pending"},
            {"task_id": "release_package", "status": "pending"},
        ],
        "agent_results": [
            {"agent": "Planner Agent", "outputs": ["plan.json"]},
            {"agent": "Code Review Agent", "outputs": ["review.md"]},
            {"agent": "Meta Review Agent", "outputs": ["meta_review.json"]},
            {"agent": "Release Agent", "outputs": ["release_notes.md"]},
        ],
        "execution_results": {
            "status": "failed",
            "steps": [
                {
                    "name": "failure_summary",
                    "status": "failed",
                    "detail": "summary only",
                    "command": None,
                },
                {
                    "name": "docker_compose_config",
                    "status": "failed",
                    "detail": "unknown flag: --quiet",
                    "command": ["docker", "compose", "config", "--quiet"],
                }
            ],
        },
    }

    RunStore._sync_task_statuses(result, lifecycle_status="failed")  # noqa: SLF001

    statuses = {task["task_id"]: task["status"] for task in result["tasks"]}
    assert statuses["implementation_plan"] == "complete"
    assert statuses["qa_verification"] == "blocked"
    assert statuses["code_review"] == "blocked"
    assert statuses["meta_review"] == "blocked"
    assert statuses["release_package"] == "blocked"


def test_run_store_marks_docker_registry_timeout_as_blocked() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-infra-blocked") / uuid4().hex
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=scratch / "runs",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)

    def blocked_lifecycle(run_id, idea, approvals):  # noqa: ANN001, ARG001
        return {
            "status": "blocked",
            "steps": [
                {
                    "name": "docker_compose_build",
                    "status": "failed",
                    "detail": (
                        'failed to resolve reference "docker.io/library/python:3.12-slim": '
                        "failed to do request: Head https://registry-1.docker.io/v2/library/python/manifests/3.12-slim: "
                        "net/http: TLS handshake timeout"
                    ),
                }
            ],
        }

    store = RunStore(settings, network, lifecycle_runner=blocked_lifecycle)
    started = store.start("Build a task API", str(scratch / "project"), "full")

    deadline = time.time() + 5
    latest = started
    while time.time() < deadline:
        latest = store.get(str(started["run_id"])) or latest
        if latest["status"] == "blocked":
            break
        time.sleep(0.05)

    statuses = {task["task_id"]: task["status"] for task in latest["tasks"]}
    assert latest["status"] == "blocked"
    assert latest["error"] == "Generated project lifecycle blocked by local infrastructure."
    assert statuses["qa_verification"] == "blocked"
    assert statuses["code_review"] == "blocked"


def test_run_store_marks_docker_daemon_unavailable_as_blocked() -> None:
    result = {
        "tasks": [
            {"task_id": "implementation_plan", "status": "pending"},
            {"task_id": "qa_verification", "status": "pending"},
            {"task_id": "code_review", "status": "pending"},
            {"task_id": "meta_review", "status": "pending"},
            {"task_id": "release_package", "status": "pending"},
        ],
        "agent_results": [{"agent": "Planner Agent", "outputs": ["plan.json"]}],
        "execution_results": {
            "status": "failed",
            "steps": [
                {
                    "name": "docker_compose_down",
                    "status": "failed",
                    "detail": (
                        "failed to connect to the docker API at npipe:////./pipe/docker_engine; "
                        "check if the path is correct and if the daemon is running: "
                        "El sistema no puede encontrar el archivo especificado."
                    ),
                    "command": ["docker-compose", "down", "--volumes"],
                }
            ],
        },
    }

    RunStore._sync_task_statuses(result, lifecycle_status="failed")  # noqa: SLF001

    statuses = {task["task_id"]: task["status"] for task in result["tasks"]}
    assert statuses["implementation_plan"] == "complete"
    assert statuses["qa_verification"] == "blocked"
    assert statuses["code_review"] == "blocked"
    assert statuses["meta_review"] == "blocked"
    assert statuses["release_package"] == "blocked"


def test_run_store_lists_persisted_runs_with_limit() -> None:
    scratch = Path(r"D:\AgenticEngineeringNetwork\tests\.tmp\run-store-list") / uuid4().hex
    settings = Settings(
        ai_provider="deterministic",
        audit_log_path=scratch / "audit.jsonl",
        agent_log_path=scratch / "agents.jsonl",
        run_state_path=scratch / "runs",
        generated_projects_path=scratch / "generated-projects",
    )
    audit = AuditLogger(settings.audit_log_path)
    approvals = ApprovalCenter(audit)
    network = AgenticEngineeringNetwork(settings, audit, approvals)
    store = RunStore(settings, network)

    first = store.start("Build first listed app", str(scratch / "project-a"), "full")
    second = store.start("Build second listed app", str(scratch / "project-b"), "full")

    listed = store.list(limit=1)

    assert len(listed) == 1
    assert listed[0]["run_id"] in {first["run_id"], second["run_id"]}

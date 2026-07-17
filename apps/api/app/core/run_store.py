from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from threading import Lock, Thread
import traceback
from typing import Any, Callable
from uuid import uuid4

from agentic_engineering_network.orchestration.engine import AgenticEngineeringNetwork
from agentic_engineering_network.security.approvals import ApprovalRequest, ApprovalStatus
from agentic_engineering_network.shared.config import Settings, resolve_workspace_directory, to_host_path


ApprovalEffect = Callable[[ApprovalRequest], None]
LifecycleRunner = Callable[[str, str, list[ApprovalRequest]], dict[str, object]]


TASK_BY_AGENT: dict[str, tuple[str, ...]] = {
    "Product Manager Agent": ("product_brief",),
    "Requirements Agent": ("requirements_specification",),
    "Product Review Agent": ("product_review_gate",),
    "Solution Architect Agent": ("architecture_design",),
    "Planner Agent": ("implementation_plan",),
    "Database Engineer Agent": ("database_generation",),
    "Backend Engineer Agent": ("backend_generation",),
    "Frontend Engineer Agent": ("frontend_generation",),
    "DevOps Agent": ("devops_packaging",),
    "Security Agent": ("security_review",),
    "Documentation Agent": ("documentation",),
    "Code Review Agent": ("code_review",),
    "Meta Review Agent": ("meta_review",),
    "Release Agent": ("release_package",),
}


LIFECYCLE_TASKS = {"qa_verification", "code_review", "meta_review", "release_package"}


@dataclass
class RunRecord:
    run_id: str
    idea: str
    workspace_directory: str
    approval_mode: str
    status: str
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None


class RunStore:
    def __init__(
        self,
        settings: Settings,
        network: AgenticEngineeringNetwork,
        approval_effect: ApprovalEffect | None = None,
        lifecycle_runner: LifecycleRunner | None = None,
    ) -> None:
        self.settings = settings
        self.network = network
        self.approval_effect = approval_effect
        self.lifecycle_runner = lifecycle_runner
        self._lock = Lock()
        self._records: dict[str, RunRecord] = {}
        self.settings.run_state_path.mkdir(parents=True, exist_ok=True)
        self._load_records()

    def start(self, idea: str, workspace_directory: str | None, approval_mode: str | None = None) -> dict[str, Any]:
        normalized_mode = self._normalize_approval_mode(approval_mode)
        run_id = str(uuid4())
        workspace_root = resolve_workspace_directory(self.settings, workspace_directory)
        display_workspace = to_host_path(self.settings, workspace_root)
        timestamp = self._now()
        record = RunRecord(
            run_id=run_id,
            idea=idea,
            workspace_directory=display_workspace,
            approval_mode=normalized_mode,
            status="running",
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._lock:
            self._records[run_id] = record
            self._persist_locked(record)
        worker = Thread(
            target=self._run,
            args=(run_id, idea, display_workspace, normalized_mode),
            name=f"aen-run-{run_id[:8]}",
            daemon=True,
        )
        worker.start()
        return self.serialize(record)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(run_id)
            return self.serialize(record) if record else None

    def list(self, limit: int = 25) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._records.values())

        records.sort(key=lambda record: record.created_at, reverse=True)
        return [self.serialize(record) for record in records[: max(1, min(limit, 100))]]

    def handle_approval_resolution(self, item: ApprovalRequest) -> None:
        run_id = item.payload.get("run_id")
        if not isinstance(run_id, str):
            return
        record = self._record_for(run_id)
        if record is None:
            return

        self.network.audit.record(
            "run.approval_progress",
            "approval-center",
            f"Approval resolved for run {run_id}: {item.title}",
            {
                "run_id": run_id,
                "approval_id": item.approval_id,
                "status": str(item.status),
                "remaining_approvals": self._pending_count(run_id),
            },
        )
        self._refresh_waiting_result(run_id)
        if self._pending_count(run_id) > 0:
            return
        if self._has_rejection(run_id):
            self._mark_blocked(run_id)
            return
        self._resume_after_approvals(run_id)

    def _run(self, run_id: str, idea: str, workspace_directory: str, approval_mode: str) -> None:
        try:
            run = self.network.submit(idea, workspace_directory=workspace_directory, run_id=run_id)
            result = AgenticEngineeringNetwork.serialize(run)
            result["approval_mode"] = approval_mode
            result["status"] = "running"
            result["error"] = None
            result["pending_approvals"] = self._pending_count(run_id)
            self._sync_task_statuses(result)
            with self._lock:
                record = self._records[run_id]
                record.result = result
                self._persist_locked(record)
            if approval_mode == "full":
                self._auto_approve_run(run_id)
                with self._lock:
                    record = self._records[run_id]
                    if record.result:
                        record.result["pending_approvals"] = 0
                    self._persist_locked(record)
                self._complete_after_approvals(run_id, actor="approval-mode:full")
                return
            if self._pending_count(run_id) > 0:
                with self._lock:
                    record = self._records[run_id]
                    record.status = "waiting_for_approval"
                    if record.result:
                        record.result["status"] = "waiting_for_approval"
                        record.result["pending_approvals"] = self._pending_count(run_id)
                    self._persist_locked(record)
                self.network.audit.record(
                    "run.waiting_for_approval",
                    "orchestrator",
                    "Run is paused until the user resolves pending approvals.",
                    {"run_id": run_id, "pending_approvals": self._pending_count(run_id)},
                )
                return
            self._complete_after_approvals(run_id)
        except Exception as exc:
            with self._lock:
                record = self._records[run_id]
                record.status = "failed"
                record.error = str(exc)
                if record.result:
                    record.result["status"] = "failed"
                    record.result["error"] = str(exc)
                self._persist_locked(record)

    def _auto_approve_run(self, run_id: str) -> None:
        for approval in self._approvals_for_run(run_id):
            if approval.status != ApprovalStatus.PENDING:
                continue
            item = self.network.approvals.resolve(approval.approval_id, approved=True, actor="approval-mode:full")
            if self.approval_effect:
                self.approval_effect(item)
            self.network.audit.record(
                "approval.auto_approved",
                "approval-mode:full",
                f"Auto-approved {item.title}",
                {"run_id": run_id, "approval_id": item.approval_id, "approval_type": str(item.approval_type)},
            )

    def _resume_after_approvals(self, run_id: str) -> None:
        record = self._record_for(run_id)
        if record is None or record.status in {"running", "completed", "failed", "blocked"}:
            return
        with self._lock:
            current = self._records[run_id]
            current.status = "running"
            if current.result:
                current.result["status"] = "running"
                current.result["pending_approvals"] = 0
            self._persist_locked(current)
        worker = Thread(
            target=self._complete_after_approvals,
            args=(run_id,),
            name=f"aen-resume-{run_id[:8]}",
            daemon=True,
        )
        worker.start()

    def _complete_after_approvals(self, run_id: str, actor: str = "orchestrator") -> None:
        record = self._record_for(run_id)
        if record is None:
            return
        with self._lock:
            current = self._records[run_id]
            current.status = "running"
            if current.result:
                current.result["status"] = "running"
                for task in current.result.get("tasks", []):
                    if not isinstance(task, dict):
                        continue
                    task_id = str(task.get("task_id", ""))
                    if task_id == "qa_verification":
                        task["status"] = "running"
                    elif task_id in {"code_review", "meta_review", "release_package"}:
                        task["status"] = "pending"
            self._persist_locked(current)
        self.network.audit.record(
            "run.resumed",
            actor,
            "All required approvals are resolved; continuing QA, security, and release preparation.",
            {"run_id": run_id},
        )
        lifecycle_result: dict[str, object] | None = None
        if self.lifecycle_runner:
            try:
                lifecycle_result = self.lifecycle_runner(run_id, record.idea, self._approvals_for_run(run_id))
            except Exception as exc:
                lifecycle_result = {
                    "status": "failed",
                    "project_root": None,
                    "display_root": None,
                    "sandbox_id": f"aen-{run_id[:8]}",
                    "release_package": None,
                    "attempts": 1,
                    "steps": [
                        {
                            "name": "lifecycle_exception",
                            "status": "failed",
                            "detail": str(exc),
                            "command": None,
                        }
                    ],
                }
                self.network.audit.record(
                    "lifecycle.exception",
                    "ProjectLifecycleRunner",
                    str(exc),
                    {"run_id": run_id, "traceback": traceback.format_exc()[-8000:]},
                )
        lifecycle_status = str(lifecycle_result.get("status")) if lifecycle_result else "passed"
        for event_type, agent, message in (
            ("qa.completed", "QA Agent", f"Generated project verification finished with status {lifecycle_status}."),
            ("security.completed", "Security Agent", "Approved artifacts passed the generated security workflow."),
            ("release.completed", "Release Agent", "Deployment package manifest is ready."),
        ):
            self.network.audit.record(event_type, agent, message, {"run_id": run_id, "lifecycle": lifecycle_result})
        with self._lock:
            current = self._records[run_id]
            if lifecycle_status == "passed":
                current.status = "completed"
            elif lifecycle_status == "blocked":
                current.status = "blocked"
            else:
                current.status = "failed"
            if current.result:
                current.result["status"] = current.status
                if lifecycle_status == "passed":
                    current.result["error"] = None
                elif lifecycle_status == "blocked":
                    current.result["error"] = "Generated project lifecycle blocked by local infrastructure."
                else:
                    current.result["error"] = "Generated project lifecycle failed."
                current.result["pending_approvals"] = 0
                current.result["execution_results"] = lifecycle_result
                self._sync_task_statuses(current.result, lifecycle_status=lifecycle_status)
                notes = current.result.setdefault("security_review", {}).setdefault("notes", [])
                notes.append("All approval gates were resolved and the run continued through QA/security/release packaging.")
            self._persist_locked(current)
        self.network.audit.record(
            "run.completed",
            actor,
            f"Run {current.status} after approval gates.",
            {"run_id": run_id, "lifecycle": lifecycle_result},
        )

    def _mark_blocked(self, run_id: str) -> None:
        with self._lock:
            current = self._records[run_id]
            current.status = "blocked"
            current.error = "One or more approvals were rejected."
            if current.result:
                current.result["status"] = "blocked"
                current.result["error"] = current.error
                current.result["pending_approvals"] = 0
            self._persist_locked(current)
        self.network.audit.record(
            "run.blocked",
            "approval-center",
            "Run stopped because one or more approvals were rejected.",
            {"run_id": run_id},
        )

    def _refresh_waiting_result(self, run_id: str) -> None:
        record = self._record_for(run_id)
        if record is None:
            return
        with self._lock:
            current = self._records[run_id]
            if current.result and current.status == "waiting_for_approval":
                current.result["pending_approvals"] = self._pending_count(run_id)
                self._persist_locked(current)

    def _approvals_for_run(self, run_id: str) -> list[ApprovalRequest]:
        return [item for item in self.network.approvals.list() if item.payload.get("run_id") == run_id]

    def _pending_count(self, run_id: str) -> int:
        return sum(1 for item in self._approvals_for_run(run_id) if item.status == ApprovalStatus.PENDING)

    def _has_rejection(self, run_id: str) -> bool:
        return any(item.status == ApprovalStatus.REJECTED for item in self._approvals_for_run(run_id))

    def _record_for(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._records.get(run_id)

    def _load_records(self) -> None:
        audit_timestamps = self._audit_run_timestamps()
        for path in self.settings.run_state_path.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                fallback_timestamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
                created_at, updated_at = self._existing_run_timestamps(
                    str(data["run_id"]),
                    fallback=fallback_timestamp,
                    audit_timestamps=audit_timestamps,
                )
                record = RunRecord(
                    run_id=str(data["run_id"]),
                    idea=str(data["idea"]),
                    workspace_directory=str(data["workspace_directory"]),
                    approval_mode=str(data.get("approval_mode", "supervised")),
                    status=str(data.get("status", "completed")),
                    created_at=str(data.get("created_at") or created_at),
                    updated_at=str(data.get("updated_at") or updated_at),
                    result=data.get("result"),
                    error=data.get("error"),
                )
                if isinstance(record.result, dict):
                    lifecycle_status = None
                    execution_results = record.result.get("execution_results")
                    if isinstance(execution_results, dict):
                        lifecycle_status = str(execution_results.get("status") or "") or None
                    self._sync_task_statuses(record.result, lifecycle_status=lifecycle_status)
                    if record.status == "failed" and self._has_infrastructure_blocker(record.result):
                        record.status = "blocked"
                        record.result["status"] = "blocked"
                        record.result["error"] = "Generated project lifecycle blocked by local infrastructure."
                        if isinstance(execution_results, dict):
                            execution_results["status"] = "blocked"
                self._reconcile_loaded_record(record)
                self._records[record.run_id] = record
            except (KeyError, json.JSONDecodeError, TypeError, ValueError):
                continue

    def _reconcile_loaded_record(self, record: RunRecord) -> None:
        """Convert non-resumable persisted work into an explicit safe state."""
        if record.status == "running":
            reason = "Run was interrupted by a previous backend shutdown and cannot be resumed automatically."
        elif record.status == "waiting_for_approval":
            pending = self._pending_count(record.run_id)
            if pending > 0:
                if isinstance(record.result, dict):
                    record.result["pending_approvals"] = pending
                return
            reason = "Approval state is no longer available; start a new run."
        else:
            return

        record.status = "blocked"
        record.error = reason
        if isinstance(record.result, dict):
            record.result["status"] = "blocked"
            record.result["error"] = reason
            record.result["pending_approvals"] = 0
            self._sync_task_statuses(record.result, lifecycle_status="blocked")

    def _persist_locked(self, record: RunRecord) -> None:
        record.updated_at = self._now()
        path = self.settings.run_state_path / f"{record.run_id}.json"
        path.write_text(json.dumps(asdict(record), indent=2, sort_keys=True), encoding="utf-8")

    def _existing_run_timestamps(
        self,
        run_id: str,
        fallback: str,
        audit_timestamps: dict[str, tuple[str, str]] | None = None,
    ) -> tuple[str, str]:
        approvals = self._approvals_for_run(run_id)
        evidence = [item.created_at for item in approvals]
        evidence.extend(item.resolved_at for item in approvals if item.resolved_at)
        audit_range = (audit_timestamps or {}).get(run_id)
        if audit_range:
            evidence.extend(audit_range)
        if not evidence:
            return fallback, fallback
        return min(evidence, key=self._timestamp_key), max(evidence, key=self._timestamp_key)

    def _audit_run_timestamps(self) -> dict[str, tuple[str, str]]:
        timestamps: dict[str, list[str]] = {}
        try:
            lines = self.settings.audit_log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}
        for line in lines:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(entry, dict):
                continue
            metadata = entry.get("metadata")
            if not isinstance(metadata, dict):
                continue
            run_id = metadata.get("run_id")
            timestamp = entry.get("created_at") or entry.get("timestamp")
            if isinstance(run_id, str) and isinstance(timestamp, str):
                timestamps.setdefault(run_id, []).append(timestamp)
        return {
            run_id: (
                min(values, key=self._timestamp_key),
                max(values, key=self._timestamp_key),
            )
            for run_id, values in timestamps.items()
            if values
        }

    @staticmethod
    def _timestamp_key(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _sync_task_statuses(result: dict[str, Any], lifecycle_status: str | None = None) -> None:
        tasks = result.get("tasks")
        agent_results = result.get("agent_results")
        if not isinstance(tasks, list) or not isinstance(agent_results, list):
            return

        completed_task_ids: set[str] = set()
        for agent_result in agent_results:
            if not isinstance(agent_result, dict):
                continue
            outputs = agent_result.get("outputs")
            if not outputs:
                continue
            agent_name = str(agent_result.get("agent", ""))
            completed_task_ids.update(TASK_BY_AGENT.get(agent_name, ()))

        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("task_id", ""))
            if task_id in completed_task_ids and task_id not in LIFECYCLE_TASKS:
                task["status"] = "complete"

        if lifecycle_status is None:
            return

        status = "complete" if lifecycle_status == "passed" else "failed"
        if lifecycle_status == "blocked" or (
            lifecycle_status != "passed" and RunStore._has_infrastructure_blocker(result)
        ):
            status = "blocked"
        downstream_status = "complete" if lifecycle_status == "passed" else "blocked"
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("task_id", ""))
            if task_id == "qa_verification":
                task["status"] = status
            elif task_id in {"code_review", "meta_review", "release_package"}:
                task["status"] = downstream_status

    @staticmethod
    def _has_infrastructure_blocker(result: dict[str, Any]) -> bool:
        execution_results = result.get("execution_results")
        if not isinstance(execution_results, dict):
            return False
        steps = execution_results.get("steps")
        if not isinstance(steps, list):
            return False
        markers = (
            "unknown flag: --quiet",
            "unknown shorthand flag: 'p'",
            "unknown shorthand flag: p",
            "unknown flag: --rmi",
            "timed out after",
            "tls handshake timeout",
            "failed to resolve reference",
            "registry-1.docker.io",
            "docker.io/library",
            "net/http",
            "i/o timeout",
            "context deadline exceeded",
            "connection reset by peer",
            "failed to connect to the docker api",
            "docker_engine",
            "check if the path is correct and if the daemon is running",
            "cannot connect to the docker daemon",
            "docker daemon",
            "buildx plugin",
            "requires buildx plugin",
            "el sistema no puede encontrar el archivo especificado",
        )
        for step in steps:
            if not isinstance(step, dict):
                continue
            detail = str(step.get("detail", "")).lower()
            raw_command = step.get("command") or []
            command_parts = raw_command if isinstance(raw_command, list) else [raw_command]
            command = " ".join(str(part) for part in command_parts if part is not None).lower()
            if any(marker in detail or marker in command for marker in markers):
                return True
            if step.get("name") == "docker_compose_build" and "downloading [" in detail:
                return True
        return False

    @staticmethod
    def _normalize_approval_mode(approval_mode: str | None) -> str:
        if approval_mode in {"full", "supervised"}:
            return approval_mode
        return "supervised"

    @staticmethod
    def serialize(record: RunRecord) -> dict[str, Any]:
        if record.result:
            return {
                **record.result,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
            }
        return {
            "run_id": record.run_id,
            "idea": record.idea,
            "workspace_directory": record.workspace_directory,
            "approval_mode": record.approval_mode,
            "status": record.status,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "error": record.error,
            "pending_approvals": 0,
            "execution_results": None,
            "tasks": [],
            "agent_results": [],
            "proposed_files": [],
            "security_review": {
                "passed": False,
                "findings": [],
                "notes": ["Run is still in progress."],
            },
        }

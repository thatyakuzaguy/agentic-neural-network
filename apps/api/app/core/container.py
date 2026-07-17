from __future__ import annotations

from agentic_engineering_network.logs.audit import AuditLogger
from agentic_engineering_network.orchestration.engine import AgenticEngineeringNetwork
from agentic_engineering_network.security.approvals import ApprovalCenter

from app.core.run_store import RunStore
from app.core.settings import settings
from app.services.approval_effects import apply_approval_effect
from app.services.agent_office import AgentOfficeService
from app.services.project_lifecycle import ProjectLifecycleRunner


audit_logger = AuditLogger(settings.audit_log_path)
approval_center = ApprovalCenter(audit_logger, settings.approval_state_path)
network = AgenticEngineeringNetwork(settings, audit_logger, approval_center)
lifecycle_runner = ProjectLifecycleRunner(settings, audit_logger)
agent_office_service = AgentOfficeService(audit_logger)
run_store = RunStore(
    settings,
    network,
    lambda item: apply_approval_effect(item, settings, audit_logger),
    lifecycle_runner.run,
)

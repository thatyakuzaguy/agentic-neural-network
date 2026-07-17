from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IdeaSubmission(BaseModel):
    idea: str = Field(min_length=3, max_length=4000)
    workspace_directory: str | None = Field(default=None, max_length=600)
    approval_mode: str = Field(default="supervised", pattern="^(full|supervised)$")


class RunResponse(BaseModel):
    run_id: str
    idea: str
    workspace_directory: str
    approval_mode: str = "supervised"
    status: str = "completed"
    created_at: str | None = None
    updated_at: str | None = None
    error: str | None = None
    pending_approvals: int = 0
    execution_results: dict[str, Any] | None = None
    tasks: list[dict[str, Any]]
    agent_results: list[dict[str, Any]]
    proposed_files: list[dict[str, Any]]
    security_review: dict[str, Any]


class ApprovalDecision(BaseModel):
    approved: bool


class RequirementRefinementRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=4000)


class SeniorAssessmentRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=4000)


class SimulationRequest(BaseModel):
    monthly_visitors: int = Field(default=1000, ge=0, le=10_000_000)
    conversion_rate: float = Field(default=0.03, ge=0, le=1)
    price: float = Field(default=29.0, ge=0, le=100_000)


class BusinessContextSubmission(BaseModel):
    industry: str = ""
    target_customer: str = ""
    geography: str = ""
    revenue_model: str = ""
    budget: str = ""
    timeline: str = ""
    risk_tolerance: str = ""
    compliance_needs: str = ""
    operational_constraints: str = ""
    existing_tools: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)


class HumanGateSubmission(BaseModel):
    gate_id: str
    approver_name: str
    role: str
    decision: str
    comments: str = ""
    risk_acceptance: str = ""


class RiskRegisterSubmission(BaseModel):
    risks: list[dict[str, object]]


class PlatformSettingsUpdate(BaseModel):
    max_repair_attempts: int = Field(ge=1, le=50)


class BillingCheckoutRequest(BaseModel):
    customer_email: str = Field(min_length=3, max_length=320)
    tenant_id: str = Field(default="default", min_length=1, max_length=120)


class BillingPortalRequest(BaseModel):
    customer_id: str = Field(min_length=3, max_length=120)

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ComplianceEvidence:
    control: str
    artifact: str
    owner: str
    status: str
    human_review_required: bool
    collected_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def collect_compliance_evidence() -> list[dict[str, object]]:
    now = datetime.now(timezone.utc).isoformat()
    evidence = [
        ComplianceEvidence("audit_logs", "logs/audit.jsonl", "Security Agent", "available", False, now),
        ComplianceEvidence("privacy_policy", "docs/compliance-templates/PRIVACY_POLICY_TEMPLATE.md", "Compliance Analyst", "template", True, now),
        ComplianceEvidence("terms", "docs/compliance-templates/TERMS_OF_SERVICE_TEMPLATE.md", "Compliance Analyst", "template", True, now),
        ComplianceEvidence("data_retention", "docs/compliance-templates/DATA_RETENTION_POLICY_TEMPLATE.md", "Compliance Analyst", "template", True, now),
        ComplianceEvidence("security_policy", "docs/compliance-templates/SECURITY_POLICY_TEMPLATE.md", "Security Engineer", "template", True, now),
        ComplianceEvidence("ci_security_scan", ".github/workflows/security-scan.yml", "DevOps Engineer", "configured", False, now),
        ComplianceEvidence("backup_restore", "scripts/maintenance/backup-postgres.ps1", "DevOps Engineer", "configured", False, now),
    ]
    return [item.to_dict() for item in evidence]

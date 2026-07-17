from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ComplianceItem:
    id: str
    title: str
    description: str
    legal_review_required: bool = False


@dataclass(frozen=True)
class ComplianceSection:
    id: str
    title: str
    items: list[ComplianceItem]


def get_compliance_checklist() -> list[dict[str, object]]:
    sections = [
        ComplianceSection(
            "gdpr",
            "GDPR",
            [
                ComplianceItem("data_map", "Data map", "Document personal data, processors, retention, and lawful basis.", True),
                ComplianceItem("dsar", "DSAR process", "Implement export, correction, and deletion workflow.", True),
                ComplianceItem("consent", "Consent tracking", "Record consent source, timestamp, and version."),
            ],
        ),
        ComplianceSection(
            "soc2_lite",
            "SOC2-lite",
            [
                ComplianceItem("access_reviews", "Access reviews", "Review production and admin access periodically."),
                ComplianceItem("change_management", "Change management", "Require PR review, CI checks, and deployment audit."),
                ComplianceItem("incident_response", "Incident response", "Create incident roles, severity levels, and notification policy."),
            ],
        ),
        ComplianceSection(
            "iso27001_lite",
            "ISO27001-lite",
            [
                ComplianceItem("risk_register", "Risk register", "Track risks, owners, mitigations, and review dates."),
                ComplianceItem("asset_inventory", "Asset inventory", "Track systems, databases, integrations, and data classes."),
                ComplianceItem("vendor_review", "Vendor review", "Review subprocessors and cloud provider controls.", True),
            ],
        ),
        ComplianceSection(
            "policies",
            "Customer Policies",
            [
                ComplianceItem("privacy", "Privacy policy", "Generate policy template and submit to counsel.", True),
                ComplianceItem("terms", "Terms of service", "Generate terms template and submit to counsel.", True),
                ComplianceItem("cookies", "Cookie policy", "Declare analytics, auth, and support cookies.", True),
                ComplianceItem("dpa", "DPA", "Prepare data processing agreement template.", True),
            ],
        ),
        ComplianceSection(
            "operational",
            "Operational Controls",
            [
                ComplianceItem("retention", "Data retention", "Define retention windows and purge automation."),
                ComplianceItem("audit", "Audit logs", "Record tenant, actor, action, target, metadata, and request id."),
                ComplianceItem("accessibility", "Accessibility", "Run WCAG 2.2 AA checks and keyboard navigation tests."),
            ],
        ),
    ]
    return [asdict(section) for section in sections]


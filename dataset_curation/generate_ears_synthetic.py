from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataset_curation.common import (
    CandidateRow,
    add_common_args,
    ensure_dir,
    resolve_public_path,
    response_from_parts,
)

SYNTHETIC_SOURCE = "EARS_STYLE_PRODUCT_AGENT_SYNTHETIC"
SYNTHETIC_LICENSE = "CC0 original synthetic examples"
SYNTHETIC_URL = "synthetic://product-agent/ears-style"
CONFIDENCE_VALUES = {"High", "Medium", "Low"}
REVIEW_STATES = ("pending", "approved", "rejected")
BANNED_QUALITY_PHRASES = (
    "a operator",
    "expected state transition",
    "in observability",
    "in cli tools",
    "validate access to",
    "clear domain error",
    "keep the workflow scoped to",
    "proves that",
    "before the x is changed",
    "product policy should define",
    "which roles or service accounts may perform",
    "incorrect handling of x can create support or compliance issues",
    "what exact threshold, role, or configuration",
    "when required context is missing or inconsistent",
)


@dataclass(frozen=True)
class GenerationReport:
    generated: int
    skipped_duplicates: int
    skipped_max_per_scenario: int
    written: int
    written_paths: tuple[Path, ...]
    domain_counts: dict[str, int]
    tag_counts: dict[str, int]
    unique_scenario_count: int
    repeated_scenario_ids: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class AuthoredScenario:
    scenario_id: str
    domain: str
    task: str
    requirements: tuple[str, ...]
    ambiguities: tuple[str, ...]
    assumptions: tuple[str, ...]
    acceptance: tuple[str, ...]
    risks: tuple[str, ...]
    confidence: str
    tags: frozenset[str]


def _scenario(
    scenario_id: str,
    domain: str,
    task: str,
    requirements: tuple[str, ...],
    ambiguities: tuple[str, ...],
    assumptions: tuple[str, ...],
    acceptance: tuple[str, ...],
    risks: tuple[str, ...],
    tags: tuple[str, ...],
    confidence: str = "High",
) -> AuthoredScenario:
    return AuthoredScenario(
        scenario_id=scenario_id,
        domain=domain,
        task=task,
        requirements=requirements,
        ambiguities=ambiguities,
        assumptions=assumptions,
        acceptance=acceptance,
        risks=risks,
        confidence=confidence,
        tags=frozenset(tags),
    )


SCENARIO_BANK: tuple[AuthoredScenario, ...] = (
    _scenario(
        "api-customer-cursor-pagination",
        "FastAPI backend APIs",
        "Add cursor pagination to the FastAPI customer search endpoint.",
        (
            "The customer search endpoint must accept limit and cursor query parameters.",
            "The first page must sort customers by created_at descending and id descending.",
            "Malformed cursors must return 400 with error code customer_cursor_invalid.",
        ),
        (
            "What maximum page size should customer search allow?",
            "How long should a customer search cursor remain valid?",
        ),
        ("The existing search filters remain available.",),
        (
            "A customer search request without a cursor returns the first ordered page.",
            "A request with next_cursor returns the next page without duplicate customers.",
            "A malformed customer cursor returns 400 and does not run an unbounded query.",
        ),
        ("Unstable customer ordering can skip records during pagination.",),
        ("api", "edge"),
    ),
    _scenario(
        "api-payment-idempotency-key",
        "FastAPI backend APIs",
        "Require idempotency keys for payment-intent creation.",
        (
            "Payment-intent creation must require an Idempotency-Key header.",
            "A repeated idempotency key must return the original payment-intent response.",
            "A reused idempotency key with a different amount must return 409.",
        ),
        (
            "How long should payment idempotency records be retained?",
            "Should idempotency keys be unique per tenant or per billing account?",
        ),
        ("The payment provider can safely reuse its stored external payment id.",),
        (
            "A payment-intent request without Idempotency-Key returns 400.",
            "Two identical payment-intent requests with the same key create one payment intent.",
            "A reused key with a different amount returns 409 and creates no payment intent.",
        ),
        ("Weak idempotency can charge customers more than once.",),
        ("api", "billing", "edge"),
    ),
    _scenario(
        "api-profile-patch-validation",
        "FastAPI backend APIs",
        "Support partial profile updates with field-level validation.",
        (
            "The profile PATCH endpoint must update only fields present in the request body.",
            "Unknown profile fields must return 422 with the invalid field names.",
            "Email changes must require the existing email verification workflow.",
        ),
        (
            "Should null clear an optional profile field or leave it unchanged?",
            "Which profile fields require re-verification after update?",
        ),
        ("Omitted profile fields keep their current stored values.",),
        (
            "A PATCH request with display_name changes only display_name.",
            "A PATCH request with an unknown profile field returns 422.",
            "A PATCH request changing email creates a verification challenge.",
        ),
        ("Ambiguous PATCH semantics can erase user profile data.",),
        ("api", "security"),
    ),
    _scenario(
        "api-etag-project-update",
        "FastAPI backend APIs",
        "Add ETag concurrency checks to project updates.",
        (
            "Project update requests must include If-Match with the current project ETag.",
            "A stale ETag must return 412 and leave the project unchanged.",
            "Successful updates must return the new ETag in the response headers.",
        ),
        (
            "Should project updates without If-Match be rejected for all clients?",
            "How should ETags be calculated for nested project settings?",
        ),
        ("Project records already store an updated_at value or revision number.",),
        (
            "A project update with the current ETag succeeds and returns a new ETag.",
            "A project update with a stale ETag returns 412.",
            "Concurrent project updates cannot silently overwrite newer values.",
        ),
        ("Missing concurrency checks can lose recent project edits.",),
        ("api", "edge"),
    ),
    _scenario(
        "api-attachment-upload-validation",
        "FastAPI backend APIs",
        "Enforce file size and MIME checks on attachment uploads.",
        (
            "Attachment uploads must reject files larger than the configured size limit.",
            "Only PDF, PNG, and JPEG attachments may be stored.",
            "Rejected uploads must not create attachment database rows.",
        ),
        (
            "What file size limit should apply to each plan tier?",
            "Should SVG uploads be blocked even when the browser reports image/svg+xml?",
        ),
        ("Attachment storage already records tenant id and uploader id.",),
        (
            "A valid PNG under the size limit creates an attachment record.",
            "A PDF above the size limit returns 413 and creates no attachment record.",
            "A disallowed MIME type returns 415 and is not written to storage.",
        ),
        ("Unsafe attachment handling can increase malware and storage risk.",),
        ("api", "security", "edge"),
    ),
    _scenario(
        "tenant-project-settings-isolation",
        "SaaS multi-tenancy",
        "Prevent cross-tenant reads in the project settings API.",
        (
            "Project settings reads must filter by both project id and active tenant id.",
            "Requests for another tenant's project must return 404.",
            "Project settings updates must write the active tenant id into audit metadata.",
        ),
        (
            "Should support users see a different response for cross-tenant requests?",
            "Which request value is authoritative for tenant selection?",
        ),
        ("The authenticated request contains one active tenant id.",),
        (
            "A tenant A user can read tenant A project settings.",
            "A tenant A user receives 404 for a tenant B project id.",
            "A project settings update records the active tenant id in audit metadata.",
        ),
        ("A missing tenant filter can expose customer configuration.",),
        ("multi_tenant", "security", "audit"),
    ),
    _scenario(
        "tenant-feature-flag-overrides",
        "SaaS multi-tenancy",
        "Scope feature flag overrides to a single tenant.",
        (
            "Tenant feature overrides must be stored with tenant id and flag key.",
            "Feature flag lookup must prefer the active tenant override over the global default.",
            "Deleting a tenant override must restore the global default for that tenant.",
        ),
        (
            "Who can create tenant-specific feature flag overrides?",
            "Should deleted overrides remain visible in change history?",
        ),
        ("Global feature flag defaults already exist.",),
        (
            "Tenant A can receive a beta flag while tenant B remains on the global default.",
            "Deleting tenant A's override restores the global default for tenant A.",
            "A feature flag lookup never returns another tenant's override.",
        ),
        ("Flag leakage can expose unfinished features to the wrong customer.",),
        ("multi_tenant", "audit"),
    ),
    _scenario(
        "tenant-invite-domain-policy",
        "SaaS multi-tenancy",
        "Enforce allowed email domains for tenant invitations.",
        (
            "Invitation creation must compare the invited email domain to tenant policy.",
            "Blocked invitation domains must return 422 with the rejected domain.",
            "Allowed-domain changes must be recorded in tenant audit logs.",
        ),
        (
            "Can tenant owners invite external contractors outside the allowed domain list?",
            "Should subdomains inherit the parent domain rule?",
        ),
        ("Tenant invitation email delivery already exists.",),
        (
            "An invite to an allowed domain creates a pending invitation.",
            "An invite to a blocked domain returns 422 and sends no email.",
            "Changing the allowed-domain list writes an audit event.",
        ),
        ("Weak invitation rules can grant access to unmanaged email accounts.",),
        ("multi_tenant", "security", "audit"),
    ),
    _scenario(
        "tenant-dashboard-cache-partition",
        "SaaS multi-tenancy",
        "Partition dashboard summary cache entries by tenant.",
        (
            "Dashboard cache keys must include tenant id and dashboard filter values.",
            "Cache entries must expire after the configured dashboard summary TTL.",
            "A cache miss must compute results only from the active tenant's records.",
        ),
        (
            "What TTL should dashboard summaries use for enterprise tenants?",
            "Should manual data refresh purge dashboard cache immediately?",
        ),
        ("Dashboard summaries are already computed from tenant-scoped queries.",),
        (
            "Tenant A's dashboard request never returns tenant B's cached summary.",
            "Changing dashboard filters produces a separate cache entry.",
            "Expired dashboard cache entries are recomputed from current tenant data.",
        ),
        ("A cache-key mistake can leak tenant metrics.",),
        ("multi_tenant", "security", "edge"),
    ),
    _scenario(
        "tenant-sso-config-owner-only",
        "SaaS multi-tenancy",
        "Restrict SSO configuration changes to tenant owners.",
        (
            "SSO provider configuration updates must require tenant owner permission.",
            "Certificate changes must store the certificate fingerprint, not the raw certificate body.",
            "Disabling SSO must require a confirmation value that includes the tenant slug.",
        ),
        (
            "Should support staff be able to repair SSO for locked-out tenants?",
            "How long should previous SSO certificates remain available for rollback?",
        ),
        ("Tenant owners are already represented in the role system.",),
        (
            "A tenant owner can update SSO metadata for the active tenant.",
            "A non-owner receives 403 when changing SSO settings.",
            "Disabling SSO without the tenant slug confirmation returns 400.",
        ),
        ("Bad SSO controls can lock customers out of their workspace.",),
        ("multi_tenant", "security"),
    ),
    _scenario(
        "rbac-billing-manage-plan",
        "RBAC and permissions",
        "Require billing.manage before changing subscription plans.",
        (
            "Subscription plan changes must require billing.manage permission.",
            "Users with billing.view may read the subscription but may not change it.",
            "Plan changes must record actor id, tenant id, previous plan, and new plan.",
        ),
        (
            "Which default roles should include billing.manage?",
            "Should plan downgrades require a second approval?",
        ),
        ("The permission service can evaluate permissions for the active tenant.",),
        (
            "A billing.view user receives 403 when changing the plan.",
            "A billing.manage user can change the subscription plan.",
            "The billing audit record includes previous plan and new plan.",
        ),
        ("Incorrect billing permissions can create unauthorized charges.",),
        ("security", "billing", "audit"),
    ),
    _scenario(
        "rbac-user-export-permission",
        "RBAC and permissions",
        "Require users.export before downloading tenant user lists.",
        (
            "User CSV exports must require users.export permission.",
            "The export must include only users from the active tenant.",
            "Denied export attempts must be counted in security metrics.",
        ),
        (
            "Should workspace owners receive users.export by default?",
            "Which user fields are safe to include in the export?",
        ),
        ("The user export job already supports tenant filters.",),
        (
            "A user without users.export receives 403 and no export job id.",
            "A user with users.export receives an export job id.",
            "The generated CSV excludes users from other tenants.",
        ),
        ("Bulk user exports can expose personal data.",),
        ("security", "multi_tenant", "audit"),
    ),
    _scenario(
        "rbac-webhook-secret-rotate",
        "RBAC and permissions",
        "Require webhook.secret.rotate before rotating webhook signing secrets.",
        (
            "Webhook secret rotation must require webhook.secret.rotate permission.",
            "Secret rotation must create a new secret version and keep the old version active temporarily.",
            "Secret values must never appear in API responses or audit payloads.",
        ),
        (
            "How long should old webhook secrets remain valid after rotation?",
            "Should failed rotation attempts notify tenant admins?",
        ),
        ("Webhook endpoints already have tenant-scoped signing secrets.",),
        (
            "A user without webhook.secret.rotate receives 403.",
            "A permitted user receives a new secret once after rotation.",
            "Audit logs show secret rotation without storing the secret value.",
        ),
        ("Webhook secret mistakes can break production integrations.",),
        ("security", "webhook", "audit"),
    ),
    _scenario(
        "rbac-role-self-escalation",
        "RBAC and permissions",
        "Prevent users from granting permissions to their own role.",
        (
            "Custom role edits must reject changes that grant the acting user new permissions.",
            "Role edits must show the added and removed permission names in audit logs.",
            "Role edits must return 409 when the role changed since it was loaded.",
        ),
        (
            "Can organization owners edit their own role during initial setup?",
            "Should self-escalation checks apply to inherited roles?",
        ),
        ("The API can determine which roles are assigned to the acting user.",),
        (
            "A user cannot add billing.manage to a role assigned to themselves.",
            "A role edit by a separate authorized admin succeeds.",
            "Concurrent role edits with stale version values return 409.",
        ),
        ("Role editing bugs can create privilege escalation.",),
        ("security", "audit", "edge"),
    ),
    _scenario(
        "rbac-production-deploy-command",
        "RBAC and permissions",
        "Require deploy.production before running production deploy commands.",
        (
            "Production deploy commands must require deploy.production permission.",
            "Denied deploy commands must show the target environment and missing permission.",
            "Successful deploy commands must write a release audit event.",
        ),
        (
            "Should temporary deploy permission expire automatically?",
            "Who can grant deploy.production during an incident?",
        ),
        ("The CLI sends the authenticated user identity to the deployment API.",),
        (
            "A user without deploy.production cannot start a production deploy.",
            "A permitted release manager can start a production deploy.",
            "The release audit event includes actor, environment, version, and timestamp.",
        ),
        ("Weak deploy permissions can bypass release governance.",),
        ("security", "devops", "audit"),
    ),
    _scenario(
        "audit-impersonation-session",
        "Audit logging",
        "Record audit events for admin impersonation sessions.",
        (
            "Starting impersonation must write an audit event before issuing the session token.",
            "Ending impersonation must write an audit event with the end reason.",
            "Impersonation audit events must include admin id, target user id, tenant id, and request id.",
        ),
        (
            "Should the target user receive a notification when impersonation starts?",
            "What end reasons should be normalized for reporting?",
        ),
        ("Impersonation already requires a privileged admin permission.",),
        (
            "Starting impersonation creates an audit event and then returns a session token.",
            "If audit storage is unavailable, impersonation returns 503 and creates no session.",
            "Ending impersonation records manual, timeout, or revoked as the end reason.",
        ),
        ("Missing impersonation audits can hide privileged access to customer data.",),
        ("audit", "security", "observability"),
    ),
    _scenario(
        "audit-api-key-reveal",
        "Audit logging",
        "Audit every API key secret reveal.",
        (
            "Revealing an API key secret must create an audit event.",
            "The audit event must include actor id, tenant id, API key id, and request id.",
            "The audit event must not include the API key secret value.",
        ),
        (
            "Should repeated API key reveals trigger a security alert?",
            "How long should reveal audit events be retained?",
        ),
        ("API key reveal is already limited to newly created or explicitly rotated keys.",),
        (
            "Revealing an API key creates exactly one audit event.",
            "The audit event includes API key id but not the secret value.",
            "Failed reveal attempts due to permission denial are counted in security metrics.",
        ),
        ("Untracked secret access makes incident investigation harder.",),
        ("audit", "security"),
    ),
    _scenario(
        "audit-data-export",
        "Audit logging",
        "Write audit records for customer data exports.",
        (
            "Customer data export requests must write an audit event when the job is created.",
            "The audit event must include actor id, tenant id, filters, export type, and request id.",
            "Export completion must update the audit event with row count and file size.",
        ),
        (
            "Which export filters should be redacted from audit metadata?",
            "Should cancelled exports keep their original audit event?",
        ),
        ("Export jobs already have stable job ids.",),
        (
            "Creating a customer export writes an audit event with export filters.",
            "Completing the export records row count and file size.",
            "Cancelled exports remain searchable in audit history.",
        ),
        ("Missing export audits can hide bulk data access.",),
        ("audit", "security", "multi_tenant"),
    ),
    _scenario(
        "audit-webhook-disable",
        "Audit logging",
        "Record audit events when webhook endpoints are disabled.",
        (
            "Disabling a webhook endpoint must write an audit event.",
            "The audit event must include endpoint id, tenant id, actor id, and disable reason.",
            "Automatic endpoint disables must use a system actor with the delivery failure summary.",
        ),
        (
            "Which failure reasons should automatically disable a webhook endpoint?",
            "Should tenant admins be notified after an automatic disable?",
        ),
        ("Webhook endpoints already have stable endpoint ids.",),
        (
            "A manual webhook disable writes an audit event with the admin actor id.",
            "An automatic webhook disable writes an audit event with system actor.",
            "The audit event includes the disable reason without webhook secrets.",
        ),
        ("Webhook disables without audit history make integration outages harder to diagnose.",),
        ("audit", "webhook", "observability"),
    ),
    _scenario(
        "audit-alert-mute",
        "Audit logging",
        "Audit alert mute and unmute actions.",
        (
            "Muting an alert must require a reason and duration.",
            "Mute and unmute actions must write audit events with actor id and alert id.",
            "Expired alert mutes must be marked as expired in audit history.",
        ),
        (
            "What maximum mute duration should production alerts allow?",
            "Should repeated mutes require incident commander approval?",
        ),
        ("Alerts already have stable ids in the monitoring system.",),
        (
            "Muting an alert without a reason returns 422.",
            "A successful alert mute writes an audit event with duration.",
            "Unmuting the alert writes a separate audit event.",
        ),
        ("Unexplained alert mutes can hide production incidents.",),
        ("audit", "observability", "devops"),
    ),
    _scenario(
        "webhook-invoice-paid-retry",
        "Webhooks",
        "Retry signed invoice.paid webhook deliveries.",
        (
            "Failed invoice.paid deliveries with retryable status codes must be retried.",
            "Each retry must include a fresh timestamp and HMAC signature.",
            "Retry history must show attempt number, response status, and next scheduled time.",
        ),
        (
            "Which HTTP status codes should be retryable for invoice.paid?",
            "What maximum retry window should apply to invoice webhooks?",
        ),
        ("Webhook endpoints already store an active signing secret.",),
        (
            "A 500 response schedules a later invoice.paid retry.",
            "Each invoice.paid retry has a different timestamped signature.",
            "Retry history shows every attempt and final failure status.",
        ),
        ("Webhook retries can duplicate customer-side billing actions.",),
        ("webhook", "billing", "security", "edge"),
    ),
    _scenario(
        "webhook-secret-overlap",
        "Webhooks",
        "Rotate webhook signing secrets with overlap support.",
        (
            "Secret rotation must create a new active webhook secret version.",
            "The previous secret must continue to validate signatures during the overlap window.",
            "The API must expose the overlap expiration time without returning old secret values.",
        ),
        (
            "How long should webhook secret overlap last?",
            "Should tenants be able to end the overlap window early?",
        ),
        ("Webhook signature verification supports multiple active secret versions.",),
        (
            "New webhook deliveries use the new secret after rotation.",
            "Deliveries signed with the old secret validate during the overlap window.",
            "After overlap expiration, the old secret no longer validates signatures.",
        ),
        ("Bad secret rotation can break production webhook consumers.",),
        ("webhook", "security"),
    ),
    _scenario(
        "webhook-endpoint-verification",
        "Webhooks",
        "Verify webhook endpoint ownership before activation.",
        (
            "New webhook endpoints must remain inactive until ownership verification succeeds.",
            "Verification must require a tenant-specific challenge token.",
            "Expired verification challenges must be regenerated instead of reused.",
        ),
        (
            "How long should endpoint verification challenges remain valid?",
            "Should verified endpoints be rechecked after URL changes?",
        ),
        ("Tenants can edit webhook endpoint URLs in the product UI.",),
        (
            "An unverified endpoint receives no production webhook events.",
            "A valid challenge response activates the webhook endpoint.",
            "Changing the endpoint URL resets verification status.",
        ),
        ("Sending events to unverified endpoints can leak payload data.",),
        ("webhook", "security", "edge"),
    ),
    _scenario(
        "webhook-event-subscriptions",
        "Webhooks",
        "Allow tenants to subscribe to selected webhook event types.",
        (
            "Webhook endpoints must store an explicit set of subscribed event types.",
            "Delivery workers must send only events included in the endpoint subscription.",
            "Removing an event type must stop future deliveries of that type.",
        ),
        (
            "Which event types should new webhook endpoints receive by default?",
            "Should security events be mandatory for all endpoints?",
        ),
        ("Webhook events already have stable event type names.",),
        (
            "An endpoint subscribed to invoice.paid receives invoice.paid events.",
            "The same endpoint does not receive user.deleted events.",
            "Removing invoice.paid from the subscription stops later invoice.paid deliveries.",
        ),
        ("Over-delivery can expose events a tenant did not request.",),
        ("webhook", "security"),
    ),
    _scenario(
        "webhook-dead-letter-review",
        "Webhooks",
        "Store permanently failed webhook deliveries for tenant review.",
        (
            "Webhook deliveries that exhaust retries must create a dead-letter record.",
            "Dead-letter records must include event type, endpoint id, final status, and last error.",
            "Tenant admins must be able to filter dead-letter records by endpoint and event type.",
        ),
        (
            "How long should webhook dead-letter records be retained?",
            "Should tenants be able to replay dead-letter records in bulk?",
        ),
        ("Retry exhaustion is already detected by the delivery worker.",),
        (
            "A webhook delivery that exhausts retries appears in dead-letter review.",
            "Dead-letter records show endpoint id and final HTTP status.",
            "Filtering dead-letter records by event type returns only matching records.",
        ),
        ("Lost webhook failure evidence makes integration support harder.",),
        ("webhook", "observability", "edge"),
    ),
    _scenario(
        "billing-invoice-pdf",
        "Billing and invoices",
        "Generate tenant-safe invoice PDFs for paid invoices.",
        (
            "Paid invoice PDFs must include invoice number, billing period, line items, tax, and total.",
            "Invoice PDF requests must require the invoice to belong to the active tenant.",
            "Unpaid invoices must return 409 and must not generate a paid invoice PDF.",
        ),
        (
            "Should invoice PDFs include customer tax identifiers?",
            "How long should generated invoice PDFs be cached?",
        ),
        ("Invoice totals and tax amounts already exist in billing records.",),
        (
            "A tenant can download a PDF for its own paid invoice.",
            "A tenant receives 404 for another tenant's invoice id.",
            "An unpaid invoice PDF request returns 409 and creates no PDF file.",
        ),
        ("Invoice PDFs can expose billing and tax data.",),
        ("billing", "multi_tenant", "security"),
    ),
    _scenario(
        "billing-refund-approval",
        "Billing and invoices",
        "Require approval before issuing large refunds.",
        (
            "Refunds above the configured amount must enter pending approval.",
            "Approved refunds must record approver id and approval timestamp.",
            "Rejected refunds must keep the invoice balance unchanged.",
        ),
        (
            "What refund amount should require approval?",
            "Can the requester also approve the refund during an incident?",
        ),
        ("Small refunds already process through the payment provider.",),
        (
            "A small refund processes without approval.",
            "A large refund creates a pending approval record.",
            "A rejected large refund does not call the payment provider.",
        ),
        ("Weak refund controls can create financial loss.",),
        ("billing", "audit", "security"),
    ),
    _scenario(
        "billing-metered-usage-finalization",
        "Billing and invoices",
        "Reconcile metered usage before invoice finalization.",
        (
            "Invoice finalization must compare metered usage totals to raw usage events.",
            "Invoices with unreconciled usage must remain in draft status.",
            "Reconciliation results must list product id, expected quantity, and actual quantity.",
        ),
        (
            "What grace period should allow late-arriving usage events?",
            "Should finance users be able to finalize invoices with usage warnings?",
        ),
        ("Usage events already include tenant id, product id, and event timestamp.",),
        (
            "An invoice with matching usage totals can be finalized.",
            "An invoice with missing usage events stays in draft status.",
            "The reconciliation report identifies the product with the mismatch.",
        ),
        ("Usage reconciliation errors can underbill or overbill tenants.",),
        ("billing", "pipeline", "edge"),
    ),
    _scenario(
        "billing-proration-preview",
        "Billing and invoices",
        "Preview prorated charges before subscription plan changes.",
        (
            "Plan change preview must show prorated charge or credit before confirmation.",
            "The preview must include current plan, target plan, effective date, and estimated total.",
            "Confirming a plan change must use the preview id that the user reviewed.",
        ),
        (
            "How long should a proration preview remain valid?",
            "Should previews include taxes for all billing regions?",
        ),
        ("The billing provider can calculate plan-change prorations.",),
        (
            "A plan change preview shows the target plan and estimated total.",
            "Confirming with an expired preview id returns 409.",
            "The confirmed plan change matches the reviewed preview id.",
        ),
        ("Unclear previews can surprise customers with unexpected charges.",),
        ("billing", "api", "edge"),
    ),
    _scenario(
        "billing-seat-reconciliation",
        "Billing and invoices",
        "Reconcile subscription seats from active user count.",
        (
            "Seat reconciliation must count active billable users for the tenant.",
            "Suspended users must not increase the subscription seat quantity.",
            "Seat quantity changes must create billing audit records.",
        ),
        (
            "Which user states should count as billable seats?",
            "Should seat decreases apply immediately or at renewal?",
        ),
        ("The user service exposes user state for the active tenant.",),
        (
            "Active users increase the tenant's billable seat count.",
            "Suspended users are excluded from seat reconciliation.",
            "A seat quantity change writes a billing audit record.",
        ),
        ("Seat-count errors can cause recurring invoice disputes.",),
        ("billing", "multi_tenant", "audit"),
    ),
    _scenario(
        "csv-customer-import-preview",
        "CSV/import/export",
        "Validate customer CSV imports before record creation.",
        (
            "Customer CSV uploads must validate required headers before row parsing.",
            "Import preview must show row number, field name, and validation message for each error.",
            "Customer records must be created only after the user confirms a valid preview.",
        ),
        (
            "What maximum CSV file size should be accepted?",
            "Should existing customers be updated or rejected when emails already exist?",
        ),
        ("The first version creates new customers only.",),
        (
            "A CSV file missing email header returns a header validation error.",
            "Invalid rows appear in preview with row numbers.",
            "Confirming a valid preview creates the expected customer records.",
        ),
        ("Partial CSV imports can corrupt customer records.",),
        ("multi_tenant", "edge"),
    ),
    _scenario(
        "csv-audit-log-export",
        "CSV/import/export",
        "Export filtered audit logs as CSV for tenant administrators.",
        (
            "Audit CSV exports must apply tenant id, date range, actor, and event type filters.",
            "The CSV must include event id, timestamp, actor id, event type, target id, and result.",
            "Date ranges above the configured limit must return 400.",
        ),
        (
            "What maximum date range should audit CSV exports allow?",
            "Should event metadata be excluded or included with redaction?",
        ),
        ("Audit events are already tenant-scoped.",),
        (
            "An audit CSV export includes only events from the active tenant.",
            "A date range above the configured limit returns 400.",
            "The CSV contains event id, timestamp, actor id, event type, target id, and result.",
        ),
        ("Audit exports can leak sensitive operational details.",),
        ("audit", "security", "multi_tenant"),
    ),
    _scenario(
        "csv-product-sku-import",
        "CSV/import/export",
        "Import product catalog rows with duplicate SKU detection.",
        (
            "Product CSV preview must detect duplicate SKUs within the uploaded file.",
            "Duplicate SKUs must block import confirmation.",
            "Valid product rows must create product records with tenant id and SKU.",
        ),
        (
            "Should SKU matching be case-sensitive?",
            "Can imports update existing products or only create new products?",
        ),
        ("Product SKU is unique within a tenant.",),
        (
            "A CSV with duplicate SKU values shows duplicate-row errors.",
            "Import confirmation is disabled while duplicate SKUs exist.",
            "A valid product CSV creates tenant-scoped product records.",
        ),
        ("Duplicate product SKUs can break ordering and reporting workflows.",),
        ("multi_tenant", "edge"),
    ),
    _scenario(
        "csv-error-file-download",
        "CSV/import/export",
        "Provide downloadable error files for failed CSV imports.",
        (
            "Failed CSV imports must create an error file with row numbers and messages.",
            "Error files must not include secrets from ignored columns.",
            "Error files must expire after the configured retention period.",
        ),
        (
            "How long should CSV error files remain available?",
            "Should error files include the original uploaded values?",
        ),
        ("Import jobs already store row-level validation results.",),
        (
            "A failed CSV import creates an error file.",
            "The error file includes row number and validation message.",
            "Expired error files are no longer downloadable.",
        ),
        ("Error files can leak sensitive uploaded data if not redacted.",),
        ("security", "edge"),
    ),
    _scenario(
        "csv-large-import-background",
        "CSV/import/export",
        "Parse large CSV uploads in a background job.",
        (
            "CSV files above the synchronous size limit must create a parse job.",
            "The parse job must expose queued, processing, failed, and completed states.",
            "Users must be able to view parse progress without re-uploading the file.",
        ),
        (
            "What file size should switch parsing to a background job?",
            "How often should parse progress be updated?",
        ),
        ("Uploaded CSV files are stored in tenant-scoped temporary storage.",),
        (
            "A small CSV file returns an immediate preview.",
            "A large CSV file returns a parse job id.",
            "The parse job status shows processed row count while running.",
        ),
        ("Large synchronous CSV parsing can degrade API workers.",),
        ("edge", "observability", "multi_tenant"),
    ),
    _scenario(
        "job-nightly-usage-aggregation",
        "Background jobs",
        "Run nightly usage aggregation as an idempotent background job.",
        (
            "The nightly usage job must aggregate usage by tenant, product, and usage date.",
            "Rerunning the job for the same tenant and date must update the same aggregate row.",
            "Failed tenant aggregations must be recorded without stopping other tenants.",
        ),
        (
            "Which timezone defines a usage date for each tenant?",
            "Should late-arriving usage events reopen finalized aggregates?",
        ),
        ("Usage events contain tenant id, product id, quantity, and timestamp.",),
        (
            "Running the usage job twice does not create duplicate aggregate rows.",
            "A failed tenant aggregation records tenant id and failure reason.",
            "Successful tenant aggregates remain available when another tenant fails.",
        ),
        ("Non-idempotent usage jobs can inflate billing quantities.",),
        ("observability", "billing", "multi_tenant", "edge"),
    ),
    _scenario(
        "job-export-expiry-cleanup",
        "Background jobs",
        "Expire completed export files after retention.",
        (
            "The export cleanup job must delete files older than the export retention period.",
            "The cleanup job must leave active and recently completed exports untouched.",
            "Deleted export files must be recorded with export id and deletion timestamp.",
        ),
        (
            "What retention period should apply to each export type?",
            "Should tenants receive a warning before export files expire?",
        ),
        ("Export records include completion timestamp and storage path.",),
        (
            "An export older than retention is deleted by cleanup.",
            "A recent export remains downloadable after cleanup.",
            "Deleted exports have deletion timestamp in the export record.",
        ),
        ("Cleanup mistakes can delete customer deliverables too early.",),
        ("observability", "edge"),
    ),
    _scenario(
        "job-invoice-finalization-resume",
        "Background jobs",
        "Finalize invoices in a resumable background job.",
        (
            "Invoice finalization must skip invoices already marked finalized.",
            "Failed invoice finalization must store invoice id and failure reason.",
            "Retrying the job must continue with invoices that are still draft or failed.",
        ),
        (
            "How many retry attempts should each failed invoice receive?",
            "Should payment-provider timeouts pause the whole batch?",
        ),
        ("Invoice records have draft, failed, and finalized states.",),
        (
            "A finalized invoice is not finalized a second time.",
            "A failed invoice stores a failure reason.",
            "Retrying the job processes failed invoices without duplicating finalized invoices.",
        ),
        ("Invoice retry bugs can create duplicate billing actions.",),
        ("billing", "observability", "edge"),
    ),
    _scenario(
        "job-stuck-watchdog",
        "Background jobs",
        "Detect and mark stuck background jobs.",
        (
            "The job watchdog must mark jobs as stuck after the configured timeout.",
            "Stuck job records must include job type, started_at, and worker id.",
            "Stuck jobs must stop counting as actively running jobs.",
        ),
        (
            "What timeout should apply to each job type?",
            "Should stuck jobs be retried automatically or require operator review?",
        ),
        ("Workers update heartbeat timestamps while processing jobs.",),
        (
            "A job without heartbeat past timeout moves to stuck state.",
            "The stuck job record includes worker id and job type.",
            "A stuck job no longer blocks the active job concurrency limit.",
        ),
        ("Stuck jobs can block queues and hide production failures.",),
        ("observability", "edge"),
    ),
    _scenario(
        "job-search-index-rebuild",
        "Background jobs",
        "Rebuild search indexes without blocking API reads.",
        (
            "Search index rebuilds must write to a new index version.",
            "API reads must continue using the active index while rebuild runs.",
            "Cutover must switch to the rebuilt index only after indexing completes.",
        ),
        (
            "How should failed rebuilds be reported to operators?",
            "Should cutover require manual approval for large tenants?",
        ),
        ("The search service supports multiple index versions.",),
        (
            "Search API reads continue during index rebuild.",
            "A failed rebuild leaves the previous index active.",
            "A completed rebuild switches search reads to the new index version.",
        ),
        ("Bad index cutover can hide searchable records.",),
        ("observability", "multi_tenant", "edge"),
    ),
    _scenario(
        "obs-invoice-job-alerts",
        "Observability",
        "Add metrics and alerts for delayed invoice jobs.",
        (
            "Invoice workers must emit queue age and processing duration metrics.",
            "Queue age above the production threshold must trigger an alert.",
            "Invoice job logs must include job id, tenant id, attempt number, and failure reason.",
        ),
        (
            "What queue-age threshold should trigger an invoice job alert?",
            "Which on-call rotation owns delayed invoice job alerts?",
        ),
        ("A metrics backend and structured logger are already available.",),
        (
            "Queued invoice jobs emit queue age metrics.",
            "An alert fires when invoice queue age exceeds the threshold.",
            "Failed invoice job logs include tenant id and failure reason.",
        ),
        ("Missing invoice job telemetry can hide billing incidents.",),
        ("observability", "billing"),
    ),
    _scenario(
        "obs-api-validation-errors",
        "Observability",
        "Track API validation errors by endpoint.",
        (
            "API validation failures must increment a metric labeled by endpoint and error code.",
            "Metrics must not include raw request bodies or customer email addresses.",
            "Dashboards must show validation error rate over the selected time window.",
        ),
        (
            "Which status codes count as validation errors?",
            "Should internal endpoints appear on the public API dashboard?",
        ),
        ("API error handlers already produce stable error codes.",),
        (
            "A 422 validation failure increments the endpoint validation metric.",
            "The metric label includes error code but not request body.",
            "The dashboard displays validation error rate by endpoint.",
        ),
        ("High-cardinality labels can increase monitoring cost.",),
        ("observability", "api"),
    ),
    _scenario(
        "obs-webhook-failure-alert",
        "Observability",
        "Alert on webhook delivery failure spikes.",
        (
            "Webhook delivery failures must be counted by endpoint id and event type.",
            "Failure rate above the configured window must trigger an alert.",
            "Alerts must include affected tenant id, endpoint id, and recent failure count.",
        ),
        (
            "What failure-rate window should page the on-call engineer?",
            "Should tenants receive automatic notifications for delivery failure spikes?",
        ),
        ("Webhook delivery workers already record response status.",),
        (
            "A spike in webhook failures triggers an alert.",
            "The alert includes tenant id, endpoint id, and failure count.",
            "Successful webhook deliveries do not count toward the failure alert.",
        ),
        ("Noisy webhook alerts can hide real integration outages.",),
        ("observability", "webhook", "edge"),
    ),
    _scenario(
        "obs-pipeline-lag",
        "Observability",
        "Alert when data pipeline lag exceeds SLA.",
        (
            "Pipeline workers must emit lag seconds for each active pipeline.",
            "Lag above the tenant SLA must trigger an alert with pipeline id and tenant id.",
            "Resolved lag alerts must close automatically after lag returns below threshold.",
        ),
        (
            "Should lag thresholds differ by pipeline tier?",
            "How long must lag stay healthy before resolving an alert?",
        ),
        ("Each pipeline has an owner tenant and configured SLA.",),
        (
            "Pipeline lag above SLA creates an alert.",
            "The alert identifies tenant id and pipeline id.",
            "The alert resolves after lag remains below threshold.",
        ),
        ("Missing lag alerts can leave customers with stale reports.",),
        ("observability", "pipeline", "multi_tenant"),
    ),
    _scenario(
        "obs-cli-failure-telemetry",
        "Observability",
        "Capture anonymized CLI command failure telemetry.",
        (
            "CLI failure telemetry must include command name, error code, and CLI version.",
            "Telemetry must not include local file paths, tokens, or environment variable values.",
            "Users must be able to disable telemetry with a config setting.",
        ),
        (
            "Should telemetry be enabled by default for internal builds?",
            "How should telemetry opt-out be displayed in CLI help?",
        ),
        ("The CLI already has a local configuration file.",),
        (
            "A failed CLI command emits command name and error code.",
            "Telemetry payloads do not include local file paths.",
            "Setting telemetry=false disables future telemetry events.",
        ),
        ("Telemetry can collect too much developer context if fields are not limited.",),
        ("observability", "cli", "security"),
    ),
    _scenario(
        "rate-api-token-endpoint",
        "Rate limiting",
        "Add per-tenant limits to the API token endpoint.",
        (
            "API token requests must be counted by tenant id and endpoint name.",
            "Requests over the tenant limit must return 429 with retry_after seconds.",
            "Tenant A exceeding its limit must not throttle tenant B.",
        ),
        (
            "What token request limit should apply to each plan tier?",
            "Should failed authentication attempts count against the same limit?",
        ),
        ("Tenant id is available before token issuance.",),
        (
            "Requests below the tenant limit receive token responses.",
            "Requests above the tenant limit receive 429 with retry_after.",
            "Tenant B token requests succeed while tenant A is throttled.",
        ),
        ("Wrong rate-limit keys can block the wrong tenant.",),
        ("security", "multi_tenant", "edge"),
    ),
    _scenario(
        "rate-login-attempts",
        "Rate limiting",
        "Limit repeated login attempts by IP and tenant.",
        (
            "Failed login attempts must be counted by tenant id and source IP.",
            "Requests above the login limit must return a generic throttled response.",
            "Successful login after throttling must clear only the user's own failure counter.",
        ),
        (
            "How long should login throttling last after repeated failures?",
            "Should trusted SSO tenants use separate limits?",
        ),
        ("Login responses must not reveal whether an account exists.",),
        (
            "Repeated failed logins from one IP trigger throttling.",
            "The throttled response does not confirm account existence.",
            "A different tenant is not throttled by the first tenant's failures.",
        ),
        ("Poor login limits can help attackers brute-force accounts.",),
        ("security", "multi_tenant", "edge"),
    ),
    _scenario(
        "rate-export-concurrency",
        "Rate limiting",
        "Limit concurrent exports per tenant.",
        (
            "Export job creation must enforce a per-tenant concurrency limit.",
            "Requests above the export concurrency limit must return 429.",
            "Completed, failed, and cancelled export jobs must release concurrency slots.",
        ),
        (
            "Should export concurrency differ by plan tier?",
            "Should queued exports be allowed instead of returning 429?",
        ),
        ("Export jobs already have terminal states.",),
        (
            "A tenant below the export limit can create an export job.",
            "A tenant at the export limit receives 429 for a new export.",
            "Finishing an export allows the tenant to create another export.",
        ),
        ("Unbounded exports can overload storage and databases.",),
        ("multi_tenant", "edge"),
    ),
    _scenario(
        "rate-webhook-replay",
        "Rate limiting",
        "Limit webhook replay requests per endpoint.",
        (
            "Webhook replay requests must be counted by endpoint id and tenant id.",
            "Replay requests above the limit must return 429.",
            "Live webhook delivery must not consume replay quota.",
        ),
        (
            "How many webhook replays should one endpoint allow per hour?",
            "Should support staff be able to bypass replay limits?",
        ),
        ("Webhook replay already creates a replay job.",),
        (
            "Replay requests below the endpoint limit create replay jobs.",
            "Replay requests above the endpoint limit return 429.",
            "Live webhook deliveries continue while replay requests are throttled.",
        ),
        ("Unbounded replays can delay live webhook events.",),
        ("webhook", "edge", "multi_tenant"),
    ),
    _scenario(
        "rate-metrics-ingest",
        "Rate limiting",
        "Limit custom metrics ingestion per tenant.",
        (
            "Metrics ingestion must enforce per-tenant event limits.",
            "Rejected ingestion requests must report accepted and dropped event counts.",
            "The ingestion limiter must not store metric label values in rate-limit keys.",
        ),
        (
            "What burst allowance should metrics ingestion support?",
            "Should dropped custom metrics create tenant notifications?",
        ),
        ("Metrics ingestion accepts batched events.",),
        (
            "A metrics batch below the tenant limit is accepted.",
            "A metrics batch above the tenant limit reports dropped count.",
            "Rate-limit keys do not include high-cardinality metric label values.",
        ),
        ("Ingestion limits can drop observability data during incidents.",),
        ("observability", "multi_tenant", "edge"),
    ),
    _scenario(
        "security-step-up-user-export",
        "Security controls",
        "Require step-up authentication for full user exports.",
        (
            "Full user exports must require recent step-up authentication.",
            "Expired step-up authentication must return 403 with code step_up_required.",
            "Successful user exports must create an audit event with actor id and row count.",
        ),
        (
            "How recent must step-up authentication be for user exports?",
            "Which authentication factors satisfy step-up requirements?",
        ),
        ("The authentication service records the last step-up timestamp.",),
        (
            "An admin without recent step-up receives 403 and no export job.",
            "An admin with recent step-up can create a user export.",
            "The user export audit event includes actor id and row count.",
        ),
        ("Bulk user exports can expose personal data after account compromise.",),
        ("security", "audit", "multi_tenant"),
    ),
    _scenario(
        "security-session-revoke-password",
        "Security controls",
        "Revoke existing sessions after password changes.",
        (
            "Password changes must revoke all other active sessions for the user.",
            "The current session may remain active only after successful password confirmation.",
            "Session revocation must write a security audit event.",
        ),
        (
            "Should trusted devices remain signed in after password change?",
            "Should API tokens be revoked with browser sessions?",
        ),
        ("Sessions are stored with user id and device id.",),
        (
            "Changing a password revokes the user's other browser sessions.",
            "The current session remains active after successful password confirmation.",
            "A security audit event records the session revocation count.",
        ),
        ("Stolen sessions can remain active if revocation is incomplete.",),
        ("security", "audit"),
    ),
    _scenario(
        "security-error-secret-redaction",
        "Security controls",
        "Redact secrets from API error responses.",
        (
            "API error rendering must redact tokens, API keys, and password-like values.",
            "Redaction must apply to validation errors and unhandled exception messages.",
            "Security logs must record that redaction occurred without storing the secret.",
        ),
        (
            "Which secret patterns should the redactor recognize?",
            "Should redacted errors include a support reference id?",
        ),
        ("The API already routes errors through a shared error renderer.",),
        (
            "An error containing an API key returns a response with [REDACTED].",
            "Validation errors and exception errors both use the redactor.",
            "Security logs show a redaction event without the original secret value.",
        ),
        ("Secret leakage in API errors can compromise integrations.",),
        ("security", "api", "observability"),
    ),
    _scenario(
        "security-custom-domain-takeover",
        "Security controls",
        "Prevent custom domain takeover after tenant deletion.",
        (
            "Deleted tenant domains must enter a quarantine period.",
            "A quarantined domain must require fresh DNS verification before reuse.",
            "Domain reuse attempts must write a security audit event.",
        ),
        (
            "How long should deleted custom domains remain quarantined?",
            "Who can manually release a quarantined domain?",
        ),
        ("Custom domains already have verification records.",),
        (
            "A deleted tenant's domain cannot be claimed during quarantine.",
            "Fresh DNS verification allows reuse after quarantine.",
            "A blocked reuse attempt writes a security audit event.",
        ),
        ("Domain takeover can redirect customer traffic.",),
        ("security", "multi_tenant", "audit"),
    ),
    _scenario(
        "security-api-key-expiry",
        "Security controls",
        "Require expiry dates for new API keys.",
        (
            "API key creation must require an expiry date.",
            "Expiry dates beyond the tenant policy must return 422.",
            "Expired API keys must fail authentication with code api_key_expired.",
        ),
        (
            "What maximum API key lifetime should each plan allow?",
            "Should existing keys without expiry be grandfathered?",
        ),
        ("API key authentication already loads key metadata.",),
        (
            "Creating an API key without expiry returns 422.",
            "Creating an API key beyond the maximum lifetime returns 422.",
            "Using an expired API key fails with api_key_expired.",
        ),
        ("Long-lived API keys increase compromise duration.",),
        ("security", "api", "edge"),
    ),
    _scenario(
        "pipeline-schema-activation",
        "Data pipelines",
        "Check destination schema before activating a data pipeline.",
        (
            "Pipeline activation must inspect required destination tables and columns.",
            "Missing required columns must block activation with table and column names.",
            "Schema check results must be stored with pipeline id, tenant id, and checked_at.",
        ),
        (
            "Should nullable type mismatches block activation or only warn?",
            "How often should active pipelines recheck destination schemas?",
        ),
        ("Pipeline configuration lists required destination tables and columns.",),
        (
            "A pipeline with all destination columns can be activated.",
            "A pipeline missing a required column remains inactive.",
            "The schema check result lists the missing table and column.",
        ),
        ("Schema drift can create failed or partial data loads.",),
        ("pipeline", "multi_tenant", "edge"),
    ),
    _scenario(
        "pipeline-backfill-window",
        "Data pipelines",
        "Limit historical backfill windows for data pipelines.",
        (
            "Backfill requests must include start date and end date.",
            "Backfill date ranges beyond the configured maximum must return 422.",
            "Accepted backfills must show estimated record count before execution.",
        ),
        (
            "What maximum backfill window should each pipeline tier allow?",
            "Should operators approve backfills above a record-count threshold?",
        ),
        ("Pipeline sources can estimate record count for a date range.",),
        (
            "A backfill within the allowed window is accepted.",
            "A backfill beyond the maximum window returns 422.",
            "Accepted backfills show estimated record count before execution.",
        ),
        ("Unbounded backfills can overload source systems.",),
        ("pipeline", "edge"),
    ),
    _scenario(
        "pipeline-dead-letter-records",
        "Data pipelines",
        "Store rejected pipeline records with validation reasons.",
        (
            "Invalid pipeline records must create dead-letter entries.",
            "Dead-letter entries must include source record id, field name, and validation reason.",
            "Dead-letter entries must be filterable by pipeline id and error type.",
        ),
        (
            "How long should dead-letter records be retained?",
            "Should tenants be able to reprocess corrected dead-letter records?",
        ),
        ("Pipeline validation already identifies field-level errors.",),
        (
            "An invalid source record creates a dead-letter entry.",
            "The dead-letter entry includes field name and validation reason.",
            "Filtering by pipeline id returns only that pipeline's rejected records.",
        ),
        ("Lost rejected records reduce trust in pipeline data.",),
        ("pipeline", "observability", "multi_tenant"),
    ),
    _scenario(
        "pipeline-pause-resume-offset",
        "Data pipelines",
        "Pause and resume pipelines without losing offsets.",
        (
            "Pausing a pipeline must stop new extraction jobs after the current checkpoint.",
            "Resuming a pipeline must continue from the last committed offset.",
            "Pause and resume actions must be visible in pipeline history.",
        ),
        (
            "Should in-flight extraction jobs finish or stop immediately on pause?",
            "Who can resume a paused production pipeline?",
        ),
        ("Pipeline workers commit offsets after successful batches.",),
        (
            "Pausing a pipeline stops later extraction jobs.",
            "Resuming a pipeline continues from the last committed offset.",
            "Pipeline history shows pause and resume actor ids.",
        ),
        ("Offset mistakes can duplicate or drop data.",),
        ("pipeline", "audit", "edge"),
    ),
    _scenario(
        "pipeline-pii-classification",
        "Data pipelines",
        "Detect personal data in fields marked non-PII.",
        (
            "Pipeline activation must scan sample fields marked non-PII for personal data patterns.",
            "Detected personal data must block activation or require an approval record.",
            "Approval records must include approver id, field name, and justification.",
        ),
        (
            "Which personal data patterns should block activation automatically?",
            "Who may approve intentional personal data fields?",
        ),
        ("Pipeline field mappings include intended data classification.",),
        (
            "A field marked non-PII with email-like values triggers a finding.",
            "Activation is blocked until the finding is resolved or approved.",
            "Approved findings record approver id and justification.",
        ),
        ("PII misclassification can violate customer data policy.",),
        ("pipeline", "security", "audit"),
    ),
    _scenario(
        "cli-deploy-preflight",
        "CLI tools",
        "Add a deployment preflight CLI command.",
        (
            "The preflight command must check required environment variables.",
            "The command must test database connectivity without applying migrations.",
            "CI mode must emit JSON with check name, status, and message.",
        ),
        (
            "Which checks are required for each deployment environment?",
            "Should warning checks fail CI or only appear in output?",
        ),
        ("The CLI can reuse existing service configuration loading.",),
        (
            "Missing required environment variables are all reported in one run.",
            "Database connectivity failure exits non-zero without running migrations.",
            "CI mode emits valid JSON for every preflight check.",
        ),
        ("A preflight command that mutates state can damage deployments.",),
        ("cli", "devops", "edge"),
    ),
    _scenario(
        "cli-secret-scan",
        "CLI tools",
        "Detect accidental secrets in local configuration files.",
        (
            "The secret scan command must inspect configured project files.",
            "Findings must show file path, line number, and secret type.",
            "The command must never print the full suspected secret value.",
        ),
        (
            "Which file patterns should the secret scanner include by default?",
            "How should developers suppress known false positives?",
        ),
        ("The CLI runs on a developer machine before commit.",),
        (
            "A file containing an API token produces a secret finding.",
            "The finding includes file path and line number.",
            "The command output masks the suspected secret value.",
        ),
        ("Printing secrets in CLI output can worsen exposure.",),
        ("cli", "security"),
    ),
    _scenario(
        "cli-migration-plan",
        "CLI tools",
        "Show pending migrations without applying them.",
        (
            "The migration plan command must list pending migration ids and descriptions.",
            "The command must not run migration upgrade operations.",
            "JSON output must include current revision and target revision.",
        ),
        (
            "Should optional migrations appear separately from required migrations?",
            "Should the command connect to read replicas in production?",
        ),
        ("Migration metadata can be read without schema changes.",),
        (
            "The migration plan command lists pending migration ids.",
            "Running the command leaves the database revision unchanged.",
            "JSON output includes current revision and target revision.",
        ),
        ("Unsafe migration commands can change production state unexpectedly.",),
        ("cli", "devops"),
    ),
    _scenario(
        "cli-job-retry",
        "CLI tools",
        "Retry failed background jobs from the CLI.",
        (
            "The retry command must accept job id and retry reason.",
            "Only failed jobs may be retried from the CLI.",
            "Retry attempts must record actor, reason, and original job id.",
        ),
        (
            "Who can run job retries in production?",
            "Should retry reason use free text or predefined values?",
        ),
        ("Failed jobs remain available in the job store.",),
        (
            "Retrying a failed job creates a retry attempt.",
            "Retrying a successful job returns 409.",
            "The retry audit record includes actor and reason.",
        ),
        ("Manual retries can duplicate side effects if jobs are not idempotent.",),
        ("cli", "audit", "edge"),
    ),
    _scenario(
        "cli-profile-switch",
        "CLI tools",
        "Switch CLI profiles without exposing stored tokens.",
        (
            "The profile switch command must update the active profile name.",
            "The command output must not print access tokens or refresh tokens.",
            "The active profile must be shown in later status commands.",
        ),
        (
            "Where should CLI profiles be stored on Windows?",
            "Should switching profiles clear cached API clients?",
        ),
        ("Profiles already exist in the CLI configuration file.",),
        (
            "Switching to an existing profile updates the active profile.",
            "Profile switch output does not include token values.",
            "The status command shows the new active profile name.",
        ),
        ("Profile mistakes can point CLI commands at the wrong environment.",),
        ("cli", "security"),
    ),
    _scenario(
        "devops-migration-gate",
        "DevOps checks",
        "Block production deploys when required migrations are pending.",
        (
            "Production deploy checks must compare applied and expected migration revisions.",
            "Deployments with pending required migrations must stop before traffic shift.",
            "The deploy check output must list pending migration ids.",
        ),
        (
            "Which environments count as production for migration gates?",
            "Who can approve an emergency migration-gate override?",
        ),
        ("Traffic shift happens after release checks complete.",),
        (
            "A production deploy with pending migrations is blocked.",
            "The blocked deploy output lists pending migration ids.",
            "A production deploy with all migrations applied can continue.",
        ),
        ("Deploying code before schema changes can break runtime requests.",),
        ("devops", "edge"),
    ),
    _scenario(
        "devops-health-gate",
        "DevOps checks",
        "Require passing health checks before traffic shift.",
        (
            "Traffic shift must wait for critical health checks to pass.",
            "Failed health checks must show service name, check name, and last error.",
            "Health-check results must be stored with release id and environment.",
        ),
        (
            "What timeout should each health check use?",
            "Should non-critical health checks block traffic shift?",
        ),
        ("Deployment orchestration can pause before traffic shift.",),
        (
            "A release with failing critical health checks does not receive production traffic.",
            "The health gate output identifies the failing service.",
            "Passing critical health checks allow traffic shift to continue.",
        ),
        ("Weak health gates can extend production outages.",),
        ("devops", "observability", "edge"),
    ),
    _scenario(
        "devops-canary-metrics",
        "DevOps checks",
        "Evaluate canary metrics before full rollout.",
        (
            "Canary rollout must measure error rate and p95 latency for the new version.",
            "Full rollout must stop when canary metrics exceed configured thresholds.",
            "Canary evaluation results must include release id and metric window.",
        ),
        (
            "What error-rate threshold should block full rollout?",
            "How long should the canary metric window be?",
        ),
        ("The platform can route a small traffic percentage to a canary version.",),
        (
            "A healthy canary allows rollout to proceed.",
            "A canary with high error rate blocks full rollout.",
            "The evaluation result records release id and metric window.",
        ),
        ("Weak canary checks can amplify regressions.",),
        ("devops", "observability"),
    ),
    _scenario(
        "devops-artifact-signature",
        "DevOps checks",
        "Verify deployment artifact signatures.",
        (
            "Deployment must reject artifacts without a trusted signature.",
            "Signature verification must record artifact digest and signer identity.",
            "Failed signature verification must stop the release.",
        ),
        (
            "Which signing keys are trusted for production releases?",
            "How should expired signing keys be handled for rollback artifacts?",
        ),
        ("Build artifacts include a digest and detached signature.",),
        (
            "A signed artifact from a trusted key can deploy.",
            "An unsigned artifact is rejected.",
            "Signature verification logs artifact digest and signer identity.",
        ),
        ("Signature gaps can allow supply-chain compromise.",),
        ("devops", "security"),
    ),
    _scenario(
        "devops-worker-capacity",
        "DevOps checks",
        "Check worker capacity before enabling queue-heavy features.",
        (
            "Feature rollout must compare expected job volume to available worker capacity.",
            "Rollout must stop when projected queue time exceeds the configured limit.",
            "Capacity check output must show worker pool, expected jobs, and projected queue time.",
        ),
        (
            "What projected queue time is acceptable for each worker pool?",
            "Should operators be allowed to continue after acknowledging capacity risk?",
        ),
        ("Worker pools expose current concurrency and queue depth.",),
        (
            "A rollout with enough worker capacity can continue.",
            "A rollout with projected queue time above limit is blocked.",
            "The capacity report includes worker pool and projected queue time.",
        ),
        ("Capacity mistakes can delay background processing for customers.",),
        ("devops", "observability", "edge"),
    ),
)


def _section_items(response: str, section: str) -> list[str]:
    items = []
    current: str | None = None
    for line in response.splitlines():
        stripped = line.strip()
        if stripped in {
            "REQUIREMENTS",
            "AMBIGUITIES",
            "ASSUMPTIONS",
            "ACCEPTANCE CRITERIA",
            "RISKS",
            "CONFIDENCE",
        }:
            current = stripped
            continue
        if current == section and stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def normalize_for_fingerprint(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"\s*\.?\s*\bvariant\s+\d+\b\.?", " ", normalized)
    normalized = re.sub(r"\bsynthetic_index\b\s*[:=]\s*\d+", " ", normalized)
    normalized = re.sub(r"\bears_\d{5}_[a-f0-9]{16}\b", " ", normalized)
    normalized = re.sub(r"\bcandidate_id\b\s*[:=]\s*[\w-]+", " ", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _dedupe_items(items: list[str]) -> str:
    return "\n".join(normalize_for_fingerprint(item) for item in items)


def content_fingerprint(candidate_task: str, candidate_response: str) -> str:
    payload = "\n".join(
        (
            normalize_for_fingerprint(candidate_task),
            _dedupe_items(_section_items(candidate_response, "REQUIREMENTS")),
            _dedupe_items(_section_items(candidate_response, "ACCEPTANCE CRITERIA")),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def section_pair_fingerprint(candidate_response: str) -> str:
    payload = "\n".join(
        (
            _dedupe_items(_section_items(candidate_response, "REQUIREMENTS")),
            _dedupe_items(_section_items(candidate_response, "ACCEPTANCE CRITERIA")),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def quality_gate_rejections(row: dict) -> list[str]:
    text = f"{row['candidate_task']}\n{row['candidate_response']}".lower()
    return [phrase for phrase in BANNED_QUALITY_PHRASES if phrase in text]


def generate_synthetic_candidates(count: int) -> list[dict]:
    if count < 0:
        raise ValueError("count must be non-negative")
    rows = []
    for index, scenario in enumerate(SCENARIO_BANK[:count]):
        response = response_from_parts(
            requirements=list(scenario.requirements),
            ambiguities=list(scenario.ambiguities),
            assumptions=list(scenario.assumptions),
            acceptance_criteria=list(scenario.acceptance),
            risks=list(scenario.risks),
            confidence=scenario.confidence,
        )
        candidate = CandidateRow(
            source=SYNTHETIC_SOURCE,
            license=SYNTHETIC_LICENSE,
            url=SYNTHETIC_URL,
            raw_input=scenario.task,
            raw_output=json.dumps(
                {
                    "domain": scenario.domain,
                    "scenario_id": scenario.scenario_id,
                    "tags": sorted(scenario.tags),
                    "synthetic_index": index,
                },
                sort_keys=True,
            ),
            candidate_task=scenario.task,
            candidate_response=response,
            quality_score=94,
            risk_flags=["synthetic", "fully_authored", *sorted(scenario.tags)],
        )
        row = {
            "candidate_id": f"ears_{index:05d}_{candidate.stable_id()}",
            "source": candidate.source,
            "license": candidate.license,
            "url": candidate.url,
            "raw_input": candidate.raw_input,
            "raw_output": candidate.raw_output,
            "candidate_task": candidate.candidate_task,
            "candidate_response": candidate.candidate_response,
            "quality_score": candidate.quality_score,
            "risk_flags": candidate.risk_flags,
            "domain": scenario.domain,
            "scenario_id": scenario.scenario_id,
            "content_fingerprint": content_fingerprint(
                candidate.candidate_task, candidate.candidate_response
            ),
            "section_fingerprint": section_pair_fingerprint(candidate.candidate_response),
        }
        if not quality_gate_rejections(row):
            rows.append(row)
    return rows


def quality_summary(rows: list[dict]) -> dict[str, int | dict[str, int]]:
    domain_counts = Counter(str(row.get("domain", "unknown")) for row in rows)
    tag_counts: Counter[str] = Counter()
    for row in rows:
        tag_counts.update(row["risk_flags"])
    return {
        "count": len(rows),
        "security_or_multi_tenant": sum(
            bool({"security", "multi_tenant"} & set(row["risk_flags"])) for row in rows
        ),
        "observability_or_audit": sum(
            bool({"observability", "audit"} & set(row["risk_flags"])) for row in rows
        ),
        "failure_or_edge": sum("edge" in row["risk_flags"] for row in rows),
        "domains": dict(sorted(domain_counts.items())),
        "tags": dict(sorted(tag_counts.items())),
    }


def _markdown_for_candidate(row: dict) -> str:
    flags = ", ".join(row.get("risk_flags") or [])
    return f"""---
candidate_id: {row["candidate_id"]}
source: {row["source"]}
license: {row["license"]}
quality_score: {row["quality_score"]}
decision: pending
scenario_id: {row["scenario_id"]}
content_fingerprint: {row["content_fingerprint"]}
section_fingerprint: {row["section_fingerprint"]}
---

# {row["source"]} / {row["candidate_id"]}

License: {row["license"]}

URL: {row["url"]}

Quality score: {row["quality_score"]}

Risk flags: {flags or "none"}

Domain: {row.get("domain", "unknown")}

Scenario ID: {row.get("scenario_id", "unknown")}

## Candidate Task

{row["candidate_task"]}

## Candidate Response

```text
{row["candidate_response"]}
```

## Raw Input

```text
{row["raw_input"]}
```

## Raw Output

```text
{row["raw_output"]}
```

## Review Checklist

- Original synthetic material; no external copyrighted text.
- Requirements are concrete and scoped to the task.
- Ambiguities capture missing product decisions.
- Acceptance criteria are testable.
- Risks are domain-specific.
"""


TASK_BLOCK = re.compile(
    r"## Candidate Task\s+(?P<task>.*?)\s+## Candidate Response\s+```text\s*(?P<response>.*?)\s*```",
    re.DOTALL,
)
SCENARIO_ID_LINE = re.compile(r"^scenario_id:\s*(?P<scenario_id>[\w-]+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ExistingReviewSignatures:
    content_fingerprints: set[str]
    section_fingerprints: set[str]
    scenario_counts: Counter[str]


def _fingerprint_from_markdown(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    match = TASK_BLOCK.search(text)
    if not match:
        return None
    return content_fingerprint(match.group("task").strip(), match.group("response").strip())


def _section_fingerprint_from_markdown(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    match = TASK_BLOCK.search(text)
    if not match:
        return None
    return section_pair_fingerprint(match.group("response").strip())


def _scenario_id_from_markdown(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    match = SCENARIO_ID_LINE.search(text)
    if match:
        return match.group("scenario_id")
    return None


def existing_review_signatures(data_root: Path) -> ExistingReviewSignatures:
    review_root = resolve_public_path("review", data_root)
    content_fingerprints = set()
    section_fingerprints = set()
    scenario_counts: Counter[str] = Counter()
    for state in REVIEW_STATES:
        state_dir = review_root / state
        if not state_dir.exists():
            continue
        for path in state_dir.glob("*.md"):
            fingerprint = _fingerprint_from_markdown(path)
            if fingerprint:
                content_fingerprints.add(fingerprint)
            section_fingerprint = _section_fingerprint_from_markdown(path)
            if section_fingerprint:
                section_fingerprints.add(section_fingerprint)
            scenario_id = _scenario_id_from_markdown(path)
            if scenario_id:
                scenario_counts[scenario_id] += 1
    return ExistingReviewSignatures(
        content_fingerprints=content_fingerprints,
        section_fingerprints=section_fingerprints,
        scenario_counts=scenario_counts,
    )


def write_pending_review(
    rows: list[dict],
    data_root: Path,
    *,
    dedupe_existing: bool = True,
    allow_duplicates: bool = False,
    max_per_scenario: int = 1,
) -> GenerationReport:
    pending_dir = ensure_dir(resolve_public_path("review/pending", data_root))
    ensure_dir(resolve_public_path("review/approved", data_root))
    ensure_dir(resolve_public_path("review/rejected", data_root))
    signatures = (
        existing_review_signatures(data_root)
        if dedupe_existing
        else ExistingReviewSignatures(set(), set(), Counter())
    )
    seen_content = set(signatures.content_fingerprints)
    seen_sections = set(signatures.section_fingerprints)
    scenario_counts = Counter(signatures.scenario_counts)
    written = []
    skipped_duplicates = 0
    skipped_max_per_scenario = 0
    for row in rows:
        scenario_id = str(row.get("scenario_id") or "unknown")
        fingerprint = row.get("content_fingerprint") or content_fingerprint(
            row["candidate_task"], row["candidate_response"]
        )
        section_fingerprint = row.get("section_fingerprint") or section_pair_fingerprint(
            row["candidate_response"]
        )
        if (
            not allow_duplicates
            and max_per_scenario > 0
            and scenario_counts[scenario_id] >= max_per_scenario
        ):
            skipped_max_per_scenario += 1
            continue
        if not allow_duplicates and (
            fingerprint in seen_content or section_fingerprint in seen_sections
        ):
            skipped_duplicates += 1
            continue
        seen_content.add(fingerprint)
        seen_sections.add(section_fingerprint)
        scenario_counts[scenario_id] += 1
        path = pending_dir / f"090_{row['source']}_{row['candidate_id']}.md"
        path.write_text(_markdown_for_candidate(row), encoding="utf-8", newline="\n")
        written.append(path)
    summary = quality_summary(rows)
    generated_scenario_counts = Counter(str(row.get("scenario_id") or "unknown") for row in rows)
    repeated_scenarios = tuple(
        (scenario_id, count)
        for scenario_id, count in generated_scenario_counts.most_common(10)
        if count > 1
    )
    return GenerationReport(
        generated=len(rows),
        skipped_duplicates=skipped_duplicates,
        skipped_max_per_scenario=skipped_max_per_scenario,
        written=len(written),
        written_paths=tuple(written),
        domain_counts=dict(summary["domains"]),
        tag_counts=dict(summary["tags"]),
        unique_scenario_count=len(generated_scenario_counts),
        repeated_scenario_ids=repeated_scenarios,
    )


def generate_to_pending(
    count: int,
    data_root: Path,
    *,
    dedupe_existing: bool = True,
    allow_duplicates: bool = False,
    max_per_scenario: int = 1,
) -> GenerationReport:
    rows = generate_synthetic_candidates(count)
    return write_pending_review(
        rows,
        data_root,
        dedupe_existing=dedupe_existing,
        allow_duplicates=allow_duplicates,
        max_per_scenario=max_per_scenario,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate authored synthetic Product Agent examples.")
    add_common_args(parser)
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--max-per-scenario", type=int, default=1)
    parser.add_argument(
        "--dedupe-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip candidates equivalent to existing pending, approved, or rejected review files.",
    )
    parser.add_argument(
        "--allow-duplicates",
        action="store_true",
        help="Debug only: bypass duplicate checks, including duplicates in the generated batch.",
    )
    args = parser.parse_args()
    rows = generate_synthetic_candidates(args.count)
    report = write_pending_review(
        rows,
        args.data_root,
        dedupe_existing=args.dedupe_existing,
        allow_duplicates=args.allow_duplicates,
        max_per_scenario=args.max_per_scenario,
    )
    print(
        f"Generated requested count {args.count}; "
        f"Generated {report.generated}; "
        f"Written {report.written}; "
        f"Skipped duplicate count {report.skipped_duplicates}; "
        f"Skipped max_per_scenario count {report.skipped_max_per_scenario}; "
        f"Unique scenario count {report.unique_scenario_count}"
    )
    if report.repeated_scenario_ids:
        print("Top repeated scenario ids:")
        for scenario_id, count in report.repeated_scenario_ids:
            print(f"- {scenario_id}: {count}")
    print("Coverage by domain:")
    for domain, count in sorted(report.domain_counts.items()):
        print(f"- {domain}: {count}")
    print("Coverage by tags:")
    for tag, count in sorted(report.tag_counts.items()):
        print(f"- {tag}: {count}")


if __name__ == "__main__":
    main()

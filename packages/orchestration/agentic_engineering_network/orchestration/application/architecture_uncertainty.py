from __future__ import annotations


def get_architecture_uncertainty_review() -> dict[str, object]:
    return {
        "architect_signoff_required": True,
        "architecture_decision_records": [
            "docs/adr/0001-clean-architecture-boundaries.md",
            "docs/adr/0002-senior-gates-and-scorecards.md",
        ],
        "tradeoff_analysis": [
            {"decision": "Docker-first local runtime", "benefit": "Reproducible sandbox", "cost": "Requires Docker Desktop and WSL2"},
            {"decision": "Mock-first providers", "benefit": "Safe local operation", "cost": "Real integration behavior must be validated later"},
            {"decision": "Bounded correction loop", "benefit": "Controls resources", "cost": "Cannot promise infinite autonomous repair"},
        ],
        "alternative_architecture_comparison": [
            {"option": "Local Docker monolith", "fit": "best for privacy and local generation", "risk": "host resource pressure"},
            {"option": "Cloud control plane", "fit": "best for teams and remote workers", "risk": "secrets, cost, and tenancy complexity"},
            {"option": "Desktop-only runtime", "fit": "simple UX", "risk": "weaker sandbox and dependency isolation"},
        ],
        "domain_fit_questionnaire": [
            "Does the domain require real-time collaboration?",
            "Does it process regulated personal or financial data?",
            "Does it need offline operation?",
            "What are peak concurrency and data-volume assumptions?",
            "Which third-party systems are business-critical?",
        ],
        "scalability_assumptions": [
            "Generated SaaS starts as small-team B2B unless specified otherwise.",
            "PostgreSQL remains primary transactional storage.",
            "Background workers should be added for long-running jobs.",
        ],
        "cost_assumptions": [
            "Local model inference costs hardware time rather than API tokens.",
            "Cloud deployment costs depend on chosen provider, database tier, and model usage.",
            "Support/admin workflows create operational cost and must be budgeted.",
        ],
        "failure_mode_analysis": [
            "Docker unavailable",
            "Model returns invalid diff",
            "Provider credentials missing",
            "Migration failure",
            "Webhook replay",
            "Tenant context missing",
            "GPU/CPU resource exhaustion",
        ],
    }

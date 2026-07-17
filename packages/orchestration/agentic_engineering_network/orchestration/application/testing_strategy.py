from __future__ import annotations


def get_test_strategy() -> dict[str, object]:
    return {
        "coverage_targets": {
            "backend_unit": 80,
            "backend_integration": 70,
            "frontend_unit": 70,
            "contract": 75,
            "security": 100,
            "smoke": 100,
        },
        "suites": [
            {"name": "unit", "tools": ["pytest", "vitest"], "retry": "never for deterministic failures"},
            {"name": "integration", "tools": ["pytest", "docker compose"], "retry": "once for environment startup only"},
            {"name": "contract", "tools": ["OpenAPI validation", "schema checks"], "retry": "never"},
            {"name": "e2e", "tools": ["Playwright"], "retry": "once for known browser flake"},
            {"name": "security", "tools": ["secret scan", "dependency audit", "auth/RBAC matrix"], "retry": "never"},
            {"name": "smoke", "tools": ["healthz", "readinessz", "docker compose up"], "retry": "bounded startup wait"},
            {"name": "regression", "tools": ["saved bug fixtures"], "retry": "never"},
        ],
        "failure_analysis": [
            "Classify as code, dependency, environment, flaky, or requirement ambiguity.",
            "Read the shortest failing command output and preserve raw logs.",
            "Patch only with validated unified diffs.",
            "Escalate when the same failure class repeats after max attempts.",
        ],
        "dashboard_metrics": [
            "last run status",
            "suite pass/fail",
            "coverage target",
            "failure class",
            "retry history",
            "human escalation status",
        ],
    }

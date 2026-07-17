"""Base model interfaces and deterministic mock model."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseModelClient(ABC):
    """Common text/chat interface used by all pipeline agents."""

    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        """Generate text from a single formatted prompt."""

    @abstractmethod
    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        """Generate text from a chat-style message list."""

    def diagnostics(self) -> dict[str, object]:
        """Return optional model backend diagnostics for logs and run summaries."""

        return {}


class DeterministicMockModel(BaseModelClient):
    """Small deterministic model used for smoke tests and CI."""

    def __init__(self, name: str, force_changes_required: bool = False) -> None:
        self.name = name
        self.force_changes_required = force_changes_required

    def generate_text(self, prompt: str) -> str:
        lower_prompt = prompt.lower()
        if "you are the final reviewer agent" in lower_prompt:
            decision = (
                "Rejected"
                if "ready for re-review\nno" in lower_prompt
                or "approval status\nneeds fixes" in lower_prompt
                else "Approved"
            )
            if decision == "Rejected":
                return (
                    "FINAL ASSESSMENT\n"
                    "* The artifact chain still has unresolved issues in mock mode.\n\n"
                    "REQUIREMENTS STATUS\n"
                    "* Requirements require follow-up before approval.\n\n"
                    "ARCHITECTURE STATUS\n"
                    "* Architecture requires follow-up before approval.\n\n"
                    "IMPLEMENTATION STATUS\n"
                    "* Implementation planning requires follow-up before approval.\n\n"
                    "TEST STATUS\n"
                    "* Test coverage requires follow-up before approval.\n\n"
                    "SECURITY STATUS\n"
                    "* Security review requires follow-up before approval.\n\n"
                    "REVIEW STATUS\n"
                    "* Reviewer findings remain unresolved.\n\n"
                    "FIX STATUS\n"
                    "* Fix plan is not ready for re-review.\n\n"
                    "FINAL DECISION\n"
                    "Rejected\n\n"
                    "REASONING\n"
                    "* Blocking uncertainty remains across the artifact chain.\n\n"
                    "CONFIDENCE\n"
                    "High"
                )
            return (
                "FINAL ASSESSMENT\n"
                "* The generated artifacts are internally consistent.\n\n"
                "REQUIREMENTS STATUS\n"
                "* Requirements are sufficiently covered.\n\n"
                "ARCHITECTURE STATUS\n"
                "* Architecture aligns with requirements.\n\n"
                "IMPLEMENTATION STATUS\n"
                "* Implementation plan aligns with architecture.\n\n"
                "TEST STATUS\n"
                "* Test coverage addresses major acceptance criteria.\n\n"
                "SECURITY STATUS\n"
                "* Security concerns have been reviewed.\n\n"
                "REVIEW STATUS\n"
                "* Reviewer findings have been addressed.\n\n"
                "FIX STATUS\n"
                "* No significant unresolved fixes remain.\n\n"
                "FINAL DECISION\n"
                "Approved\n\n"
                "REASONING\n"
                "* No blocking inconsistencies remain across the artifact chain.\n\n"
                "CONFIDENCE\n"
                "High"
            )

        if "you are the reviewer agent" in lower_prompt:
            approval_status = "Needs Fixes" if self.force_changes_required else "Approved"
            return (
                "CONSISTENCY CHECK\n"
                "* The upstream artifacts are internally consistent in mock mode.\n\n"
                "REQUIREMENT GAPS\n"
                "* No requirement gaps are identified in mock mode.\n\n"
                "ARCHITECTURE GAPS\n"
                "* No architecture gaps are identified in mock mode.\n\n"
                "IMPLEMENTATION RISKS\n"
                "* Implementation should remain scoped to the planned files.\n\n"
                "TEST COVERAGE GAPS\n"
                "* Add focused regression coverage for the requested behavior.\n\n"
                "SECURITY GAPS\n"
                "* Preserve generic user-facing feedback for sensitive flows.\n\n"
                "RECOMMENDATIONS\n"
                "* Proceed with the planned implementation after reviewing the gaps.\n\n"
                "APPROVAL STATUS\n"
                f"{approval_status}\n\n"
                "CONFIDENCE\n"
                "High"
            )

        if (
            "output exactly:" in lower_prompt
            and "status: approved or changes required" in lower_prompt
        ):
            if "final notes" in lower_prompt:
                return (
                    "STATUS: APPROVED\n"
                    "REMAINING BLOCKING ISSUES:\n"
                    "- None in mock mode.\n"
                    "FINAL NOTES:\n"
                    "- Mock final review completed."
                )
            if self.force_changes_required:
                return (
                    "STATUS: CHANGES REQUIRED\n"
                    "BLOCKING ISSUES:\n"
                    "- Mock reviewer requires a missing edge-case test.\n"
                    "NON-BLOCKING ISSUES:\n"
                    "- None.\n"
                    "MISSING TESTS:\n"
                    "- Add tenant isolation regression test.\n"
                    "REQUIRED FIX PLAN:\n"
                    "- Add the missing test and update implementation notes."
                )
            return (
                "STATUS: APPROVED\n"
                "BLOCKING ISSUES:\n"
                "- None.\n"
                "NON-BLOCKING ISSUES:\n"
                "- None.\n"
                "MISSING TESTS:\n"
                "- None.\n"
                "REQUIRED FIX PLAN:\n"
                "- No fix required."
            )

        if "product / requirements" in lower_prompt:
            return (
                "REQUIREMENTS\n"
                "- Build the requested software capability.\n\n"
                "AMBIGUITIES\n"
                "- Mock mode does not ask follow-up questions.\n\n"
                "ASSUMPTIONS\n"
                "- Use local, testable defaults.\n\n"
                "ACCEPTANCE CRITERIA\n"
                "- Code, tests, review, and final approval artifacts exist.\n\n"
                "RISKS\n"
                "- Real model behavior is not exercised in mock mode.\n\n"
                "CONFIDENCE\n"
                "High"
            )

        if "you are the code agent" in lower_prompt:
            return (
                "FILES TO MODIFY\n"
                "- Candidate: application entrypoint or route handler.\n\n"
                "NEW FILES\n"
                "- Candidate: focused tests for the requested behavior.\n\n"
                "CODE CHANGES\n"
                "- Add the smallest implementation that satisfies the architecture plan.\n"
                "- Keep existing behavior available.\n\n"
                "TESTS TO ADD\n"
                "- Add happy-path and edge-case coverage for the requested behavior.\n\n"
                "RATIONALE\n"
                "- Preserve Product Agent acceptance criteria with minimal changes.\n\n"
                "CONFIDENCE\n"
                "High"
            )

        if "solution architect" in lower_prompt or "architect agent" in lower_prompt:
            return (
                "TECHNICAL SUMMARY\n"
                "- Use the existing application structure and keep the implementation small.\n\n"
                "AFFECTED AREAS\n"
                "- API handler and focused tests.\n\n"
                "FILES TO INSPECT\n"
                "- app/main.py\n"
                "- tests/test_main.py\n\n"
                "IMPLEMENTATION PLAN\n"
                "- Inspect the target module before editing.\n"
                "- Add the smallest route or service change that satisfies the requirements.\n"
                "- Keep behavior covered by tests before handing off for review.\n\n"
                "DATA OR STATE CHANGES\n"
                "- No persistent model required for mock task.\n\n"
                "TEST STRATEGY\n"
                "- Unit and integration smoke tests.\n\n"
                "RISKS\n"
                "- Real model behavior is not exercised in mock mode.\n\n"
                "HANDOFF TO CODE AGENT\n"
                "- Implement only the listed files unless inspection shows a nearby pattern.\n"
                "- Preserve the Product Agent acceptance criteria in code and tests.\n\n"
                "CONFIDENCE\n"
                "High"
            )

        if "test engineer" in lower_prompt:
            return (
                "TEST SCENARIOS\n"
                "- Verify the requested behavior succeeds for the primary user flow.\n"
                "- Verify invalid or excessive user actions receive clear feedback.\n\n"
                "TEST CASES\n"
                "- User completes the intended flow successfully.\n"
                "- User input outside expected bounds is handled clearly.\n\n"
                "EDGE CASES\n"
                "- Repeated attempts occur close together.\n"
                "- The flow is interrupted and retried.\n\n"
                "REGRESSION TESTS\n"
                "- Existing behavior around the changed area remains unchanged.\n\n"
                "AUTOMATION STRATEGY\n"
                "- Add behavior-level automated coverage for success and failure flows.\n\n"
                "RISKS\n"
                "- Missing negative-path coverage may allow regressions.\n\n"
                "CONFIDENCE\n"
                "High"
            )

        if "security agent" in lower_prompt:
            return (
                "SECURITY FINDINGS\n"
                "- The planned change should preserve existing authorization and input validation behavior.\n\n"
                "THREATS\n"
                "- Attackers may attempt to abuse the new behavior at high volume.\n\n"
                "ABUSE SCENARIOS\n"
                "- A malicious actor repeatedly exercises the new flow to disrupt normal users.\n\n"
                "SECURITY TESTS\n"
                "- Verify the new behavior fails safely when limits or validation conditions are reached.\n\n"
                "MITIGATIONS\n"
                "- Use generic user-facing feedback where sensitive state may be inferred.\n\n"
                "RESIDUAL RISKS\n"
                "- Missing telemetry may reduce the ability to detect abuse.\n\n"
                "CONFIDENCE\n"
                "High"
            )

        if "fixer agent" in lower_prompt:
            ready = "No" if "approval status\nneeds fixes" in lower_prompt else "Yes"
            if ready == "Yes":
                return (
                    "FIX SUMMARY\n"
                    "* No significant fixes are required based on the current review.\n\n"
                    "REQUIREMENT FIXES\n"
                    "* No requirement changes are required.\n\n"
                    "ARCHITECTURE FIXES\n"
                    "* No architecture changes are required.\n\n"
                    "IMPLEMENTATION FIXES\n"
                    "* Continue with planned implementation.\n\n"
                    "TEST FIXES\n"
                    "* Maintain planned test coverage.\n\n"
                    "SECURITY FIXES\n"
                    "* Maintain planned security controls.\n\n"
                    "PRIORITY ORDER\n"
                    "* Proceed with implementation review.\n\n"
                    "READY FOR RE-REVIEW\n"
                    "Yes\n\n"
                    "CONFIDENCE\n"
                    "High"
                )
            return (
                "FIX SUMMARY\n"
                "* Reviewer findings require corrective planning before re-review.\n\n"
                "REQUIREMENT FIXES\n"
                "* Reconcile reviewer-noted requirement gaps with Product Agent intent.\n\n"
                "ARCHITECTURE FIXES\n"
                "* Align architecture notes with reviewer-noted gaps before implementation.\n\n"
                "IMPLEMENTATION FIXES\n"
                "* Scope implementation corrections to reviewer findings only.\n\n"
                "TEST FIXES\n"
                "* Add or adjust tests for reviewer-noted coverage gaps.\n\n"
                "SECURITY FIXES\n"
                "* Address reviewer-noted security gaps with minimal corrective actions.\n\n"
                "PRIORITY ORDER\n"
                "* Resolve requirement gaps, then architecture, implementation, test, and security gaps.\n\n"
                "READY FOR RE-REVIEW\n"
                "No\n\n"
                "CONFIDENCE\n"
                "High"
            )

        return (
            "IMPLEMENTATION\n"
            "```python\n"
            "from fastapi import FastAPI\n\n"
            "app = FastAPI()\n\n"
            "@app.get('/hello')\n"
            "async def hello() -> dict[str, str]:\n"
            "    return {'message': 'hello'}\n"
            "```\n\n"
            "FILES\n"
            "- app/main.py"
        )

    def generate_chat(self, messages: list[dict[str, str]]) -> str:
        prompt = "\n".join(f"{message['role']}: {message['content']}" for message in messages)
        return self.generate_text(prompt)

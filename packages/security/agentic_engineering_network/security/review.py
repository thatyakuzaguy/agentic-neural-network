from __future__ import annotations

from dataclasses import asdict, dataclass

from agentic_engineering_network.security.secrets import SecretFinding, SecretScanner


@dataclass(frozen=True)
class SecurityReview:
    passed: bool
    findings: list[SecretFinding]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "findings": [asdict(finding) for finding in self.findings],
            "notes": list(self.notes),
        }


class SecurityReviewer:
    def __init__(self) -> None:
        self.scanner = SecretScanner()

    def review_generated_files(self, files: dict[str, str]) -> SecurityReview:
        findings: list[SecretFinding] = []
        for path, content in files.items():
            findings.extend(self.scanner.scan_text(path, content))
        notes = (
            "Shell execution must be approval-gated and run in Docker where possible.",
            "Secrets belong in environment variables or a local secret store, never source files.",
            "Authentication code must be reviewed before deployment.",
        )
        return SecurityReview(passed=not findings, findings=findings, notes=notes)


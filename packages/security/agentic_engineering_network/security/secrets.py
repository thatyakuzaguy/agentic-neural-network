from __future__ import annotations

import re
from dataclasses import dataclass


SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{16,})"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


@dataclass(frozen=True)
class SecretFinding:
    path: str
    line: int
    pattern: str


class SecretScanner:
    def scan_text(self, path: str, content: str) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        for index, line in enumerate(content.splitlines(), start=1):
            for pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(SecretFinding(path=path, line=index, pattern=pattern.pattern))
        return findings


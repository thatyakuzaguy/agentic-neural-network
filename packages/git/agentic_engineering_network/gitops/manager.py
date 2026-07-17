from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitStatus:
    branch: str
    short_status: str


class GitManager:
    def __init__(self, root: Path) -> None:
        self.root = root

    def status(self) -> GitStatus:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=self.root,
            text=True,
        ).strip()
        short_status = subprocess.check_output(
            ["git", "status", "--short"],
            cwd=self.root,
            text=True,
        ).strip()
        return GitStatus(branch=branch or "main", short_status=short_status)


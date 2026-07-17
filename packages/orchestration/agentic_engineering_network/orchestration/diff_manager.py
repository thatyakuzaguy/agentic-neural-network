from __future__ import annotations

import difflib
from pathlib import Path


class DiffManager:
    def build_diff(self, target: Path, proposed_content: str) -> str:
        safe_target = target.resolve()
        old_content = safe_target.read_text(encoding="utf-8") if safe_target.exists() else ""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = proposed_content.splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=str(safe_target),
                tofile=f"{safe_target} (proposed)",
            )
        )

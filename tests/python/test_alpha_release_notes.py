from __future__ import annotations

from pathlib import Path


def test_alpha_release_notes_cover_user_facing_topics() -> None:
    text = Path("D:/AgenticEngineeringNetwork/README_ALPHA_RELEASE_NOTES.md").read_text(encoding="utf-8")

    for phrase in (
        "What ANN Can Do",
        "What ANN Cannot Do Yet",
        "Desktop",
        "Runtime",
        "Skills",
        "Project Builder",
        "Self Healing",
        "Consensus",
        "FAST",
        "POWERFUL",
        "Safe Mode",
        "Known Blockers",
    ):
        assert phrase in text

"""Navigation primitives for ANN Desktop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - UI smoke covers this when Qt is available.
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QListWidget, QListWidgetItem

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QSize = None
    QListWidget = None
    QListWidgetItem = None
    PYSIDE6_AVAILABLE = False


@dataclass(frozen=True)
class NavigationItem:
    """One desktop navigation item."""

    label: str
    view_id: str


NAV_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem("Dashboard", "dashboard"),
    NavigationItem("Engineering Pipeline", "engineering_pipeline"),
    NavigationItem("First Run", "first_run"),
    NavigationItem("Chat", "chat"),
    NavigationItem("Projects", "projects"),
    NavigationItem("Project Creation", "project_creation"),
    NavigationItem("Project Scaffold", "project_scaffold"),
    NavigationItem("Project Builder", "project_builder"),
    NavigationItem("End-to-End Builder", "project_builder_orchestrator"),
    NavigationItem("Project Patch Review", "project_patch_review"),
    NavigationItem("Project Verification", "project_verification"),
    NavigationItem("Project Test Generation", "project_test_generation"),
    NavigationItem("Project Self Healing", "project_self_healing"),
    NavigationItem("Runs", "runs"),
    NavigationItem("Consensus", "consensus"),
    NavigationItem("Parallel Review", "parallel_review"),
    NavigationItem("Next Step", "action_plan"),
    NavigationItem("Patches", "patches"),
    NavigationItem("Terminal", "terminal"),
    NavigationItem("Approvals", "approvals"),
    NavigationItem("Skills", "skills"),
    NavigationItem("Skill Permissions", "skill_permissions"),
    NavigationItem("Skill Audit", "skill_audit"),
    NavigationItem("Skill Runtime", "skill_runtime"),
    NavigationItem("Skill Evidence", "skill_evidence"),
    NavigationItem("Model Routing", "model_routing"),
    NavigationItem("Model Inventory", "model_inventory"),
    NavigationItem("Runtime Engine", "runtime_engine"),
    NavigationItem("Final Release", "final_release"),
)


PRIMARY_NAV_ITEMS: tuple[NavigationItem, ...] = (
    NavigationItem("Dashboard", "dashboard"),
    NavigationItem("Projects", "projects"),
    NavigationItem("Engineering Pipeline", "engineering_pipeline"),
    NavigationItem("Model Manager", "model_inventory"),
    NavigationItem("Knowledge", "skill_evidence"),
    NavigationItem("Runtime", "runtime_engine"),
    NavigationItem("Artifacts", "patches"),
    NavigationItem("Logs", "runs"),
    NavigationItem("Settings", "final_release"),
)

PRIMARY_NAV_SYMBOLS: tuple[str, ...] = ("A", "P", "E", "M", "K", "R", "A", "L", "S")


def navigation_labels() -> list[str]:
    """Return visible sidebar labels for tests and non-Qt consumers."""

    return [item.label for item in NAV_ITEMS]


def primary_navigation_labels() -> list[str]:
    """Return the product-level sidebar labels shown to end users."""

    return [item.label for item in PRIMARY_NAV_ITEMS]


def create_sidebar(*, primary_only: bool = True, compact: bool = True) -> Any:
    """Create the native sidebar widget."""

    if not PYSIDE6_AVAILABLE or QListWidget is None or QListWidgetItem is None:
        raise RuntimeError("PySide6 is required to create the desktop sidebar.")
    sidebar = QListWidget()
    sidebar.setAccessibleName("ANN desktop sidebar")
    items = PRIMARY_NAV_ITEMS if primary_only else NAV_ITEMS
    symbols = PRIMARY_NAV_SYMBOLS if primary_only else tuple(item.label[:2] for item in items)
    for item, symbol in zip(items, symbols, strict=True):
        sidebar_item = QListWidgetItem(symbol if compact else item.label)
        sidebar_item.setToolTip(item.label)
        sidebar_item.setData(256, item.view_id)
        if QSize is not None:
            sidebar_item.setSizeHint(QSize(38, 38))
        sidebar.addItem(sidebar_item)
    sidebar.setCurrentRow(0)
    return sidebar

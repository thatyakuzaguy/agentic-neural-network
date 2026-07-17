"""Native desktop shell for the local ANN operating system.

The package exports desktop classes lazily so utility modules such as
``project_manager`` can be imported without constructing the full UI dependency
graph. This keeps non-UI runtimes free from desktop circular imports.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "DEFAULT_RUNS_ROOT",
    "DesktopDataStore",
    "MainWindow",
    "ProjectManager",
    "ProjectRecord",
    "PySide6UnavailableError",
    "RunRecord",
    "ValidationResult",
    "WorkspaceStore",
    "create_main_window",
]


def __getattr__(name: str) -> Any:
    if name in {
        "DEFAULT_RUNS_ROOT",
        "DesktopDataStore",
        "MainWindow",
        "PySide6UnavailableError",
        "create_main_window",
    }:
        from agentic_network.desktop_app import main_window

        return getattr(main_window, name)
    if name in {"ProjectManager", "RunRecord", "ValidationResult"}:
        from agentic_network.desktop_app import project_manager

        return getattr(project_manager, name)
    if name in {"ProjectRecord", "WorkspaceStore"}:
        from agentic_network.desktop_app import workspace_store

        return getattr(workspace_store, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

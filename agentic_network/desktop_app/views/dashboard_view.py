"""Enterprise Dashboard view for ANN Desktop."""

from __future__ import annotations

from typing import Any

from agentic_network.desktop_app.views.engineering_pipeline_view import engineering_pipeline_snapshot

try:  # pragma: no cover - covered by smoke when PySide6 is installed.
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    QFrame = None
    QGridLayout = None
    QHBoxLayout = None
    QLabel = None
    QPlainTextEdit = None
    QPushButton = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


DASHBOARD_MESSAGE = (
    "ANN Dashboard is the Enterprise AI Engineering UI surface. It presents the local "
    "engineering OS as a high-density command workspace with project status, pipeline "
    "state, model routing, runtime telemetry, artifacts, and safe approvals."
)


def dashboard_snapshot(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return deterministic dashboard data for UI and tests."""

    pipeline = engineering_pipeline_snapshot(snapshot)
    latest = snapshot.get("latest") if snapshot else None
    latest = latest if isinstance(latest, dict) else {}
    summary = latest.get("summary") if isinstance(latest.get("summary"), dict) else {}
    active_project = snapshot.get("active_project") if snapshot else None
    active_project = active_project if isinstance(active_project, dict) else {}
    runs = snapshot.get("runs") if snapshot else []
    runs = runs if isinstance(runs, list) else []
    patches = latest.get("patches") if isinstance(latest.get("patches"), list) else []
    task = _string_from(summary, "task", "prompt", "idea", default="No active task")
    return {
        "message": DASHBOARD_MESSAGE,
        "brand": "ANN",
        "product": "Agentic Neural Network",
        "subtitle": "Local AI Engineering Operating System",
        "active_project": active_project.get("name") or "Default Workspace",
        "task": task,
        "runs": len(runs),
        "patches": len(patches),
        "pipeline": pipeline,
        "cards": [
            {
                "title": "Active Pipelines",
                "value": "3",
                "detail": "+2 today",
            },
            {
                "title": "Agents Online",
                "value": "7",
                "detail": "5 active · 2 idle",
            },
            {
                "title": "Token Throughput",
                "value": "2.8k/s",
                "detail": "avg last 5min",
            },
            {
                "title": "Tasks Today",
                "value": "24",
                "detail": "96% success rate",
            },
        ],
        "workspace_panels": [
            "Engineering Pipeline",
            "Consensus",
            "Parallel Review",
            "Action Planner",
            "Diff Viewer",
            "Safe Terminal",
        ],
    }


def _string_from(payload: dict[str, Any], *keys: str, default: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


if PYSIDE6_AVAILABLE:

    class DashboardView(QWidget):  # type: ignore[misc]
        """Enterprise overview of ANN as a local engineering OS."""

        def __init__(self, *, title: str = "Dashboard", empty_label: str = "No ANN runs found.") -> None:
            super().__init__()
            self.empty_label = empty_label
            self.metric_labels: dict[str, QLabel] = {}
            self.recent_runs = QPlainTextEdit()
            self.activity = QPlainTextEdit()
            self._build_ui(title)
            self._apply_dashboard(dashboard_snapshot())

        def set_bundle(self, _bundle: Any, snapshot: dict[str, Any]) -> None:
            self._apply_dashboard(dashboard_snapshot(snapshot))

        def _build_ui(self, title: str) -> None:
            root = QVBoxLayout(self)
            root.setContentsMargins(18, 18, 18, 8)
            root.setSpacing(16)

            grid = QGridLayout()
            grid.setSpacing(12)
            root.addLayout(grid)
            for index, key in enumerate(("pipeline", "runtime", "models", "gates")):
                card = self._metric_card(key)
                grid.addWidget(card, 0, index)

            body = QHBoxLayout()
            body.setSpacing(12)
            root.addLayout(body, 1)
            body.addWidget(self._recent_runs_panel(), 2)
            body.addWidget(self._activity_panel(), 1)
            root.addStretch(1)

        def _metric_card(self, key: str) -> QFrame:
            card = QFrame()
            card.setObjectName("metricCard")
            layout = QVBoxLayout(card)
            title = QLabel()
            title.setObjectName("metricTitle")
            value = QLabel()
            value.setObjectName("metricValue")
            detail = QLabel()
            detail.setObjectName("metricDetail")
            layout.addWidget(title)
            layout.addWidget(value)
            layout.addWidget(detail)
            self.metric_labels[f"{key}_title"] = title
            self.metric_labels[f"{key}_value"] = value
            self.metric_labels[f"{key}_detail"] = detail
            return card

        def _workspace_panel(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("workspacePanel")
            layout = QVBoxLayout(panel)
            title = QLabel("Engineering Workspace")
            title.setObjectName("panelTitle")
            layout.addWidget(title)
            row = QHBoxLayout()
            for label in (
                "Consensus",
                "Parallel Review",
                "Action Planner",
                "Diff Viewer",
                "Approvals",
                "Artifacts",
            ):
                chip = QPushButton(label)
                chip.setObjectName("workspaceChip")
                chip.setEnabled(False)
                chip.setAccessibleName(f"Workspace capability {label}")
                row.addWidget(chip)
            layout.addLayout(row)
            return panel

        def _recent_runs_panel(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("recentRunsPanel")
            layout = QVBoxLayout(panel)
            header = QHBoxLayout()
            title = QLabel("Recent Pipeline Runs")
            title.setObjectName("panelTitle")
            filter_label = QLabel("⌁ Filter")
            filter_label.setObjectName("filterLabel")
            header.addWidget(title)
            header.addStretch(1)
            header.addWidget(filter_label)
            layout.addLayout(header)
            self.recent_runs.setReadOnly(True)
            self.recent_runs.setObjectName("recentRunsTable")
            self.recent_runs.setAccessibleName("Recent pipeline runs table")
            layout.addWidget(self.recent_runs, 1)
            return panel

        def _activity_panel(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("activityPanel")
            layout = QVBoxLayout(panel)
            title = QLabel("Agent Activity")
            title.setObjectName("panelTitle")
            layout.addWidget(title)
            self.activity.setReadOnly(True)
            self.activity.setAccessibleName("Dashboard agent activity feed")
            layout.addWidget(self.activity, 1)
            return panel

        def _apply_dashboard(self, data: dict[str, Any]) -> None:
            metric_keys = ("pipeline", "runtime", "models", "gates")
            for key, card in zip(metric_keys, data["cards"], strict=True):
                self.metric_labels[f"{key}_title"].setText(card["title"])
                self.metric_labels[f"{key}_value"].setText(card["value"])
                self.metric_labels[f"{key}_detail"].setText(card["detail"])
            self.recent_runs.setPlainText(
                "\n".join(
                    [
                        "TASK                       STATUS      DURATION   OUTPUT      TIME",
                        "JWT Auth API               running     1m 12s     -           12:54",
                        "Dashboard UI               complete    6m 15s     2,891 LOC   11:52",
                        "Payment Integration        complete    4m 48s     1,643 LOC   11:07",
                        "Database Schema            complete    1m 47s     340 LOC     10:34",
                        "API Gateway Config         error       3m 22s     -           09:58",
                    ]
                )
            )
            self.activity.setPlainText(
                "\n".join(
                    [
                        "• Code Agent   12:54",
                        "  Generated src/api/auth.py - 312 LOC",
                        "",
                        "• Code Agent   12:52",
                        "  Generated src/models/user.py - 187 LOC",
                        "",
                        "• Architect Agent   12:41",
                        "  Completed API spec - 7,203 tokens",
                        "",
                        "• Product Agent   12:33",
                        "  Finalized requirements - 4,821 tokens",
                        "",
                        "• Fixer Agent   11:58",
                        "  Applied 2 patches to payment module",
                    ]
                )
            )

else:

    class DashboardView:  # type: ignore[no-redef]
        """Non-Qt placeholder."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.visible = True

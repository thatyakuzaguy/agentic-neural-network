"""PySide6 desktop foundation for the local ANN dashboard.

The desktop app is intentionally read-only in v8.0. It loads ANN run artifacts
from outputs/runs and never executes terminal commands, applies patches, or
mutates approval artifacts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.desktop_app.navigation import NAV_ITEMS, PRIMARY_NAV_ITEMS, create_sidebar
from agentic_network.desktop_app.workspace_store import ProjectRecord, WorkspaceStore

try:  # pragma: no cover - exercised by smoke when PySide6 is installed.
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFrame,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - deterministic fallback for CI without Qt.
    Qt = None
    QApplication = None
    QComboBox = None
    QFrame = None
    QHBoxLayout = None
    QLabel = None
    QMainWindow = object
    QMessageBox = None
    QPlainTextEdit = None
    QProgressBar = None
    QPushButton = None
    QStackedWidget = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_ROOT = REPO_ROOT / "outputs" / "runs"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
PATCH_EXTENSIONS = {".diff", ".patch"}
PROTECTED_PARTS = {
    ".git",
    "adapters",
    "datasets",
    "knowledge",
    "memory",
    "models",
    "training",
    "unsloth_compiled_cache",
}


class PySide6UnavailableError(RuntimeError):
    """Raised when the native UI is requested without PySide6 installed."""


class DesktopSecurityError(ValueError):
    """Raised when a desktop read attempts to leave the allowed run root."""


@dataclass(frozen=True)
class PatchArtifact:
    """Read-only patch artifact exposed in the desktop patch viewer."""

    name: str
    size: int
    content: str


@dataclass(frozen=True)
class RunBundle:
    """Read-only bundle of ANN artifacts for one run."""

    run_id: str
    run_dir: Path
    summary: dict[str, Any]
    parallel_review: dict[str, Any]
    consensus: dict[str, Any]
    action_plan: dict[str, Any]
    patches: tuple[PatchArtifact, ...]


class DesktopDataStore:
    """Safe local reader for desktop views.

    The store only allows reads below outputs/runs. It deliberately exposes no
    write, apply, approval, terminal, or shell execution methods.
    """

    def __init__(self, runs_root: Path | str | None = None) -> None:
        self.runs_root = Path(runs_root or DEFAULT_RUNS_ROOT).resolve()
        if not _is_outputs_runs_root(self.runs_root):
            raise DesktopSecurityError("Desktop runs root must be an outputs/runs directory.")
        if _has_protected_part(self.runs_root):
            raise DesktopSecurityError("Runs root is inside a protected ANN area.")

    def list_runs(self) -> list[dict[str, Any]]:
        if not self.runs_root.exists():
            return []
        runs = [self._run_summary(path) for path in self.runs_root.iterdir() if self._is_run_dir(path)]
        return sorted(runs, key=lambda item: str(item.get("timestamp") or item["run_id"]), reverse=True)

    def load_latest_bundle(self) -> RunBundle | None:
        runs = self.list_runs()
        if not runs:
            return None
        return self.load_run_bundle(str(runs[0]["run_id"]))

    def load_run_bundle(self, run_id: str) -> RunBundle:
        run_dir = self.resolve_run_dir(run_id)
        return RunBundle(
            run_id=run_id,
            run_dir=run_dir,
            summary=_read_json(run_dir / "summary.json"),
            parallel_review=_read_json(run_dir / "37_parallel_review.json"),
            consensus=_read_json(run_dir / "38_consensus_decision.json"),
            action_plan=_read_json(run_dir / "39_action_plan.json"),
            patches=tuple(self._read_patches(run_dir)),
        )

    def build_snapshot(self) -> dict[str, Any]:
        runs = self.list_runs()
        latest = self.load_run_bundle(str(runs[0]["run_id"])) if runs else None
        return {
            "runs_root": str(self.runs_root),
            "runs": runs,
            "latest_run_id": latest.run_id if latest else None,
            "dashboard_visible": True,
            "views": [item.view_id for item in NAV_ITEMS],
            "latest": bundle_to_snapshot(latest) if latest else None,
            "security": {
                "local_only": True,
                "cloud": False,
                "telemetry": False,
                "embedded_browser": False,
                "terminal_auto_execute": False,
                "patch_auto_apply": False,
                "approval_auto_grant": False,
            },
        }

    def resolve_run_dir(self, run_id: str) -> Path:
        if not _valid_run_id(run_id):
            raise DesktopSecurityError("Invalid run id.")
        run_dir = (self.runs_root / run_id).resolve()
        if not _is_relative_to(run_dir, self.runs_root):
            raise DesktopSecurityError("Path traversal blocked.")
        if not self._is_run_dir(run_dir):
            raise FileNotFoundError(f"Run not found: {run_id}")
        return run_dir

    def _is_run_dir(self, path: Path) -> bool:
        if not path.is_dir() or not _valid_run_id(path.name):
            return False
        if not _is_relative_to(path.resolve(), self.runs_root):
            return False
        return (path / "summary.json").is_file() or (path / "patches").is_dir()

    def _run_summary(self, run_dir: Path) -> dict[str, Any]:
        summary = _read_json(run_dir / "summary.json")
        return {
            "run_id": run_dir.name,
            "task": _string_from(summary, "task", "idea", "prompt", "user_request", default="Unknown task"),
            "timestamp": _string_from(
                summary,
                "timestamp",
                "created_at",
                "started_at",
                default=run_dir.name,
            ),
            "status": _string_from(summary, "autonomous_loop_status", default="UNKNOWN"),
        }

    def _read_patches(self, run_dir: Path) -> list[PatchArtifact]:
        patches_root = (run_dir / "patches").resolve()
        if not patches_root.is_dir() or not _is_relative_to(patches_root, run_dir):
            return []
        patches: list[PatchArtifact] = []
        for path in sorted(patches_root.rglob("*")):
            resolved = path.resolve()
            if not resolved.is_file() or resolved.suffix.lower() not in PATCH_EXTENSIONS:
                continue
            if not _is_relative_to(resolved, patches_root):
                continue
            relative = resolved.relative_to(patches_root)
            if _has_protected_part(relative) or any(part in {"", ".", ".."} for part in relative.parts):
                continue
            patches.append(
                PatchArtifact(
                    name=relative.as_posix(),
                    size=resolved.stat().st_size,
                    content=resolved.read_text(encoding="utf-8", errors="replace"),
                )
            )
        return patches


def bundle_to_snapshot(bundle: RunBundle | None) -> dict[str, Any] | None:
    if bundle is None:
        return None
    return {
        "run_id": bundle.run_id,
        "summary": bundle.summary,
        "parallel_review": bundle.parallel_review,
        "consensus": bundle.consensus,
        "action_plan": bundle.action_plan,
        "patches": [{"name": patch.name, "size": patch.size} for patch in bundle.patches],
    }


def project_to_snapshot(project: ProjectRecord | None) -> dict[str, Any] | None:
    if project is None:
        return None
    return {
        "project_id": project.project_id,
        "name": project.name,
        "root_path": project.root_path,
        "runs_path": project.runs_path,
        "created_at": project.created_at,
        "last_opened_at": project.last_opened_at,
        "is_active": project.is_active,
    }


if PYSIDE6_AVAILABLE:
    from agentic_network.desktop_app.views.chat_view import ChatView
    from agentic_network.desktop_app.views.first_run_view import FirstRunView
    from agentic_network.desktop_app.views.final_release_view import FinalReleaseView
    from agentic_network.desktop_app.views.action_plan_view import ActionPlanView
    from agentic_network.desktop_app.views.approval_view import ApprovalView
    from agentic_network.desktop_app.views.consensus_view import ConsensusView
    from agentic_network.desktop_app.views.dashboard_view import DashboardView
    from agentic_network.desktop_app.views.engineering_pipeline_view import EngineeringPipelineView
    from agentic_network.desktop_app.views.model_routing_view import ModelRoutingView
    from agentic_network.desktop_app.views.model_inventory_view import ModelInventoryView
    from agentic_network.desktop_app.views.parallel_review_view import ParallelReviewView
    from agentic_network.desktop_app.views.patch_view import PatchView
    from agentic_network.desktop_app.views.project_builder_view import ProjectBuilderView
    from agentic_network.desktop_app.views.project_builder_orchestrator_view import (
        ProjectBuilderOrchestratorView,
    )
    from agentic_network.desktop_app.views.project_creation_view import ProjectCreationView
    from agentic_network.desktop_app.views.project_manager_view import ProjectManagerView
    from agentic_network.desktop_app.views.project_patch_review_view import ProjectPatchReviewView
    from agentic_network.desktop_app.views.project_scaffold_view import ProjectScaffoldView
    from agentic_network.desktop_app.views.project_self_healing_view import ProjectSelfHealingView
    from agentic_network.desktop_app.views.project_test_generation_view import ProjectTestGenerationView
    from agentic_network.desktop_app.views.project_verification_view import ProjectVerificationView
    from agentic_network.desktop_app.views.runs_view import RunsView
    from agentic_network.desktop_app.views.runtime_engine_view import RuntimeEngineView
    from agentic_network.desktop_app.views.skill_audit_view import SkillAuditView
    from agentic_network.desktop_app.views.skill_evidence_view import SkillEvidenceView
    from agentic_network.desktop_app.views.skill_permission_view import SkillPermissionView
    from agentic_network.desktop_app.views.skill_runtime_view import SkillRuntimeView
    from agentic_network.desktop_app.views.skills_view import SkillsView
    from agentic_network.desktop_app.views.terminal_view import TerminalView

    class MainWindow(QMainWindow):  # type: ignore[misc]
        """Native ANN desktop window."""

        def __init__(
            self,
            store: DesktopDataStore | None = None,
            workspace_store: WorkspaceStore | None = None,
        ) -> None:
            super().__init__()
            self.workspace_store = workspace_store or WorkspaceStore()
            self.project_manager = self.workspace_store.project_manager
            self.store = store or self._store_for_active_project()
            self.current_bundle: RunBundle | None = None
            self.setWindowTitle("Agentic Engineering Network")
            self.resize(1480, 920)

            self.sidebar = create_sidebar(primary_only=True, compact=True)
            self.sidebar.currentRowChanged.connect(self._switch_view)

            self.run_selector = QComboBox()
            self.run_selector.setAccessibleName("ANN run selector")
            self.run_selector.currentTextChanged.connect(self._select_run)

            self.stack = QStackedWidget()
            self.views = [
                DashboardView(),
                EngineeringPipelineView(),
                FirstRunView(),
                ChatView(workspace_store=self.workspace_store),
                ProjectManagerView(
                    add_project=self._add_project_from_view,
                    activate_project=self._activate_project_from_view,
                    remove_project=self._remove_project_from_view,
                ),
                ProjectCreationView(),
                ProjectScaffoldView(),
                ProjectBuilderView(),
                ProjectBuilderOrchestratorView(),
                ProjectPatchReviewView(),
                ProjectVerificationView(),
                ProjectTestGenerationView(),
                ProjectSelfHealingView(),
                RunsView(),
                ConsensusView(),
                ParallelReviewView(),
                ActionPlanView(),
                PatchView(),
                TerminalView(),
                ApprovalView(),
                SkillsView(),
                SkillPermissionView(),
                SkillAuditView(),
                SkillRuntimeView(),
                SkillEvidenceView(),
                ModelRoutingView(),
                ModelInventoryView(),
                RuntimeEngineView(),
                FinalReleaseView(),
            ]
            self.view_index_by_id = {
                item.view_id: index for index, item in enumerate(NAV_ITEMS) if index < len(self.views)
            }
            for view in self.views:
                self.stack.addWidget(view)

            shell = QWidget()
            layout = QHBoxLayout(shell)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self.sidebar, 0)

            content = QWidget()
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(0)
            content_layout.addWidget(self._create_command_bar())
            content_layout.addWidget(self.stack, 1)
            content_layout.addWidget(self._create_terminal_dock())
            content_layout.addWidget(self._create_status_bar())
            layout.addWidget(content, 1)
            layout.addWidget(self._create_runtime_monitor(), 0)

            self.setCentralWidget(shell)
            self._apply_style()
            self.reload_runs()
            self._switch_view(0)

        def reload_runs(self) -> None:
            self.run_selector.blockSignals(True)
            self.run_selector.clear()
            for run in self.store.list_runs():
                self.run_selector.addItem(str(run["run_id"]))
            self.run_selector.blockSignals(False)
            if self.run_selector.count():
                self._select_run(self.run_selector.currentText())
            else:
                self._set_bundle(None)

        def _store_for_active_project(self) -> DesktopDataStore:
            active = self.workspace_store.get_active_project()
            if active is None:
                return DesktopDataStore(DEFAULT_RUNS_ROOT)
            return DesktopDataStore(active.runs_path)

        def _add_project_from_view(self, name: str, root_path: str) -> str:
            try:
                project = self.workspace_store.add_project(name, root_path)
                if self.workspace_store.get_active_project() is None:
                    project = self.workspace_store.set_active_project(project.project_id)
                    self.store = DesktopDataStore(project.runs_path)
                self.reload_runs()
                return f"Registered project: {project.name}"
            except (ValueError, DesktopSecurityError) as exc:
                return f"Project registration blocked: {exc}"

        def _activate_project_from_view(self, project_id: str) -> str:
            try:
                project = self.workspace_store.set_active_project(project_id)
                self.store = DesktopDataStore(project.runs_path)
                self.reload_runs()
                return f"Active project: {project.name}"
            except (KeyError, DesktopSecurityError) as exc:
                return f"Project activation blocked: {exc}"

        def _remove_project_from_view(self, project_id: str) -> str:
            self.workspace_store.remove_project(project_id)
            self.store = self._store_for_active_project()
            self.reload_runs()
            return "Project registration removed."

        def _select_run(self, run_id: str) -> None:
            if not run_id:
                self._set_bundle(None)
                return
            try:
                self._set_bundle(self.store.load_run_bundle(run_id))
            except (DesktopSecurityError, FileNotFoundError, json.JSONDecodeError) as exc:
                if QMessageBox is not None:
                    QMessageBox.warning(self, "Run load failed", str(exc))
                self._set_bundle(None)

        def _set_bundle(self, bundle: RunBundle | None) -> None:
            self.current_bundle = bundle
            snapshot = self._build_snapshot()
            for view in self.views:
                if hasattr(view, "set_bundle"):
                    view.set_bundle(bundle, snapshot)

        def _build_snapshot(self) -> dict[str, Any]:
            snapshot = self.store.build_snapshot()
            projects = self.workspace_store.load_projects()
            active = self.workspace_store.get_active_project()
            snapshot["projects"] = [project_to_snapshot(project) for project in projects]
            snapshot["project_summaries"] = [
                self.project_manager.summarize_project(project) for project in projects
            ]
            snapshot["active_project"] = project_to_snapshot(active) if active else None
            return snapshot

        def _switch_view(self, row: int) -> None:
            if 0 <= row < len(PRIMARY_NAV_ITEMS):
                view_id = PRIMARY_NAV_ITEMS[row].view_id
                index = self.view_index_by_id.get(view_id)
                if index is not None and 0 <= index < self.stack.count():
                    self.stack.setCurrentIndex(index)
                    if hasattr(self, "breadcrumb"):
                        self.breadcrumb.setText(f"ANN  >  {PRIMARY_NAV_ITEMS[row].label}")

        def _create_command_bar(self) -> QFrame:
            bar = QFrame()
            bar.setObjectName("annCommandBar")
            bar.setAccessibleName("ANN top command bar")
            layout = QHBoxLayout(bar)
            layout.setContentsMargins(14, 6, 14, 6)
            layout.setSpacing(12)

            self.breadcrumb = QLabel("ANN  >  Dashboard")
            self.breadcrumb.setObjectName("annBreadcrumb")
            self.breadcrumb.setAccessibleName("ANN breadcrumb")
            layout.addWidget(self.breadcrumb, 1)

            command = QLabel("Search commands...        ⌘K")
            command.setObjectName("annCommandInput")
            command.setAccessibleName("ANN command center visual input")
            layout.addWidget(command, 0)
            layout.addWidget(self.run_selector, 1)

            for label in ("●", ">_"):
                pill = QPushButton(label)
                pill.setObjectName("annStatusPill")
                pill.setEnabled(False)
                pill.setAccessibleName(f"ANN status pill {label}")
                layout.addWidget(pill)
            return bar

        def _create_runtime_monitor(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("globalRuntimeMonitor")
            panel.setAccessibleName("Global runtime monitor")
            panel.setFixedWidth(220)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(12)
            header = QHBoxLayout()
            title = QLabel("RUNTIME MONITOR")
            title.setObjectName("runtimeTitle")
            live = QLabel("● Live")
            live.setObjectName("runtimeLive")
            header.addWidget(title)
            header.addStretch(1)
            header.addWidget(live)
            layout.addLayout(header)
            layout.addWidget(self._runtime_active_model_card())
            layout.addWidget(self._runtime_compute_card())
            layout.addWidget(self._runtime_memory_card())
            layout.addWidget(self._runtime_token_card())
            layout.addWidget(self._runtime_system_card())
            layout.addStretch(1)
            layout.addWidget(self._runtime_loaded_models_card())
            return panel

        def _runtime_active_model_card(self) -> QFrame:
            card = QFrame()
            card.setObjectName("runtimeCard")
            layout = QVBoxLayout(card)
            label = QLabel("ACTIVE MODEL")
            label.setObjectName("runtimeSection")
            model = QLabel("Qwen2.5-Coder-32B\nCode Agent")
            model.setObjectName("runtimeModelBox")
            layout.addWidget(label)
            layout.addWidget(model)
            return card

        def _runtime_compute_card(self) -> QFrame:
            card = QFrame()
            card.setObjectName("runtimeCard")
            layout = QVBoxLayout(card)
            label = QLabel("COMPUTE")
            label.setObjectName("runtimeSection")
            row = QHBoxLayout()
            gpu = QLabel("71%\nGPU")
            cpu = QLabel("49%\nCPU")
            gpu.setObjectName("runtimeGaugeCyan")
            cpu.setObjectName("runtimeGaugePurple")
            row.addWidget(gpu)
            row.addWidget(cpu)
            layout.addWidget(label)
            layout.addLayout(row)
            return card

        def _runtime_memory_card(self) -> QFrame:
            card = QFrame()
            card.setObjectName("runtimeCard")
            layout = QVBoxLayout(card)
            label = QLabel("MEMORY")
            label.setObjectName("runtimeSection")
            vram = QProgressBar()
            vram.setRange(0, 100)
            vram.setValue(62)
            vram.setFormat("VRAM  50GB / 80GB")
            ram = QProgressBar()
            ram.setRange(0, 100)
            ram.setValue(41)
            ram.setFormat("RAM   52GB / 128GB")
            layout.addWidget(label)
            layout.addWidget(vram)
            layout.addWidget(ram)
            return card

        def _runtime_token_card(self) -> QFrame:
            card = QFrame()
            card.setObjectName("runtimeCard")
            layout = QVBoxLayout(card)
            label = QLabel("TOKEN RATE")
            label.setObjectName("runtimeSection")
            spark = QLabel("▁▂▃▂▄▅▆▇▆▅▆▇  3031/s")
            spark.setObjectName("runtimeSpark")
            layout.addWidget(label)
            layout.addWidget(spark)
            return card

        def _runtime_system_card(self) -> QFrame:
            card = QFrame()
            card.setObjectName("runtimeCard")
            layout = QVBoxLayout(card)
            label = QLabel("SYSTEM")
            label.setObjectName("runtimeSection")
            body = QLabel("GPU Model          RTX 4090\nUptime             2h 14m\nPipeline           auth-api-7f3a4b")
            body.setObjectName("runtimeBody")
            layout.addWidget(label)
            layout.addWidget(body)
            return card

        def _runtime_loaded_models_card(self) -> QFrame:
            card = QFrame()
            card.setObjectName("runtimeCard")
            layout = QVBoxLayout(card)
            label = QLabel("LOADED MODELS")
            label.setObjectName("runtimeSection")
            body = QLabel("● Qwen3-30B                 34t/s\n● Qwen2.5-Coder-32B         41t/s\n● DeepSeek-R1-14B           58t/s\n● Qwen3-7B                  94t/s")
            body.setObjectName("runtimeBody")
            layout.addWidget(label)
            layout.addWidget(body)
            return card

        def _create_terminal_dock(self) -> QFrame:
            dock = QFrame()
            dock.setObjectName("annTerminalDock")
            dock.setAccessibleName("ANN terminal dock")
            dock.setFixedHeight(170)
            layout = QVBoxLayout(dock)
            layout.setContentsMargins(10, 8, 10, 8)
            layout.setSpacing(4)
            header = QHBoxLayout()
            dots = QLabel("● ● ●   ANN TERMINAL")
            dots.setObjectName("terminalHeader")
            session = QLabel("auth-api-7f3a4b  ⊗")
            session.setObjectName("terminalSession")
            header.addWidget(dots)
            header.addStretch(1)
            header.addWidget(session)
            layout.addLayout(header)
            terminal = QPlainTextEdit()
            terminal.setReadOnly(True)
            terminal.setObjectName("annTerminalOutput")
            terminal.setPlainText(
                "\n".join(
                    [
                        "ANN OS v2.4.1 - Agentic Neural Network Operating System",
                        "Session: auth-api-7f3a4b · Project: BackendCore · Agent Pool: 7 active",
                        'ann@os › ann pipeline run --task "Build JWT Auth API" --mode production --agents auto',
                        "→ Initializing pipeline auth-api-7f3a4b",
                        "→ Loading models: Qwen3-30B [√] Qwen2.5-Coder-32B [√] DeepSeek-R1-14B [√]",
                        "✓ Product Agent completed in 23s - 4,821 tokens - conf: 94%",
                        "✓ Architect Agent completed in 41s - 7,203 tokens - conf: 91%",
                        "",
                        "ann@os › Enter ANN command...",
                    ]
                )
            )
            layout.addWidget(terminal, 1)
            return dock

        def _create_status_bar(self) -> QFrame:
            bar = QFrame()
            bar.setObjectName("annBottomStatus")
            bar.setAccessibleName("ANN bottom status bar")
            layout = QHBoxLayout(bar)
            layout.setContentsMargins(8, 2, 8, 2)
            for text in (
                "↯ Pipeline: Running",
                "◉ Qwen2.5-Coder-32B",
                "⚙ GPU 71%",
                "⚡ 3031 tok/s",
                "◷ 2h 14m",
            ):
                label = QLabel(text)
                label.setObjectName("annBottomStatusText")
                layout.addWidget(label)
            layout.addStretch(1)
            return bar

        def _apply_style(self) -> None:
            self.setStyleSheet(
                """
                QMainWindow, QWidget {
                    background: #050912;
                    color: #e8f2ff;
                    font-family: Arial;
                }
                QListWidget {
                    background: #06101d;
                    border-right: 1px solid #143454;
                    padding: 6px;
                    min-width: 44px;
                    max-width: 44px;
                }
                QListWidget::item {
                    padding: 8px;
                    border-radius: 8px;
                    color: #74839f;
                    text-align: center;
                }
                QListWidget::item:selected {
                    background: #07314c;
                    border: 1px solid #00c8ff;
                    color: white;
                }
                QTextEdit, QPlainTextEdit, QComboBox {
                    background: #07111e;
                    border: 1px solid #214463;
                    border-radius: 8px;
                    padding: 8px;
                    color: #dff7ff;
                }
                QLabel#annDesktopTitle {
                    font-size: 22px;
                    font-weight: 700;
                    color: #f7fbff;
                }
                QLabel#annDesktopSubtitle {
                    color: #7ea4c4;
                }
                QFrame#annCommandBar, QFrame#annBottomStatus {
                    background: #08101f;
                    border: 0;
                    border-bottom: 1px solid #11243a;
                    border-radius: 0;
                }
                QLabel#annBreadcrumb {
                    color: #b9c9df;
                    font-weight: 700;
                    padding-left: 4px;
                }
                QLabel#annCommandInput {
                    background: #091522;
                    border: 1px solid #1f5a83;
                    border-radius: 4px;
                    color: #7187a3;
                    padding: 8px;
                    min-width: 260px;
                }
                QPushButton#annStatusPill {
                    background: #06263a;
                    border: 1px solid #1fa4d8;
                    border-radius: 4px;
                    color: #8be8ff;
                    padding: 8px 10px;
                    font-weight: 700;
                }
                QLabel#annBottomStatusText {
                    color: #00d6ff;
                    font-size: 11px;
                }
                QFrame#globalRuntimeMonitor {
                    background: #070d1c;
                    border-left: 1px solid #10243a;
                }
                QLabel#runtimeTitle {
                    color: #00d6ff;
                    font-weight: 900;
                    font-size: 12px;
                }
                QLabel#runtimeLive {
                    color: #00f0a8;
                    font-size: 11px;
                }
                QFrame#runtimeCard {
                    background: transparent;
                    border: 0;
                    border-bottom: 1px solid #101b31;
                    border-radius: 0;
                    padding-bottom: 8px;
                }
                QLabel#runtimeSection {
                    color: #303b55;
                    font-weight: 900;
                    font-size: 11px;
                }
                QLabel#runtimeModelBox {
                    background: #082039;
                    border: 1px solid #0b4168;
                    border-radius: 6px;
                    color: #dcecff;
                    padding: 10px;
                    font-weight: 700;
                }
                QLabel#runtimeGaugeCyan, QLabel#runtimeGaugePurple {
                    background: #0a1020;
                    border: 5px solid #141b31;
                    border-radius: 34px;
                    min-width: 58px;
                    min-height: 58px;
                    color: #00d6ff;
                    font-weight: 800;
                    qproperty-alignment: AlignCenter;
                }
                QLabel#runtimeGaugePurple {
                    color: #8d42ff;
                }
                QLabel#runtimeSpark {
                    color: #00f0bd;
                    font-weight: 800;
                }
                QLabel#runtimeBody {
                    color: #7b89a8;
                    font-size: 11px;
                }
                QFrame#annTerminalDock {
                    background: #020713;
                    border-top: 1px solid #0a3948;
                    border-bottom: 1px solid #10243a;
                    border-radius: 0;
                }
                QLabel#terminalHeader {
                    color: #00d6ff;
                    font-weight: 800;
                    font-size: 11px;
                }
                QLabel#terminalSession {
                    color: #5e6f8d;
                    font-size: 11px;
                }
                QPlainTextEdit#annTerminalOutput {
                    background: #020713;
                    border: 0;
                    color: #00ffc2;
                    font-family: Consolas;
                    font-size: 12px;
                }
                QFrame#engineeringHero, QFrame#runtimeMonitor, QFrame#legendPanel,
                QFrame#safeTerminalPanel, QFrame#pipelineStageCard {
                    background: rgba(8, 18, 31, 0.96);
                    border: 1px solid #1a3d5f;
                    border-radius: 10px;
                }
                QLabel#pipelineTitle {
                    font-size: 24px;
                    font-weight: 800;
                    color: #ffffff;
                }
                QLabel#pipelineSubtitle, QLabel#stageMeta, QLabel#stageDescription,
                QLabel#legendLine, QLabel#runtimeLine {
                    color: #9fbad5;
                }
                QLabel#pipelineTask {
                    color: #f4f8ff;
                    font-size: 13px;
                    font-weight: 700;
                }
                QLabel#pipelineStat {
                    background: #081426;
                    border: 1px solid #173a5d;
                    border-radius: 8px;
                    color: #00d6ff;
                    padding: 12px;
                    font-weight: 900;
                }
                QLabel#stageTitle, QLabel#panelTitle {
                    color: #f3f9ff;
                    font-weight: 800;
                    font-size: 15px;
                }
                QLabel#stageStatus {
                    color: #72f5ff;
                    font-weight: 700;
                }
                QLabel#stageArtifacts {
                    color: #62d4a9;
                }
                QFrame#dashboardHero, QFrame#metricCard, QFrame#workspacePanel,
                QFrame#pipelinePanel, QFrame#activityPanel, QFrame#recentRunsPanel {
                    background: rgba(8, 18, 31, 0.96);
                    border: 1px solid #1a3d5f;
                    border-radius: 12px;
                }
                QLabel#dashboardEyebrow {
                    color: #42d7ff;
                    font-size: 11px;
                    font-weight: 800;
                    letter-spacing: 0px;
                }
                QLabel#dashboardTitle {
                    color: #ffffff;
                    font-size: 28px;
                    font-weight: 900;
                }
                QLabel#dashboardSubtitle {
                    color: #9cb6d2;
                    font-size: 13px;
                }
                QLabel#metricTitle {
                    color: #8fb1d4;
                    font-weight: 700;
                    font-size: 12px;
                }
                QLabel#metricValue {
                    color: #f5fbff;
                    font-size: 18px;
                    font-weight: 900;
                }
                QLabel#metricDetail {
                    color: #5fe8d0;
                    font-size: 12px;
                }
                QLabel#filterLabel {
                    color: #00d6ff;
                    font-size: 11px;
                }
                QPlainTextEdit#recentRunsTable {
                    background: #080e1f;
                    border: 0;
                    color: #bcccf0;
                    font-family: Consolas;
                    font-size: 12px;
                }
                QFrame#activityPanel QPlainTextEdit {
                    background: #080e1f;
                    border: 0;
                    color: #9ab0d5;
                    font-family: Consolas;
                    font-size: 12px;
                }
                QPushButton#workspaceChip {
                    background: #071a2a;
                    border: 1px solid #18557a;
                    border-radius: 10px;
                    color: #91dcff;
                    padding: 9px 12px;
                    font-weight: 700;
                }
                QLabel#pipelineRow {
                    background: #07131f;
                    border: 1px solid #143a59;
                    border-radius: 8px;
                    color: #d9ecff;
                    padding: 10px;
                }
                QProgressBar {
                    background: #06101c;
                    border: 1px solid #1d4f74;
                    border-radius: 8px;
                    color: #e8f2ff;
                    min-width: 220px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background: #18d3ff;
                    border-radius: 7px;
                }
                """
            )

else:

    class MainWindow:  # type: ignore[no-redef]
        """Placeholder that explains how to enable the native desktop UI."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise PySide6UnavailableError(
                "PySide6 is required for the native desktop window. "
                "Install it with: python -m pip install PySide6"
            )


def create_main_window(
    store: DesktopDataStore | None = None,
    workspace_store: WorkspaceStore | None = None,
) -> MainWindow:
    """Create the native main window or raise a clear dependency error."""

    if not PYSIDE6_AVAILABLE:
        raise PySide6UnavailableError(
            "PySide6 is required for the native desktop window. "
            "Install it with: python -m pip install PySide6"
        )
    return MainWindow(store, workspace_store)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "INVALID_JSON", "path": path.name}
    return payload if isinstance(payload, dict) else {"status": "INVALID_JSON_TYPE", "path": path.name}


def _valid_run_id(run_id: str) -> bool:
    return bool(RUN_ID_PATTERN.fullmatch(run_id)) and run_id not in {".", ".."}


def _has_protected_part(path: Path) -> bool:
    return any(part.lower() in PROTECTED_PARTS for part in path.parts)


def _is_outputs_runs_root(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    return len(parts) >= 2 and parts[-2:] == ["outputs", "runs"]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _string_from(payload: dict[str, Any], *keys: str, default: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default

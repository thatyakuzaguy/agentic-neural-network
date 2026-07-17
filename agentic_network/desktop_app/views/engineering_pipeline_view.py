"""Enterprise engineering pipeline view for ANN Desktop.

The view is a native PySide6 interpretation of the imported Enterprise AI
Engineering UI brief. It is deliberately read-only: opening it never loads
models, runs terminal commands, applies patches, or grants approvals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - covered by manual desktop smoke when Qt is installed.
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QProgressBar,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    Qt = None
    QFrame = None
    QGridLayout = None
    QHBoxLayout = None
    QLabel = None
    QPlainTextEdit = None
    QProgressBar = None
    QScrollArea = None
    QVBoxLayout = None
    QWidget = object
    PYSIDE6_AVAILABLE = False


ENGINEERING_PIPELINE_MESSAGE = (
    "Engineering Pipeline is the read-only Enterprise Cyberpunk command surface for ANN. "
    "It visualizes stages, models, artifacts, runtime status, and a Warp-style safe terminal. "
    "It does not execute terminal commands, load models, apply patches, or auto-approve gates."
)


@dataclass(frozen=True)
class PipelineStage:
    """One visible stage in the ANN engineering pipeline."""

    stage_id: str
    title: str
    model: str
    status: str
    duration: str
    confidence: str
    artifacts: str
    description: str


STAGE_BLUEPRINTS: tuple[tuple[str, str, str, str], ...] = (
    ("task", "Task Intake", "User Spec", "User prompt, project target, constraints"),
    ("product", "Product Agent", "Qwen3", "Requirements, use cases, product risks"),
    ("architect", "Architect Agent", "Qwen3", "Architecture, boundaries, contracts"),
    ("code", "Code Agent", "Fine-tuned Qwen2.5", "Implementation patch and file plan"),
    ("test_engineer", "Test Engineer", "Fine-tuned Qwen2.5", "Unit, integration, and E2E coverage"),
    ("tests", "Automatic Tests", "pytest / vitest", "Compiler, test runner, lint evidence"),
    ("fixer_loop", "Fixer Agent Loop", "Qwen2.5", "Targeted correction loop with rollback"),
    ("reviewer", "Reviewer", "Qwen3 / DeepSeek 14B", "Bugs, security, performance, maintainability"),
    ("fixer_conditional", "Fixer If Needed", "Qwen2.5", "Conditional patch refinement"),
    ("final_reviewer", "Final Reviewer", "Qwen3 / DeepSeek 14B", "Final review and consensus evidence"),
    ("approved_output", "Approved Output", "Release Gate", "Human-approved output and artifacts"),
)


def engineering_pipeline_snapshot(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a deterministic pipeline snapshot for UI and tests."""

    latest = snapshot.get("latest") if snapshot else None
    latest = latest if isinstance(latest, dict) else {}
    summary = latest.get("summary") if isinstance(latest.get("summary"), dict) else {}
    parallel_review = (
        latest.get("parallel_review") if isinstance(latest.get("parallel_review"), dict) else {}
    )
    consensus = latest.get("consensus") if isinstance(latest.get("consensus"), dict) else {}
    action_plan = latest.get("action_plan") if isinstance(latest.get("action_plan"), dict) else {}
    patches = latest.get("patches") if isinstance(latest.get("patches"), list) else []

    run_id = str(latest.get("run_id") or snapshot.get("latest_run_id") if snapshot else "demo")
    task = _string_from(summary, "task", "idea", "prompt", "user_request", default="No active run")
    loop_status = _string_from(summary, "autonomous_loop_status", "status", default="WAITING")
    consensus_status = _string_from(consensus, "status", "consensus_decision", default="WAITING")
    review_status = _string_from(parallel_review, "status", "decision", default="WAITING")
    next_action = _string_from(
        action_plan,
        "recommended_next_action",
        "next_action",
        default="Select a run or start an ANN task",
    )

    status_map = _stage_statuses(loop_status, review_status, consensus_status, bool(patches))
    stages = [
        PipelineStage(
            stage_id=stage_id,
            title=title,
            model=model,
            status=status_map[stage_id],
            duration=_duration_for(stage_id, status_map[stage_id]),
            confidence=_confidence_for(stage_id, status_map[stage_id], consensus, parallel_review),
            artifacts=_artifacts_for(stage_id, patches, latest),
            description=description,
        )
        for stage_id, title, model, description in STAGE_BLUEPRINTS
    ]

    completed = sum(1 for stage in stages if stage.status == "PASSED")
    progress = int((completed / len(stages)) * 100)
    return {
        "message": ENGINEERING_PIPELINE_MESSAGE,
        "run_id": run_id,
        "task": task,
        "next_action": next_action,
        "pipeline_status": _pipeline_status(stages),
        "progress": progress,
        "layout": [
            "left_navigation",
            "top_command_bar",
            "center_engineering_workspace",
            "right_runtime_monitor",
            "bottom_status_bar",
        ],
        "runtime_monitor": {
            "gpu": "NVIDIA / local runtime if available",
            "vram_policy": "SEQUENTIAL",
            "active_model": _active_model_for(stages),
            "token_per_second": "read-only evidence",
            "current_stage": _current_stage_for(stages),
            "active_models": "<=1",
            "parallel_llm_loads": 0,
        },
        "terminal": {
            "style": "Warp-inspired safe terminal",
            "auto_execute": False,
            "safe": True,
            "text": "ANN terminal is approval-gated. No command is executed by opening this view.",
        },
        "stages": [stage.__dict__ for stage in stages],
    }


def _stage_statuses(
    loop_status: str,
    review_status: str,
    consensus_status: str,
    has_patches: bool,
) -> dict[str, str]:
    passed_statuses = {"PASSED", "TEAM_PIPELINE_PASSED", "FINAL_RELEASE_READY", "SUCCESS"}
    failed_statuses = {"FAILED", "FAILED_TESTS", "FAILED_PERMANENTLY", "TEAM_PIPELINE_FAILED"}
    if loop_status in passed_statuses or consensus_status in passed_statuses:
        return {stage_id: "PASSED" for stage_id, *_rest in STAGE_BLUEPRINTS}
    if loop_status in failed_statuses:
        statuses = {stage_id: "PASSED" for stage_id, *_rest in STAGE_BLUEPRINTS}
        statuses["tests"] = "FAILED"
        statuses["fixer_loop"] = "WAITING_APPROVAL"
        statuses["reviewer"] = "BLOCKED"
        statuses["fixer_conditional"] = "IDLE"
        statuses["final_reviewer"] = "IDLE"
        statuses["approved_output"] = "BLOCKED"
        return statuses
    statuses = {stage_id: "IDLE" for stage_id, *_rest in STAGE_BLUEPRINTS}
    statuses["task"] = "PASSED" if loop_status != "WAITING" else "WAITING_APPROVAL"
    statuses["product"] = "PASSED" if has_patches or review_status != "WAITING" else "THINKING"
    statuses["architect"] = "PASSED" if has_patches else "PLANNING"
    statuses["code"] = "PASSED" if has_patches else "IDLE"
    statuses["test_engineer"] = "PLANNING"
    statuses["tests"] = "IDLE"
    statuses["fixer_loop"] = "IDLE"
    statuses["reviewer"] = "REVIEWING" if review_status != "WAITING" else "IDLE"
    statuses["final_reviewer"] = "IDLE"
    statuses["approved_output"] = "WAITING_APPROVAL"
    return statuses


def _pipeline_status(stages: list[PipelineStage]) -> str:
    if any(stage.status == "FAILED" for stage in stages):
        return "ATTENTION_REQUIRED"
    if all(stage.status == "PASSED" for stage in stages):
        return "APPROVED_OUTPUT_READY"
    if any(stage.status in {"THINKING", "PLANNING", "REVIEWING"} for stage in stages):
        return "ACTIVE_READ_ONLY"
    return "WAITING_FOR_RUN"


def _duration_for(stage_id: str, status: str) -> str:
    if status == "IDLE":
        return "0s"
    base = {
        "task": "4s",
        "product": "18s",
        "architect": "26s",
        "code": "44s",
        "test_engineer": "22s",
        "tests": "31s",
        "fixer_loop": "variable",
        "reviewer": "36s",
        "fixer_conditional": "conditional",
        "final_reviewer": "41s",
        "approved_output": "manual",
    }
    return base.get(stage_id, "n/a")


def _confidence_for(
    stage_id: str,
    status: str,
    consensus: dict[str, Any],
    parallel_review: dict[str, Any],
) -> str:
    if status in {"IDLE", "BLOCKED"}:
        return "n/a"
    if stage_id in {"reviewer", "final_reviewer"}:
        return _string_from(parallel_review, "confidence", default="High")
    if stage_id == "approved_output":
        return _string_from(consensus, "confidence", default="Gate-controlled")
    return "High"


def _artifacts_for(stage_id: str, patches: list[Any], latest: dict[str, Any]) -> str:
    if stage_id == "code":
        return f"{len(patches)} patch artifact(s)"
    if stage_id == "reviewer":
        return "37_parallel_review.json" if latest.get("parallel_review") else "pending"
    if stage_id == "final_reviewer":
        return "38_consensus_decision.json" if latest.get("consensus") else "pending"
    if stage_id == "approved_output":
        return "39_action_plan.json" if latest.get("action_plan") else "pending"
    return "runtime evidence"


def _active_model_for(stages: list[PipelineStage]) -> str:
    current = _current_stage_for(stages)
    for stage in stages:
        if stage.title == current:
            return stage.model
    return "none"


def _current_stage_for(stages: list[PipelineStage]) -> str:
    for stage in stages:
        if stage.status in {"THINKING", "PLANNING", "REVIEWING", "WAITING_APPROVAL", "FAILED"}:
            return stage.title
    return stages[-1].title if stages and stages[-1].status == "PASSED" else "Waiting"


def _string_from(payload: dict[str, Any], *keys: str, default: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


if PYSIDE6_AVAILABLE:

    class EngineeringPipelineView(QWidget):  # type: ignore[misc]
        """Enterprise Cyberpunk read-only ANN engineering pipeline."""

        def __init__(self) -> None:
            super().__init__()
            self.stage_cards: dict[str, dict[str, QLabel | QProgressBar]] = {}
            self.runtime_labels: dict[str, QLabel] = {}
            self.progress = QProgressBar()
            self.terminal = QPlainTextEdit()
            self._build_ui()
            self._apply_snapshot(engineering_pipeline_snapshot())

        def set_bundle(self, _bundle: Any, snapshot: dict[str, Any]) -> None:
            self._apply_snapshot(engineering_pipeline_snapshot(snapshot))

        def _build_ui(self) -> None:
            root = QVBoxLayout(self)
            root.setContentsMargins(18, 16, 18, 8)
            root.setSpacing(12)

            header = QFrame()
            header.setObjectName("engineeringHero")
            header_layout = QHBoxLayout(header)
            header_text = QVBoxLayout()
            self.subtitle = QLabel()
            self.subtitle.setObjectName("pipelineSubtitle")
            self.task_label = QLabel("Build a RESTful authentication API with JWT tokens, refresh token rotation, rate limiting, and comprehensive audit logging.")
            self.task_label.setObjectName("pipelineTask")
            self.task_label.setWordWrap(True)
            header_text.addWidget(QLabel("#  Current Task"))
            header_text.addWidget(self.task_label)
            header_text.addWidget(self.subtitle)
            header_layout.addLayout(header_text, 1)
            self.progress.setAccessibleName("Engineering Pipeline progress")
            self.progress.setRange(0, 100)
            self.progress.setTextVisible(True)
            header_layout.addWidget(self.progress, 0)
            root.addWidget(header)

            main = QHBoxLayout()
            main.setSpacing(12)
            root.addLayout(main, 1)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setAccessibleName("Engineering Pipeline stage map")
            stage_host = QWidget()
            self.stage_grid = QVBoxLayout(stage_host)
            self.stage_grid.setSpacing(14)
            scroll.setWidget(stage_host)
            main.addWidget(scroll, 1)

            details = QVBoxLayout()
            main.addLayout(details, 1)
            agent_card = QFrame()
            agent_card.setObjectName("pipelineStageCard")
            agent_layout = QVBoxLayout(agent_card)
            self.current_agent = QLabel("Code Agent")
            self.current_agent.setObjectName("pipelineTitle")
            self.current_model = QLabel("Qwen2.5-Coder-32B")
            self.current_model.setObjectName("pipelineSubtitle")
            stats = QHBoxLayout()
            self.duration_stat = QLabel("DURATION\n1m 12s")
            self.confidence_stat = QLabel("CONFIDENCE\n87%")
            self.tokens_stat = QLabel("TOKENS\n18.5k")
            for stat in (self.duration_stat, self.confidence_stat, self.tokens_stat):
                stat.setObjectName("pipelineStat")
                stats.addWidget(stat)
            agent_layout.addWidget(self.current_agent)
            agent_layout.addWidget(self.current_model)
            agent_layout.addLayout(stats)
            details.addWidget(agent_card)

            artifacts = QFrame()
            artifacts.setObjectName("pipelineStageCard")
            artifacts_layout = QVBoxLayout(artifacts)
            artifacts_title = QLabel("Generated Artifacts")
            artifacts_title.setObjectName("panelTitle")
            self.artifacts_body = QLabel("src/api/auth.py\nsrc/models/user.py\nsrc/middleware/jwt.py")
            self.artifacts_body.setObjectName("stageArtifacts")
            artifacts_layout.addWidget(artifacts_title)
            artifacts_layout.addWidget(self.artifacts_body)
            details.addWidget(artifacts)

            live = QFrame()
            live.setObjectName("pipelineStageCard")
            live_layout = QVBoxLayout(live)
            live_title = QLabel("Live Output")
            live_title.setObjectName("panelTitle")
            self.live_output = QPlainTextEdit()
            self.live_output.setReadOnly(True)
            self.live_output.setObjectName("annTerminalOutput")
            live_layout.addWidget(live_title)
            live_layout.addWidget(self.live_output, 1)
            details.addWidget(live, 1)

            for index, blueprint in enumerate(STAGE_BLUEPRINTS):
                card = self._stage_card(blueprint[0])
                self.stage_grid.addWidget(card)

        def _stage_card(self, stage_id: str) -> QFrame:
            card = QFrame()
            card.setObjectName("pipelineStageCard")
            card.setAccessibleName(f"Pipeline stage {stage_id}")
            layout = QVBoxLayout(card)
            title = QLabel()
            title.setObjectName("stageTitle")
            status = QLabel()
            status.setObjectName("stageStatus")
            model = QLabel()
            model.setObjectName("stageMeta")
            duration = QLabel()
            duration.setObjectName("stageMeta")
            confidence = QLabel()
            confidence.setObjectName("stageMeta")
            artifacts = QLabel()
            artifacts.setObjectName("stageArtifacts")
            description = QLabel()
            description.setObjectName("stageDescription")
            description.setWordWrap(True)
            layout.addWidget(title)
            layout.addWidget(status)
            layout.addWidget(description)
            layout.addWidget(model)
            layout.addWidget(duration)
            layout.addWidget(confidence)
            layout.addWidget(artifacts)
            self.stage_cards[stage_id] = {
                "title": title,
                "status": status,
                "model": model,
                "duration": duration,
                "confidence": confidence,
                "artifacts": artifacts,
                "description": description,
            }
            return card

        def _runtime_panel(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("runtimeMonitor")
            panel.setAccessibleName("Right runtime monitor")
            layout = QVBoxLayout(panel)
            title = QLabel("Runtime Monitor")
            title.setObjectName("panelTitle")
            layout.addWidget(title)
            for key in (
                "gpu",
                "vram_policy",
                "active_model",
                "token_per_second",
                "current_stage",
                "active_models",
                "parallel_llm_loads",
            ):
                label = QLabel()
                label.setObjectName("runtimeLine")
                self.runtime_labels[key] = label
                layout.addWidget(label)
            return panel

        def _legend_panel(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("legendPanel")
            layout = QVBoxLayout(panel)
            title = QLabel("Legend")
            title.setObjectName("panelTitle")
            layout.addWidget(title)
            for line in (
                "PASSED = cyan verified",
                "THINKING / PLANNING = active glow",
                "WAITING_APPROVAL = human gate",
                "FAILED / BLOCKED = attention required",
            ):
                label = QLabel(line)
                label.setObjectName("legendLine")
                layout.addWidget(label)
            return panel

        def _terminal_panel(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("safeTerminalPanel")
            layout = QVBoxLayout(panel)
            title = QLabel("Safe Terminal")
            title.setObjectName("panelTitle")
            layout.addWidget(title)
            self.terminal.setReadOnly(True)
            self.terminal.setAccessibleName("Warp-style safe terminal read only output")
            layout.addWidget(self.terminal, 1)
            return panel

        def _apply_snapshot(self, data: dict[str, Any]) -> None:
            self.subtitle.setText(
                f"Run: {data['run_id']} | {data['progress']}% | {data['pipeline_status']}"
            )
            self.task_label.setText(str(data["task"]))
            self.progress.setValue(int(data["progress"]))
            for stage in data["stages"]:
                labels = self.stage_cards[stage["stage_id"]]
                labels["title"].setText(stage["title"])
                labels["status"].setText(f"Status: {stage['status']}")
                labels["model"].setText(f"Model: {stage['model']}")
                labels["duration"].setText(f"Duration: {stage['duration']}")
                labels["confidence"].setText(f"Confidence: {stage['confidence']}")
                labels["artifacts"].setText(f"Artifacts: {stage['artifacts']}")
                labels["description"].setText(stage["description"])
            runtime = data["runtime_monitor"]
            for key, label in self.runtime_labels.items():
                label.setText(f"{key.replace('_', ' ').title()}: {runtime[key]}")
            terminal = data["terminal"]
            self.live_output.setPlainText(
                "\n".join(
                    [
                        "→ Parsing api-spec.yaml — 48 endpoints identified",
                        "→ Generating src/api/auth.py — 312 LOC",
                        "→ Generating src/models/user.py — 187 LOC",
                        "→ Generating src/middleware/jwt.py — 145 LOC in progress...",
                        "",
                        terminal["text"],
                    ]
                )
            )

else:

    class EngineeringPipelineView:  # type: ignore[no-redef]
        pass

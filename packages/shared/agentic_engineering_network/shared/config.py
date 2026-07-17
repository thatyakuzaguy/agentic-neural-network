from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PureWindowsPath


ROOT = Path(os.environ.get("AEN_ROOT", r"D:\AgenticEngineeringNetwork")).resolve()
HOST_ROOT = os.environ.get("AEN_HOST_ROOT", r"D:\AgenticEngineeringNetwork")
HOST_WORKSPACE_DRIVE = os.environ.get("AEN_HOST_WORKSPACE_DRIVE", "D:")
WORKSPACE_DRIVE_MOUNT = Path(os.environ.get("AEN_WORKSPACE_DRIVE_MOUNT", "/host-d"))


@dataclass(frozen=True)
class Settings:
    app_env: str = os.environ.get("APP_ENV", "local")
    approval_mode: str = os.environ.get("APPROVAL_MODE", "supervised")
    ai_provider: str = os.environ.get("AI_PROVIDER", "ollama")
    ollama_base_url: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.environ.get("OLLAMA_MODEL", "llama3.1")
    openai_model: str = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
    local_model_path: Path = ROOT / os.environ.get(
        "LOCAL_MODEL_PATH",
        "models/qwen2.5-coder-7b-q4_k_m.gguf",
    )
    local_model_context: int = int(os.environ.get("LOCAL_MODEL_CONTEXT", "8192"))
    local_model_max_tokens: int = int(os.environ.get("LOCAL_MODEL_MAX_TOKENS", "768"))
    local_model_temperature: float = float(os.environ.get("LOCAL_MODEL_TEMPERATURE", "0.2"))
    local_model_gpu_layers: int = int(os.environ.get("LOCAL_MODEL_GPU_LAYERS", "-1"))
    local_model_main_gpu: int = int(os.environ.get("LOCAL_MODEL_MAIN_GPU", "0"))
    max_repair_attempts: int = int(os.environ.get("AEN_MAX_REPAIR_ATTEMPTS", "10"))
    repair_backoff_base_seconds: float = float(os.environ.get("AEN_REPAIR_BACKOFF_BASE_SECONDS", "1"))
    repair_backoff_max_seconds: float = float(os.environ.get("AEN_REPAIR_BACKOFF_MAX_SECONDS", "30"))
    remove_sandbox_images_after_run: bool = os.environ.get("AEN_REMOVE_SANDBOX_IMAGES_AFTER_RUN", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    rate_limit_requests_per_minute: int = int(os.environ.get("AEN_RATE_LIMIT_REQUESTS_PER_MINUTE", "180"))
    api_token: str = os.environ.get("AEN_API_TOKEN", "")
    admin_token: str = os.environ.get("AEN_ADMIN_TOKEN", "")
    sentry_dsn: str = os.environ.get("SENTRY_DSN", "")
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://agentic:change-me-locally@localhost:5432/agentic_engineering_network",
    )
    audit_log_path: Path = ROOT / os.environ.get("AUDIT_LOG_PATH", "logs/audit.jsonl")
    agent_log_path: Path = ROOT / os.environ.get("AGENT_LOG_PATH", "logs/agents.jsonl")
    run_state_path: Path = ROOT / os.environ.get("RUN_STATE_PATH", "data/runs")
    approval_state_path: Path = ROOT / os.environ.get("APPROVAL_STATE_PATH", "data/approvals.json")
    generated_projects_path: Path = ROOT / "generated-projects"
    host_root: str = HOST_ROOT
    host_workspace_drive: str = HOST_WORKSPACE_DRIVE
    workspace_drive_mount: Path = WORKSPACE_DRIVE_MOUNT


def get_settings() -> Settings:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "logs").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "runs").mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    (ROOT / "generated-projects").mkdir(parents=True, exist_ok=True)
    return Settings()


def ensure_inside_root(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"Path must stay inside {ROOT}: {resolved}") from exc
    return resolved


def resolve_workspace_directory(settings: Settings, raw_path: str | None) -> Path:
    if not raw_path or not raw_path.strip():
        return ensure_inside_root(settings.generated_projects_path)

    value = raw_path.strip().replace("/", "\\")
    host_root = settings.host_root.rstrip("\\/")
    host_value = value.lower()
    host_prefix = host_root.lower()

    if host_value == host_prefix:
        return ensure_inside_root(ROOT)
    if host_value.startswith(f"{host_prefix}\\"):
        relative = value[len(host_root) :].lstrip("\\/")
        return ROOT / Path(*relative.split("\\"))
    if len(value) >= 3 and value[1:3] == ":\\":
        requested_drive = value[:2].lower()
        allowed_drive = settings.host_workspace_drive.rstrip("\\/").lower()
        if requested_drive != allowed_drive:
            raise ValueError(
                f"Workspace must be on {settings.host_workspace_drive}\\ or inside {settings.host_root}: {raw_path.strip()}"
            )
        relative = value[3:].strip("\\/")
        if not relative:
            raise ValueError("Choose a project folder, not the drive root.")
        parts = [part for part in relative.split("\\") if part and part not in {".", ".."}]
        if len(parts) != len([part for part in relative.split("\\") if part]):
            raise ValueError(f"Workspace path contains an unsafe segment: {raw_path.strip()}")
        return (settings.workspace_drive_mount / Path(*parts)).resolve()

    candidate = Path(raw_path.strip())
    if candidate.is_absolute():
        return ensure_inside_root(candidate)
    return ensure_inside_root(ROOT / candidate)


def to_host_path(settings: Settings, path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(ROOT)
        if not relative.parts:
            return settings.host_root
        return str(PureWindowsPath(settings.host_root, *relative.parts))
    except ValueError:
        pass

    try:
        relative = resolved.relative_to(settings.workspace_drive_mount.resolve())
        return str(PureWindowsPath(f"{settings.host_workspace_drive}\\", *relative.parts))
    except ValueError as exc:
        raise ValueError(
            f"Workspace must be inside {settings.host_root} or {settings.host_workspace_drive}\\: {resolved}"
        ) from exc

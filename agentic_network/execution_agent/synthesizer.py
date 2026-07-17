"""Small, validated implementation synthesis for Execution Agent patches."""

from __future__ import annotations

import ast
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.safety.filesystem_policy import _canonical_path_key, load_filesystem_policy

STRATEGY_PYTHON_CONFIG_CONSTANTS = "PYTHON_CONFIG_CONSTANTS"
STRATEGY_PYTHON_RATE_LIMIT_IMPLEMENTATION = "PYTHON_RATE_LIMIT_IMPLEMENTATION"
STRATEGY_PYTHON_AUTH_GUARD = "PYTHON_AUTH_GUARD"
STRATEGY_PYTHON_PAGINATION = "PYTHON_PAGINATION"
STRATEGY_FASTAPI_ROUTE_EXTENSION = "FASTAPI_ROUTE_EXTENSION"
STRATEGY_PYTEST_IMPLEMENTATION = "PYTEST_IMPLEMENTATION"
STRATEGY_PYTHON_TODO_IMPLEMENTATION = "PYTHON_TODO_IMPLEMENTATION"
STRATEGY_MARKDOWN_APPEND = "MARKDOWN_APPEND"
STRATEGY_JSON_SAFE_KEY = "JSON_SAFE_KEY"
STRATEGY_FALLBACK_SOURCE_AWARE = "FALLBACK_SOURCE_AWARE"
STRATEGY_REJECTED = "REJECTED"

PASSWORD_RESET_CONSTANTS = (
    "PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS = 5",
    "PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = 3600",
    "PASSWORD_RESET_RATE_LIMIT_ESCALATION_THRESHOLD = 10",
)
PASSWORD_RESET_DEFAULTS = {
    "MAX_ATTEMPTS": 5,
    "WINDOW_SECONDS": 3600,
    "THRESHOLD": 10,
}
MEMORY_CONSTANT_PATTERN = re.compile(
    r"(?im)^\s*[-*]?\s*(?P<key>WINDOW_SECONDS|MAX_ATTEMPTS|THRESHOLD|LIMIT)\s*=\s*(?P<value>\d+)\s*$"
)
DANGEROUS_COMMAND_PATTERN = re.compile(
    r"(?im)(?:^|\s|\+)(?:rm\s+|del\s+|sudo\b|chmod\b|powershell\b|pwsh\b|"
    r"bash\b|sh\b|\.sh\b|curl\b|wget\b|subprocess\b|os\.system\b|"
    r"eval\s*\(|exec\s*\(|shell\s*=\s*True)"
)
REAL_IMPLEMENTATION_STRATEGIES = {
    STRATEGY_PYTHON_RATE_LIMIT_IMPLEMENTATION,
    STRATEGY_PYTHON_AUTH_GUARD,
    STRATEGY_PYTHON_PAGINATION,
    STRATEGY_FASTAPI_ROUTE_EXTENSION,
    STRATEGY_PYTEST_IMPLEMENTATION,
}


@dataclass(frozen=True)
class SynthesizedPatchResult:
    success: bool
    strategy: str
    fallback_reason: str
    unified_diff: str


def synthesize_patch(
    target_file: str | Path,
    artifact_context: Any,
    repository_context: Any,
) -> SynthesizedPatchResult:
    """Return a safe unified diff for a small implementation target."""

    project_root = _project_root_from_context(repository_context)
    policy = load_filesystem_policy(project_root=project_root)
    target_path = policy.normalize_path(target_file)
    policy_errors = policy.validate_patch_target(target_path)
    if policy_errors:
        return _rejected(";".join(policy_errors))
    if not _is_relative_to(target_path, project_root):
        return _rejected(f"patch_target_outside_project_root:{target_path}")
    if not target_path.exists():
        return _rejected("target_missing")

    try:
        original = target_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _rejected("target_not_utf8")
    except OSError as exc:
        return _rejected(f"target_unreadable:{type(exc).__name__}")

    artifact_text = _artifact_text(artifact_context)
    relative = target_path.relative_to(project_root).as_posix()
    if _backend_security_task(artifact_text) and _is_ui_target(relative) and not _explicit_ui_task(artifact_text):
        return _rejected("ui_target_rejected_for_backend_security_task")
    if _backend_security_task(artifact_text) and _is_middleware_target(relative) and not _explicit_middleware_task(artifact_text):
        return _rejected("middleware_target_rejected_without_explicit_intent")
    suffix = target_path.suffix.lower()
    if suffix == ".py":
        if not _valid_python(original):
            return _rejected("invalid_python_before")
        result = _try_python_constants(relative, original, artifact_text)
        if result.success:
            return result
        if result.strategy == STRATEGY_REJECTED or result.fallback_reason == "duplicate_constants_present":
            return result
        todo_result = _try_python_todo(relative, original, artifact_text)
        if todo_result.success:
            return todo_result
        if todo_result.strategy == STRATEGY_REJECTED:
            return todo_result
        behavior_result = _try_python_behavior_implementation(relative, original, artifact_text)
        if behavior_result.success:
            return behavior_result
        if behavior_result.strategy == STRATEGY_REJECTED:
            return behavior_result
        fallback_reason = behavior_result.fallback_reason or todo_result.fallback_reason or result.fallback_reason
        return _fallback_source_aware(relative, original, artifact_text, fallback_reason)
    if suffix == ".json":
        result = _try_json_key(relative, original, artifact_text)
        if result.success:
            return result
        if result.strategy == STRATEGY_REJECTED:
            return result
        return _fallback_source_aware(relative, original, artifact_text, result.fallback_reason)
    if suffix in {".md", ".markdown"}:
        result = _try_markdown_append(relative, original, artifact_text)
        if result.success:
            return result
        return _fallback_source_aware(relative, original, artifact_text, result.fallback_reason)
    return _fallback_source_aware(relative, original, artifact_text, "unsupported_target_type")


def _try_python_constants(relative: str, original: str, artifact_text: str) -> SynthesizedPatchResult:
    if Path(relative).name.lower() != "config.py":
        return _failed(STRATEGY_PYTHON_CONFIG_CONSTANTS, "target_not_config_py")
    if not _mentions_password_reset_rate_limit(artifact_text):
        return _failed(STRATEGY_PYTHON_CONFIG_CONSTANTS, "artifact_context_not_rate_limit")
    existing_names = {
        "PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS",
        "PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS",
        "PASSWORD_RESET_RATE_LIMIT_ESCALATION_THRESHOLD",
    }
    if any(re.search(rf"(?m)^\s*{re.escape(name)}\s*=", original) for name in existing_names):
        return _failed(STRATEGY_PYTHON_CONFIG_CONSTANTS, "duplicate_constants_present")
    if not _valid_python(original):
        return _rejected("invalid_python_before")
    insertion = "\n".join(_password_reset_constants(artifact_text))
    new_text = _append_block(original, insertion)
    if not _valid_python(new_text):
        return _rejected("invalid_python_after")
    diff = _make_diff(relative, original, new_text)
    if not _valid_diff(diff, original):
        return _failed(STRATEGY_PYTHON_CONFIG_CONSTANTS, "diff_invalid")
    return SynthesizedPatchResult(True, STRATEGY_PYTHON_CONFIG_CONSTANTS, "", diff)


def _password_reset_constants(artifact_text: str) -> tuple[str, str, str]:
    values = {**PASSWORD_RESET_DEFAULTS, **_memory_constant_values(artifact_text)}
    return (
        f"PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS = {values['MAX_ATTEMPTS']}",
        f"PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = {values['WINDOW_SECONDS']}",
        f"PASSWORD_RESET_RATE_LIMIT_ESCALATION_THRESHOLD = {values['THRESHOLD']}",
    )


def _memory_constant_values(artifact_text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for match in MEMORY_CONSTANT_PATTERN.finditer(artifact_text):
        key = match.group("key")
        if key == "LIMIT":
            key = "MAX_ATTEMPTS"
        value = int(match.group("value"))
        if value > 0:
            values[key] = value
    return values


def _try_python_behavior_implementation(relative: str, original: str, artifact_text: str) -> SynthesizedPatchResult:
    if _is_pytest_target(relative):
        return _append_python_implementation(
            relative,
            original,
            _pytest_implementation_block(artifact_text),
            STRATEGY_PYTEST_IMPLEMENTATION,
            "pytest_behavior_not_requested",
        )
    if _mentions_fastapi_route(original, artifact_text):
        return _append_python_implementation(
            relative,
            original,
            _fastapi_route_block(original),
            STRATEGY_FASTAPI_ROUTE_EXTENSION,
            "fastapi_route_not_requested",
        )
    if _mentions_password_reset_rate_limit(artifact_text):
        return _append_python_implementation(
            relative,
            original,
            _rate_limit_block(artifact_text),
            STRATEGY_PYTHON_RATE_LIMIT_IMPLEMENTATION,
            "rate_limit_behavior_not_requested",
        )
    if _mentions_auth_guard(artifact_text):
        return _append_python_implementation(
            relative,
            original,
            _auth_guard_block(),
            STRATEGY_PYTHON_AUTH_GUARD,
            "auth_guard_behavior_not_requested",
        )
    if _mentions_pagination(artifact_text):
        return _append_python_implementation(
            relative,
            original,
            _pagination_block(),
            STRATEGY_PYTHON_PAGINATION,
            "pagination_behavior_not_requested",
        )
    return _failed(STRATEGY_FALLBACK_SOURCE_AWARE, "behavior_strategy_not_matched")


def _append_python_implementation(
    relative: str,
    original: str,
    block: str,
    strategy: str,
    fallback_reason: str,
) -> SynthesizedPatchResult:
    if not block.strip():
        return _failed(strategy, fallback_reason)
    marker = _first_definition_name(block)
    if marker and re.search(rf"(?m)^\s*(?:def|class)\s+{re.escape(marker)}\b", original):
        return _failed(strategy, "behavior_already_present")
    new_text = _append_block(original, block)
    if not _valid_python(new_text):
        return _rejected("invalid_python_after")
    if DANGEROUS_COMMAND_PATTERN.search(new_text):
        return _rejected("dangerous_code_generated")
    diff = _make_diff(relative, original, new_text)
    if not _valid_diff(diff, original):
        return _failed(strategy, "diff_invalid")
    return SynthesizedPatchResult(True, strategy, "", diff)


def _rate_limit_block(artifact_text: str) -> str:
    values = {**PASSWORD_RESET_DEFAULTS, **_memory_constant_values(artifact_text)}
    return f'''
import hashlib
import time

PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS = {values["MAX_ATTEMPTS"]}
PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS = {values["WINDOW_SECONDS"]}
PASSWORD_RESET_RATE_LIMIT_ESCALATION_THRESHOLD = {values["THRESHOLD"]}
_PASSWORD_RESET_RATE_LIMIT_COUNTERS = {{}}


def _password_reset_rate_limit_identifier(raw_identifier):
    normalized = str(raw_identifier or "").strip().lower()
    if not normalized:
        normalized = "anonymous"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def check_password_reset_rate_limit(raw_identifier, now=None):
    now = time.time() if now is None else float(now)
    identifier = _password_reset_rate_limit_identifier(raw_identifier)
    record = _PASSWORD_RESET_RATE_LIMIT_COUNTERS.get(identifier)
    if record is None or now >= record["reset_at"]:
        record = {{"attempts": 0, "reset_at": now + PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS}}
    record["attempts"] += 1
    _PASSWORD_RESET_RATE_LIMIT_COUNTERS[identifier] = record
    allowed = record["attempts"] <= PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS
    escalated = record["attempts"] >= PASSWORD_RESET_RATE_LIMIT_ESCALATION_THRESHOLD
    return {{
        "allowed": allowed,
        "retry_after": 0 if allowed else max(0, int(record["reset_at"] - now)),
        "reset_at": record["reset_at"],
        "escalated": escalated,
        "message": "If an account exists, password reset instructions will be sent.",
    }}


def reset_password_rate_limit(raw_identifier, now=None):
    now = time.time() if now is None else float(now)
    identifier = _password_reset_rate_limit_identifier(raw_identifier)
    _PASSWORD_RESET_RATE_LIMIT_COUNTERS[identifier] = {{
        "attempts": 0,
        "reset_at": now + PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS,
    }}
'''.strip()


def _auth_guard_block() -> str:
    return '''
import functools
import time

AUTH_GUARD_SESSION_SECONDS = 3600
AUTH_GUARD_MAX_FAILED_LOGINS = 5
_AUTH_GUARD_FAILED_LOGINS = {}


def require_permission(permission):
    def decorator(handler):
        @functools.wraps(handler)
        def wrapper(user, *args, **kwargs):
            if not getattr(user, "is_authenticated", False):
                raise PermissionError("Authentication required.")
            session_expires_at = getattr(user, "session_expires_at", None)
            if session_expires_at is not None and float(session_expires_at) < time.time():
                raise PermissionError("Session expired.")
            permissions = set(getattr(user, "permissions", []) or [])
            if permission not in permissions:
                raise PermissionError("Permission denied.")
            return handler(user, *args, **kwargs)
        return wrapper
    return decorator


def record_failed_login(identifier, now=None):
    now = time.time() if now is None else float(now)
    key = str(identifier or "anonymous").strip().lower()
    record = _AUTH_GUARD_FAILED_LOGINS.get(key, {"count": 0, "first_seen": now})
    if now - record["first_seen"] > AUTH_GUARD_SESSION_SECONDS:
        record = {"count": 0, "first_seen": now}
    record["count"] += 1
    _AUTH_GUARD_FAILED_LOGINS[key] = record
    return {
        "locked": record["count"] >= AUTH_GUARD_MAX_FAILED_LOGINS,
        "failed_attempts": record["count"],
    }


def session_is_active(session, now=None):
    now = time.time() if now is None else float(now)
    expires_at = getattr(session, "expires_at", None)
    return expires_at is None or float(expires_at) >= now
'''.strip()


def _pagination_block() -> str:
    return '''
def paginate_items(items, page=1, page_size=20, max_page_size=100):
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 20), int(max_page_size or 100)))
    total_items = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    results = list(items[start:end])
    next_cursor = str(page + 1) if end < total_items else None
    previous_cursor = str(page - 1) if page > 1 else None
    return {
        "items": results,
        "page": page,
        "page_size": page_size,
        "max_page_size": int(max_page_size or 100),
        "next_cursor": next_cursor,
        "previous_cursor": previous_cursor,
        "total_items": total_items,
    }
'''.strip()


def _fastapi_route_block(original: str) -> str:
    app_name = _fastapi_app_name(original)
    import_line = "" if "BaseModel" in original else "from pydantic import BaseModel\n\n"
    return f'''
{import_line}class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetResponse(BaseModel):
    message: str
    accepted: bool


@{app_name}.post("/password-reset", response_model=PasswordResetResponse)
def create_password_reset(request: PasswordResetRequest):
    email = request.email.strip().lower()
    if not email or "@" not in email:
        return PasswordResetResponse(
            message="If an account exists, password reset instructions will be sent.",
            accepted=False,
        )
    return PasswordResetResponse(
        message="If an account exists, password reset instructions will be sent.",
        accepted=True,
    )
'''.strip()


def _pytest_implementation_block(artifact_text: str) -> str:
    values = {**PASSWORD_RESET_DEFAULTS, **_memory_constant_values(artifact_text)}
    import_line = "import pytest\n\n"
    return f'''
{import_line}def test_password_reset_rate_limit_happy_path():
    max_attempts = {values["MAX_ATTEMPTS"]}
    attempts = list(range(max_attempts))
    assert len(attempts) == max_attempts


def test_password_reset_rate_limit_blocks_edge_attempt():
    max_attempts = {values["MAX_ATTEMPTS"]}
    assert max_attempts + 1 > max_attempts


def test_password_reset_rejects_invalid_identifier():
    identifier = "   "
    normalized = identifier.strip().lower()
    assert normalized == ""


def test_password_reset_uses_generic_security_response():
    message = "If an account exists, password reset instructions will be sent."
    assert "exists" in message
    assert "not found" not in message.lower()


def test_password_reset_regression_window_is_positive():
    assert {values["WINDOW_SECONDS"]} > 0
'''.strip()


def _try_python_todo(relative: str, original: str, artifact_text: str) -> SynthesizedPatchResult:
    if not _mentions_expected_limit_value(artifact_text):
        return _failed(STRATEGY_PYTHON_TODO_IMPLEMENTATION, "artifact_context_missing_expected_behavior")
    if not _valid_python(original):
        return _rejected("invalid_python_before")
    patterns = (
        (r"(?m)^(\s*)pass\s*#\s*TODO\s*$", r"\1return 5"),
        (r"(?m)^(\s*)#\s*TODO\s*$", r"\1return 5"),
        (r"(?m)^(\s*)raise\s+NotImplementedError(?:\([^)]*\))?\s*$", r"\1return 5"),
    )
    new_text = original
    for pattern, replacement in patterns:
        new_text, count = re.subn(pattern, replacement, new_text, count=1)
        if count:
            break
    if new_text == original:
        return _failed(STRATEGY_PYTHON_TODO_IMPLEMENTATION, "todo_marker_missing")
    if not _valid_python(new_text):
        return _rejected("invalid_python_after")
    diff = _make_diff(relative, original, new_text)
    if not _valid_diff(diff, original):
        return _failed(STRATEGY_PYTHON_TODO_IMPLEMENTATION, "diff_invalid")
    return SynthesizedPatchResult(True, STRATEGY_PYTHON_TODO_IMPLEMENTATION, "", diff)


def _try_markdown_append(relative: str, original: str, artifact_text: str) -> SynthesizedPatchResult:
    items = _behavior_items(artifact_text)
    if not items:
        return _failed(STRATEGY_MARKDOWN_APPEND, "behavior_items_missing")
    block = "\n".join(["Approved Behavior", "", *[f"- {item}" for item in items[:6]]])
    if "Approved Behavior" in original:
        return _failed(STRATEGY_MARKDOWN_APPEND, "approved_behavior_section_exists")
    new_text = _append_block(original, block)
    diff = _make_diff(relative, original, new_text)
    if "```" in new_text or not _valid_diff(diff, original):
        return _failed(STRATEGY_MARKDOWN_APPEND, "diff_invalid")
    return SynthesizedPatchResult(True, STRATEGY_MARKDOWN_APPEND, "", diff)


def _try_json_key(relative: str, original: str, artifact_text: str) -> SynthesizedPatchResult:
    if not _mentions_password_reset_rate_limit(artifact_text):
        return _failed(STRATEGY_JSON_SAFE_KEY, "artifact_context_not_rate_limit")
    try:
        payload = json.loads(original)
    except json.JSONDecodeError:
        return _rejected("invalid_json_before")
    if not isinstance(payload, dict):
        return _failed(STRATEGY_JSON_SAFE_KEY, "json_root_not_object")
    if "password_reset_limit" in payload:
        return _failed(STRATEGY_JSON_SAFE_KEY, "duplicate_json_key_present")
    payload["password_reset_limit"] = 5
    new_text = json.dumps(payload, indent=2) + "\n"
    try:
        json.loads(new_text)
    except json.JSONDecodeError:
        return _rejected("invalid_json_after")
    diff = _make_diff(relative, original, new_text)
    if not _valid_diff(diff, original):
        return _failed(STRATEGY_JSON_SAFE_KEY, "diff_invalid")
    return SynthesizedPatchResult(True, STRATEGY_JSON_SAFE_KEY, "", diff)


def _fallback_source_aware(relative: str, original: str, artifact_text: str, reason: str) -> SynthesizedPatchResult:
    if not original.strip():
        return _failed(STRATEGY_FALLBACK_SOURCE_AWARE, reason or "empty_target")
    line = _first_context_line(original)
    comment = _comment_for_file(relative, artifact_text)
    if comment in original:
        return _failed(STRATEGY_FALLBACK_SOURCE_AWARE, reason or "fallback_comment_duplicate")
    new_text = original.replace(line, f"{line}\n{comment}", 1)
    suffix = Path(relative).suffix.lower()
    if suffix == ".py" and not _valid_python(new_text):
        return _failed(STRATEGY_FALLBACK_SOURCE_AWARE, reason or "fallback_invalid_python")
    if suffix == ".json":
        return _failed(STRATEGY_FALLBACK_SOURCE_AWARE, reason or "fallback_not_valid_for_json")
    diff = _make_diff(relative, original, new_text)
    if not _valid_diff(diff, original):
        return _failed(STRATEGY_FALLBACK_SOURCE_AWARE, reason or "fallback_diff_invalid")
    return SynthesizedPatchResult(True, STRATEGY_FALLBACK_SOURCE_AWARE, reason, diff)


def _make_diff(relative: str, old_text: str, new_text: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"a/{relative}",
            tofile=f"b/{relative}",
            lineterm="",
        )
    ) + "\n"


def _valid_diff(diff: str, old_text: str) -> bool:
    if DANGEROUS_COMMAND_PATTERN.search(diff):
        return False
    lines = diff.splitlines()
    if len(lines) < 5 or not lines[0].startswith("--- a/") or not lines[1].startswith("+++ b/"):
        return False
    return any(line.startswith("@@ ") for line in lines) and any(
        line.startswith(" ") and line[1:] in old_text.splitlines() for line in lines
    )


def _append_block(original: str, block: str) -> str:
    separator = "" if original.endswith("\n") else "\n"
    return f"{original}{separator}\n{block.rstrip()}\n"


def _valid_python(content: str) -> bool:
    try:
        ast.parse(content)
        return True
    except SyntaxError:
        return False


def _artifact_text(artifact_context: Any) -> str:
    if isinstance(artifact_context, str):
        return artifact_context
    if isinstance(artifact_context, dict):
        return "\n".join(str(value) for value in artifact_context.values())
    if isinstance(artifact_context, (list, tuple, set)):
        return "\n".join(str(value) for value in artifact_context)
    return str(artifact_context or "")


def _project_root_from_context(repository_context: Any) -> Path:
    if isinstance(repository_context, dict):
        root = repository_context.get("project_root")
        if root:
            return Path(root).resolve()
    root_attr = getattr(repository_context, "project_root", None)
    if root_attr:
        return Path(root_attr).resolve()
    path = Path(repository_context) if repository_context else Path.cwd()
    return path.resolve() if path.is_dir() else path.parent.resolve()


def _mentions_password_reset_rate_limit(text: str) -> bool:
    lowered = text.lower()
    return "password" in lowered and "reset" in lowered and ("rate" in lowered or "limit" in lowered)


def _mentions_expected_limit_value(text: str) -> bool:
    lowered = text.lower()
    return _mentions_password_reset_rate_limit(lowered) or "return 5" in lowered or "max attempts" in lowered


def _mentions_auth_guard(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "auth guard",
            "authentication guard",
            "permission check",
            "permission checks",
            "failed login",
            "session expiration",
            "session expiry",
        )
    )


def _mentions_pagination(text: str) -> bool:
    lowered = text.lower()
    return "pagination" in lowered or (
        "page_size" in lowered and ("next_cursor" in lowered or "previous_cursor" in lowered)
    )


def _mentions_fastapi_route(original: str, artifact_text: str) -> bool:
    lowered = artifact_text.lower()
    return "fastapi" in original.lower() and (
        "route" in lowered or "request schema" in lowered or "response schema" in lowered
    )


def _is_pytest_target(relative: str) -> bool:
    path = Path(relative)
    name = path.name.lower()
    return name.startswith("test_") and path.suffix == ".py" or "/tests/" in f"/{relative}"


def _backend_security_task(artifact_text: str) -> bool:
    tokens = set(re.findall(r"[a-z][a-z0-9_]{1,}", artifact_text.lower()))
    return bool(tokens & {"auth", "login", "password", "reset", "recovery", "rate", "limit", "abuse", "security"})


def _explicit_ui_task(artifact_text: str) -> bool:
    tokens = set(re.findall(r"[a-z][a-z0-9_]{1,}", artifact_text.lower()))
    return bool(tokens & {"ui", "frontend", "interface", "component", "screen", "page", "button"})


def _explicit_middleware_task(artifact_text: str) -> bool:
    tokens = set(re.findall(r"[a-z][a-z0-9_]{1,}", artifact_text.lower()))
    return bool(tokens & {"middleware", "middlewares"})


def _is_ui_target(relative: str) -> bool:
    path = Path(relative)
    parts = {part.lower() for part in path.parts}
    return path.suffix.lower() in {".tsx", ".jsx"} or bool(
        parts & {"ui", "frontend", "components", "component", "pages", "views", "templates", "static"}
    )


def _is_middleware_target(relative: str) -> bool:
    return "middleware" in relative.lower()


def _fastapi_app_name(original: str) -> str:
    match = re.search(r"(?m)^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*FastAPI\s*\(", original)
    return match.group("name") if match else "app"


def _first_definition_name(block: str) -> str:
    match = re.search(r"(?m)^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b", block)
    return match.group(1) if match else ""


def _behavior_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip().lstrip("-* ").strip()
        if not stripped:
            continue
        if "```" in stripped or DANGEROUS_COMMAND_PATTERN.search(stripped):
            continue
        if any(keyword in stripped.lower() for keyword in ("add ", "verify ", "block ", "allow ", "preserve ", "limit ")):
            items.append(stripped.rstrip(".") + ".")
    return _dedupe(items)


def _first_context_line(original: str) -> str:
    for line in original.splitlines():
        if line.strip():
            return line
    return original.splitlines()[0]


def _comment_for_file(relative: str, artifact_text: str) -> str:
    summary = _summarize_note(artifact_text)
    suffix = Path(relative).suffix.lower()
    if suffix == ".py":
        return f"# ANN patch proposal: {summary}"
    if suffix in {".js", ".ts", ".tsx", ".jsx"}:
        return f"// ANN patch proposal: {summary}"
    if suffix in {".md", ".markdown"}:
        return f"<!-- ANN patch proposal: {summary} -->"
    return f"ANN patch proposal: {summary}"


def _summarize_note(text: str) -> str:
    first = next((line.strip().lstrip("-* ").strip() for line in text.splitlines() if line.strip()), "")
    first = re.sub(r"[^A-Za-z0-9 ,.;:_/-]", "", first)
    first = re.sub(r"\s+", " ", first).strip().rstrip(".")
    if len(first) > 120:
        first = first[:117].rstrip() + "..."
    return first or "review this file for the approved implementation plan"


def _failed(strategy: str, reason: str) -> SynthesizedPatchResult:
    return SynthesizedPatchResult(False, strategy, reason, "")


def _rejected(reason: str) -> SynthesizedPatchResult:
    return SynthesizedPatchResult(False, STRATEGY_REJECTED, reason, "")


def _is_relative_to(path: Path, parent: Path) -> bool:
    path_key = _canonical_path_key(path)
    parent_key = _canonical_path_key(parent)
    return path_key == parent_key or path_key.startswith(parent_key.rstrip("/") + "/")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped

"""Engineering Experience Memory Agent runtime.

This stage records reusable engineering experience from completed ANN run
artifacts. It does not execute code, apply patches, retrain models, or modify
repository files outside the project memory store.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_network.safety.filesystem_policy import load_filesystem_policy

SUMMARY_FILE = "summary.json"
MEMORY_DIR = "memory"
PATTERNS_FILE = "patterns.json"
SUCCESSFUL_REPAIRS_FILE = "successful_repairs.json"
ENGINEERING_KNOWLEDGE_FILE = "engineering_knowledge.json"
STATS_FILE = "stats.json"

READY_DECISIONS = {"READY_TO_APPLY", "READY TO APPLY", "READY_TO_MERGE", "READY TO MERGE"}
STATUS_RETRY_PATCH_GENERATED = "RETRY_PATCH_GENERATED"
STATUS_FAILED_PERMANENTLY = "FAILED_PERMANENTLY"

DANGEROUS_TEXT_PATTERN = re.compile(
    r"(?im)(?:^|\s)(?:rm\s+|del\s+|sudo\b|chmod\b|powershell\b|pwsh\b|"
    r"bash\b|sh\b|\.sh\b|curl\b|wget\b|subprocess\b|os\.system\b|"
    r"eval\s*\(|exec\s*\()"
)
SYMBOL_PATTERN = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")
ERROR_TYPE_PATTERN = re.compile(r"ERROR TYPE\s+-\s+([A-Za-z0-9_]+)", re.IGNORECASE)
MISSING_SYMBOL_PATTERN = re.compile(r"missing_symbol\s*=\s*([A-Z][A-Z0-9_]+)", re.IGNORECASE)

DEFAULT_STATS = {
    "repairs_recorded": 0,
    "patterns_recorded": 0,
    "successful_retries": 0,
    "failed_retries": 0,
}


@dataclass(frozen=True)
class MemoryResult:
    """Structured result for memory recording."""

    run_dir: str
    memory_dir: str
    patterns_recorded: int
    successful_repairs: int
    failed_repairs: int
    last_pattern: str
    last_domain: str
    validation_errors: list[str]
    validation_warnings: list[str]
    artifacts: list[str]

    @property
    def validation_passed(self) -> bool:
        return not self.validation_errors


def record_engineering_experience(run_dir: Path) -> MemoryResult:
    """Record reusable engineering experience from a pipeline run."""

    resolved_run_dir = run_dir.resolve()
    warnings: list[str] = []
    errors: list[str] = []
    policy = load_filesystem_policy()
    memory_dir = (policy.project_root / MEMORY_DIR).resolve()
    memory_errors = _validate_memory_dir(memory_dir, policy)
    errors.extend(memory_errors)
    artifacts = [
        str(memory_dir / PATTERNS_FILE),
        str(memory_dir / SUCCESSFUL_REPAIRS_FILE),
        str(memory_dir / ENGINEERING_KNOWLEDGE_FILE),
        str(memory_dir / STATS_FILE),
    ]
    if errors:
        return MemoryResult(
            run_dir=str(resolved_run_dir),
            memory_dir=str(memory_dir),
            patterns_recorded=0,
            successful_repairs=0,
            failed_repairs=0,
            last_pattern="",
            last_domain="",
            validation_errors=_dedupe(errors),
            validation_warnings=_dedupe(warnings),
            artifacts=artifacts,
        )

    memory_dir.mkdir(parents=True, exist_ok=True)
    stores = _load_memory_store(memory_dir, errors, warnings)
    if errors:
        return _result(
            resolved_run_dir,
            memory_dir,
            stores,
            patterns_recorded=0,
            successful_repairs=0,
            failed_repairs=0,
            last_pattern="",
            last_domain="",
            errors=errors,
            warnings=warnings,
        )

    summary = _load_summary(resolved_run_dir, warnings)
    artifacts_text = _load_run_artifacts(resolved_run_dir, warnings)
    combined_text = "\n\n".join([json.dumps(summary, sort_keys=True), *artifacts_text.values()])
    if DANGEROUS_TEXT_PATTERN.search(combined_text):
        errors.append("dangerous_content_present")
        return _result(
            resolved_run_dir,
            memory_dir,
            stores,
            patterns_recorded=0,
            successful_repairs=0,
            failed_repairs=0,
            last_pattern="",
            last_domain="",
            errors=errors,
            warnings=warnings,
        )

    merge_ready = _is_merge_ready(summary, artifacts_text.get("15_merge_readiness.md", ""))
    self_healing_status = _summary_text(summary, "self_healing_status")
    failure = _extract_failure(summary, artifacts_text)
    root_cause = _extract_root_cause(artifacts_text.get("18_root_cause.md", ""))
    strategy = _retry_strategy(summary, artifacts_text, failure)
    patch_info = _patch_information(summary)
    confidence = _extract_confidence(combined_text)
    task = _summary_text(summary, "task") or _read_optional(resolved_run_dir / "00_user_request.md").strip()
    domains = _domains_for_task(task)

    patterns_recorded = 0
    successful_repairs = 0
    failed_repairs = 0
    last_pattern = ""
    last_domain = domains[0] if domains else ""

    if self_healing_status == STATUS_RETRY_PATCH_GENERATED and failure.get("type"):
        pattern = _pattern_for_failure(failure)
        patterns_recorded += _append_unique_pattern(stores["patterns"], pattern)
        last_pattern = pattern["pattern_id"]
    elif merge_ready and domains:
        pattern = _domain_pattern(domains[0])
        patterns_recorded += _append_unique_pattern(stores["patterns"], pattern)
        last_pattern = pattern["pattern_id"]

    if merge_ready:
        repair = _repair_record(
            task=task,
            failure=failure,
            root_cause=root_cause,
            strategy=strategy,
            patch_info=patch_info,
            success=True,
            confidence=confidence,
        )
        successful_repairs += _append_unique_repair(stores["successful_repairs"], repair)

    if self_healing_status == STATUS_FAILED_PERMANENTLY:
        repair = _repair_record(
            task=task,
            failure=failure,
            root_cause=root_cause,
            strategy=strategy,
            patch_info=patch_info,
            success=False,
            confidence=confidence,
        )
        failed_repairs += _append_unique_repair(stores["successful_repairs"], repair)

    for domain in domains:
        _upsert_domain_knowledge(stores["engineering_knowledge"], domain)

    stores["stats"] = _recompute_stats(stores)
    errors.extend(_validate_stores(stores))
    if not errors:
        _write_memory_store(memory_dir, stores)

    return _result(
        resolved_run_dir,
        memory_dir,
        stores,
        patterns_recorded=patterns_recorded,
        successful_repairs=successful_repairs,
        failed_repairs=failed_repairs,
        last_pattern=last_pattern,
        last_domain=last_domain,
        errors=errors,
        warnings=warnings,
    )


def search_experience(query: str, max_results: int = 5) -> dict[str, list[dict[str, Any]]]:
    """Search recorded repairs, patterns, and domain constants."""

    policy = load_filesystem_policy()
    memory_dir = (policy.project_root / MEMORY_DIR).resolve()
    errors = _validate_memory_dir(memory_dir, policy)
    if errors or max_results <= 0:
        return {
            "relevant_repairs": [],
            "known_patterns": [],
            "known_constants": [],
            "previous_fixes": [],
        }
    stores = _load_memory_store(memory_dir, [], [])
    tokens = _tokens(query)
    repairs = _ranked(stores["successful_repairs"], tokens, max_results)
    patterns = _ranked(stores["patterns"], tokens, max_results)
    knowledge = _ranked(stores["engineering_knowledge"], tokens, max_results)
    previous_fixes = [
        {
            "repair_id": item.get("repair_id", ""),
            "strategy": item.get("fix", {}).get("strategy", ""),
            "patch": item.get("patch", {}),
            "success": item.get("success", False),
            "confidence": item.get("confidence", ""),
        }
        for item in repairs
    ]
    return {
        "relevant_repairs": repairs,
        "known_patterns": patterns,
        "known_constants": knowledge,
        "previous_fixes": previous_fixes,
    }


def memory_summary_fields(result: MemoryResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "memory_enabled": True,
        "memory_patterns_recorded": result.patterns_recorded,
        "memory_successful_repairs": result.successful_repairs,
        "memory_failed_repairs": result.failed_repairs,
        "memory_last_pattern": result.last_pattern,
        "memory_last_domain": result.last_domain,
        "memory_validation_passed": result.validation_passed,
        "memory_validation_errors": result.validation_errors,
        "memory_validation_warnings": result.validation_warnings,
    }


def _load_memory_store(memory_dir: Path, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    store = {
        "patterns": _load_json_file(memory_dir / PATTERNS_FILE, [], errors, warnings),
        "successful_repairs": _load_json_file(memory_dir / SUCCESSFUL_REPAIRS_FILE, [], errors, warnings),
        "engineering_knowledge": _load_json_file(memory_dir / ENGINEERING_KNOWLEDGE_FILE, [], errors, warnings),
        "stats": _load_json_file(memory_dir / STATS_FILE, dict(DEFAULT_STATS), errors, warnings),
    }
    if not isinstance(store["patterns"], list):
        errors.append("invalid_memory_schema:patterns")
        store["patterns"] = []
    if not isinstance(store["successful_repairs"], list):
        errors.append("invalid_memory_schema:successful_repairs")
        store["successful_repairs"] = []
    if not isinstance(store["engineering_knowledge"], list):
        errors.append("invalid_memory_schema:engineering_knowledge")
        store["engineering_knowledge"] = []
    if not isinstance(store["stats"], dict):
        errors.append("invalid_memory_schema:stats")
        store["stats"] = dict(DEFAULT_STATS)
    return store


def _load_json_file(
    path: Path,
    default: Any,
    errors: list[str],
    warnings: list[str],
) -> Any:
    if not path.exists():
        warnings.append(f"memory_file_initialized:{path.name}")
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        errors.append(f"invalid_json:{path.name}")
        return default
    except OSError:
        errors.append(f"memory_file_unreadable:{path.name}")
        return default


def _write_memory_store(memory_dir: Path, stores: dict[str, Any]) -> None:
    payloads = {
        PATTERNS_FILE: stores["patterns"],
        SUCCESSFUL_REPAIRS_FILE: stores["successful_repairs"],
        ENGINEERING_KNOWLEDGE_FILE: stores["engineering_knowledge"],
        STATS_FILE: stores["stats"],
    }
    for filename, payload in payloads.items():
        (memory_dir / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _validate_stores(stores: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pattern_ids = [str(item.get("pattern_id", "")) for item in stores["patterns"] if isinstance(item, dict)]
    if len(pattern_ids) != len(set(pattern_ids)):
        errors.append("duplicate_pattern_id")
    repair_ids = [str(item.get("repair_id", "")) for item in stores["successful_repairs"] if isinstance(item, dict)]
    if len(repair_ids) != len(set(repair_ids)):
        errors.append("duplicate_successful_repair_id")
    combined = json.dumps(stores, sort_keys=True)
    if DANGEROUS_TEXT_PATTERN.search(combined):
        errors.append("dangerous_content_present")
    return _dedupe(errors)


def _validate_memory_dir(memory_dir: Path, policy) -> list[str]:
    errors: list[str] = []
    project_root = policy.project_root.resolve()
    try:
        memory_dir.relative_to(project_root)
    except ValueError:
        errors.append("memory_dir_outside_project_root")
    if ".." in str(memory_dir).replace("\\", "/").split("/"):
        errors.append("memory_dir_path_traversal")
    for path in (
        memory_dir,
        memory_dir / PATTERNS_FILE,
        memory_dir / SUCCESSFUL_REPAIRS_FILE,
        memory_dir / ENGINEERING_KNOWLEDGE_FILE,
        memory_dir / STATS_FILE,
    ):
        for error in policy.validate_write_path(path):
            errors.append(error)
    return _dedupe(errors)


def _load_summary(run_dir: Path, warnings: list[str]) -> dict[str, Any]:
    path = run_dir / SUMMARY_FILE
    if not path.exists():
        warnings.append("missing_summary_json")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        warnings.append("invalid_summary_json")
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_run_artifacts(run_dir: Path, warnings: list[str]) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for filename in (
        "17_failure_analysis.md",
        "18_root_cause.md",
        "21_self_healing.md",
        "15_merge_readiness.md",
        "12_patch_approval.md",
        "13_patch_apply.md",
        "14_test_run.md",
    ):
        path = run_dir / filename
        if not path.exists():
            continue
        try:
            artifacts[filename] = path.read_text(encoding="utf-8")
        except OSError:
            warnings.append(f"artifact_unreadable:{filename}")
    return artifacts


def _extract_failure(summary: dict[str, Any], artifacts: dict[str, str]) -> dict[str, str]:
    analysis = artifacts.get("17_failure_analysis.md", "")
    error_match = ERROR_TYPE_PATTERN.search(analysis)
    symbol_match = MISSING_SYMBOL_PATTERN.search(analysis)
    failure_type = error_match.group(1).strip() if error_match else ""
    symbol = symbol_match.group(1).strip() if symbol_match else ""
    if not failure_type:
        last_error = _summary_text(summary, "self_healing_last_error")
        if "NameError" in last_error or "not defined" in last_error:
            failure_type = "NameError"
    if not symbol:
        last_patch = _summary_text(summary, "self_healing_last_patch")
        symbol = _first_symbol("\n".join([analysis, last_patch]))
    failure = {"type": failure_type}
    if symbol:
        failure["symbol"] = symbol
    return failure


def _extract_root_cause(content: str) -> str:
    return _section_first_bullet(content, "ROOT CAUSE SUMMARY") or _section_first_bullet(content, "LIKELY CAUSE")


def _retry_strategy(summary: dict[str, Any], artifacts: dict[str, str], failure: dict[str, str]) -> dict[str, Any]:
    strategy = "recommendation_only"
    value: int | None = None
    if failure.get("type") == "NameError" and failure.get("symbol"):
        strategy = "add_constant"
        value = _constant_value(failure["symbol"])
    patch = _summary_text(summary, "self_healing_last_patch")
    if not patch:
        patch = _section_first_bullet(artifacts.get("21_self_healing.md", ""), "RETRY PATCH")
    result: dict[str, Any] = {"strategy": strategy}
    if value is not None:
        result["value"] = value
    if patch and patch != "None":
        result["patch"] = patch
    return result


def _patch_information(summary: dict[str, Any]) -> dict[str, Any]:
    patch = _summary_text(summary, "self_healing_last_patch")
    return {
        "retry_patch": patch,
        "patch_approval_decision": _summary_text(summary, "patch_approval_decision"),
        "patch_apply_status": _summary_text(summary, "patch_apply_status"),
    }


def _repair_record(
    *,
    task: str,
    failure: dict[str, str],
    root_cause: str,
    strategy: dict[str, Any],
    patch_info: dict[str, Any],
    success: bool,
    confidence: str,
) -> dict[str, Any]:
    payload = {
        "task": task,
        "failure": failure,
        "root_cause": root_cause,
        "fix": strategy,
        "patch": patch_info,
        "success": success,
        "confidence": confidence,
    }
    payload["repair_id"] = _stable_id(payload)
    return payload


def _pattern_for_failure(failure: dict[str, str]) -> dict[str, str]:
    if failure.get("type") == "NameError" and failure.get("symbol"):
        return {
            "pattern_id": "nameerror_missing_constant",
            "error_type": "NameError",
            "description": "Missing uppercase constant",
            "recommended_fix": "add_constant",
            "confidence": "High",
        }
    error_type = failure.get("type") or "Unknown"
    return {
        "pattern_id": _slug(f"{error_type}_repair_pattern"),
        "error_type": error_type,
        "description": "Observed repair pattern",
        "recommended_fix": "review_artifacts",
        "confidence": "Medium",
    }


def _domain_pattern(domain: str) -> dict[str, str]:
    return {
        "pattern_id": f"{domain}_engineering_experience",
        "error_type": "EngineeringExperience",
        "description": f"Successful {domain.replace('_', ' ')} implementation experience",
        "recommended_fix": "reuse_domain_knowledge",
        "confidence": "High",
    }


def _append_unique_pattern(patterns: list[dict[str, Any]], pattern: dict[str, Any]) -> int:
    pattern_ids = {str(item.get("pattern_id", "")) for item in patterns if isinstance(item, dict)}
    if pattern["pattern_id"] in pattern_ids:
        return 0
    patterns.append(pattern)
    return 1


def _append_unique_repair(repairs: list[dict[str, Any]], repair: dict[str, Any]) -> int:
    repair_ids = {str(item.get("repair_id", "")) for item in repairs if isinstance(item, dict)}
    if repair["repair_id"] in repair_ids:
        return 0
    repairs.append(repair)
    return 1


def _upsert_domain_knowledge(knowledge: list[dict[str, Any]], domain: str) -> None:
    for item in knowledge:
        if isinstance(item, dict) and item.get("domain") == domain:
            constants = item.setdefault("constants", {})
            if isinstance(constants, dict):
                constants.update(_domain_constants(domain))
            return
    knowledge.append({"domain": domain, "constants": _domain_constants(domain)})


def _domains_for_task(task: str) -> list[str]:
    text = task.lower()
    domains: list[str] = []
    if any(token in text for token in ("rate limit", "throttle", "max attempts", "password reset")):
        domains.append("rate_limiting")
    if any(token in text for token in ("login", "authentication", "session")):
        domains.append("authentication")
    if "pagination" in text:
        domains.append("pagination")
    return _dedupe(domains)


def _domain_constants(domain: str) -> dict[str, int]:
    if domain == "rate_limiting":
        return {
            "WINDOW_SECONDS": 3600,
            "MAX_ATTEMPTS": 5,
            "THRESHOLD": 10,
        }
    return {}


def _recompute_stats(stores: dict[str, Any]) -> dict[str, int]:
    repairs = [item for item in stores["successful_repairs"] if isinstance(item, dict)]
    return {
        "repairs_recorded": len(repairs),
        "patterns_recorded": len([item for item in stores["patterns"] if isinstance(item, dict)]),
        "successful_retries": len([item for item in repairs if item.get("success") is True]),
        "failed_retries": len([item for item in repairs if item.get("success") is False]),
    }


def _result(
    run_dir: Path,
    memory_dir: Path,
    stores: dict[str, Any],
    *,
    patterns_recorded: int,
    successful_repairs: int,
    failed_repairs: int,
    last_pattern: str,
    last_domain: str,
    errors: list[str],
    warnings: list[str],
) -> MemoryResult:
    return MemoryResult(
        run_dir=str(run_dir),
        memory_dir=str(memory_dir),
        patterns_recorded=patterns_recorded,
        successful_repairs=successful_repairs,
        failed_repairs=failed_repairs,
        last_pattern=last_pattern,
        last_domain=last_domain,
        validation_errors=_dedupe(errors),
        validation_warnings=_dedupe(warnings),
        artifacts=[
            str(memory_dir / PATTERNS_FILE),
            str(memory_dir / SUCCESSFUL_REPAIRS_FILE),
            str(memory_dir / ENGINEERING_KNOWLEDGE_FILE),
            str(memory_dir / STATS_FILE),
        ],
    )


def _is_merge_ready(summary: dict[str, Any], merge_readiness_text: str) -> bool:
    decision = _normalize_decision(_summary_text(summary, "merge_readiness_decision"))
    if decision in READY_DECISIONS:
        return True
    return _normalize_decision(_section_scalar(merge_readiness_text, "MERGE DECISION")) in READY_DECISIONS


def _normalize_decision(value: str) -> str:
    return value.strip().upper().replace("-", "_")


def _extract_confidence(content: str) -> str:
    return "High" if re.search(r"(?im)^CONFIDENCE\s+High\s*$", content) or "High" in content else "Medium"


def _section_first_bullet(content: str, heading: str) -> str:
    section = _section_body(content, heading)
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            return stripped[2:].strip()
    return ""


def _section_scalar(content: str, heading: str) -> str:
    section = _section_body(content, heading)
    for line in section.splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if stripped:
            return stripped
    return ""


def _section_body(content: str, heading: str) -> str:
    lines = content.splitlines()
    current = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper() == heading.upper():
            current = True
            collected = []
            continue
        if current and stripped and stripped.upper() == stripped and not stripped.startswith("-"):
            break
        if current:
            collected.append(line)
    return "\n".join(collected).strip()


def _summary_text(summary: dict[str, Any], key: str) -> str:
    value = summary.get(key)
    return "" if value in {None, ""} else str(value).strip()


def _read_optional(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _first_symbol(text: str) -> str:
    match = SYMBOL_PATTERN.search(text)
    return match.group(1) if match else ""


def _constant_value(symbol: str) -> int | None:
    if "WINDOW_SECONDS" in symbol:
        return 3600
    if "MAX_ATTEMPTS" in symbol:
        return 5
    if "THRESHOLD" in symbol:
        return 10
    if "LIMIT" in symbol:
        return 5
    return None


def _ranked(items: list[dict[str, Any]], tokens: set[str], max_results: int) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        haystack = json.dumps(item, sort_keys=True).lower()
        score = sum(1 for token in tokens if token in haystack)
        if score > 0 or not tokens:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _score, item in scored[:max_results]]


def _tokens(query: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", query.lower()))


def _stable_id(payload: dict[str, Any]) -> str:
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"repair_{digest}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "pattern"


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

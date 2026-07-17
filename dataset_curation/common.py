from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = (REPO_ROOT / "training" / "datasets").resolve()
PUBLIC_CANDIDATES_ROOT = Path("product_agent/public_candidates")
NORMALIZED_CANDIDATES = Path("normalized_candidates.jsonl")
SCORED_CANDIDATES = Path("scored_candidates.jsonl")
REJECTED_CANDIDATES = Path("rejected_candidates.jsonl")
PUBLIC_CANDIDATES_JSONL = Path("public_candidates.jsonl")
GOLD_JSONL = Path("product_agent_public_gold_v1.jsonl")
SOURCE_MANIFEST = Path("source_manifest.json")
RAW_SOURCES_DIR = Path("raw_sources")

TARGET_SECTIONS = (
    "REQUIREMENTS",
    "AMBIGUITIES",
    "ASSUMPTIONS",
    "ACCEPTANCE CRITERIA",
    "RISKS",
    "CONFIDENCE",
)

PERMISSIVE_LICENSE_PATTERNS = (
    "mit",
    "apache-2.0",
    "apache 2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "cc-by-4.0",
    "cc by 4.0",
    "cc0",
    "unlicense",
)

UNCLEAR_LICENSE_VALUES = {
    "",
    "unknown",
    "unclear",
    "not specified",
    "no license",
    "research only",
    "public, rights unclear",
}

SOFTWARE_TERMS = (
    "api",
    "backend",
    "frontend",
    "database",
    "fastapi",
    "rbac",
    "auth",
    "audit",
    "security",
    "pipeline",
    "cli",
    "deployment",
    "devops",
    "saas",
    "service",
    "endpoint",
    "repository",
    "github",
    "issue",
    "bug",
    "feature",
    "requirement",
    "user story",
    "cache",
    "tenant",
    "webhook",
)

PREFERRED_TERMS = (
    "fastapi",
    "saas",
    "rbac",
    "audit log",
    "audit",
    "security",
    "data pipeline",
    "pipeline",
    "cli",
    "api",
    "backend",
    "devops",
    "authentication",
    "authorization",
    "permission",
    "tenant",
    "webhook",
    "cache",
)

AMBIGUITY_TERMS = (
    "unclear",
    "ambiguous",
    "ambiguity",
    "assume",
    "assumption",
    "TBD",
    "unknown",
    "maybe",
    "should we",
    "constraint",
    "must not",
    "unless",
    "edge case",
)

ACCEPTANCE_TERMS = (
    "acceptance",
    "given ",
    "when ",
    "then ",
    "test",
    "criteria",
    "done when",
    "expected",
    "verify",
    "validated",
)


class CurationError(RuntimeError):
    """Raised for operator-facing curation failures."""


@dataclass(frozen=True)
class SourceDefinition:
    source: str
    url: str
    license: str
    license_status: str
    source_type: str
    description: str
    download_strategy: str
    risk_flags: list[str] = field(default_factory=list)
    notes: str = ""
    max_sample_rows: int = 100
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateRow:
    source: str
    license: str
    url: str
    raw_input: str
    raw_output: str
    candidate_task: str
    candidate_response: str
    quality_score: int
    risk_flags: list[str] = field(default_factory=list)

    def stable_id(self) -> str:
        payload = f"{self.source}\n{self.url}\n{self.raw_input}\n{self.raw_output}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help=(
            "Dataset root. Defaults to D:/AgenticEngineeringNetwork/training/datasets. "
            "All reads and writes are constrained to product_agent/public_candidates."
        ),
    )


def _assert_allowed_data_root(data_root: Path) -> Path:
    root = data_root.resolve()
    drive = root.drive.upper()
    if drive in {"C:", "E:"}:
        raise CurationError(f"Refusing dataset root on {drive}: {root}")
    legacy_training = Path("D:/training").resolve()
    if drive == "D:" and (root == legacy_training or legacy_training in root.parents):
        raise CurationError("Refusing legacy D:/training dataset location.")
    return root


def public_candidates_dir(data_root: Path = DEFAULT_DATA_ROOT) -> Path:
    root = _assert_allowed_data_root(data_root)
    return (root / PUBLIC_CANDIDATES_ROOT).resolve()


def resolve_public_path(
    relative_path: Path | str = Path("."),
    data_root: Path = DEFAULT_DATA_ROOT,
) -> Path:
    base = public_candidates_dir(data_root)
    path = (base / relative_path).resolve()
    if path != base and base not in path.parents:
        raise CurationError(f"Resolved path escapes public_candidates: {path}")
    return path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise CurationError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any] | CandidateRow]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            payload = asdict(row) if isinstance(row, CandidateRow) else row
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def is_license_clear(license_name: str, license_status: str = "") -> bool:
    normalized = license_name.strip().lower()
    status = license_status.strip().lower()
    if normalized in UNCLEAR_LICENSE_VALUES or status in {"unclear", "restricted"}:
        return False
    return any(pattern in normalized for pattern in PERMISSIVE_LICENSE_PATTERNS)


def text_has_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def truncate_text(text: str, max_chars: int = 6000) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n...[truncated]"


def response_from_parts(
    *,
    requirements: list[str],
    ambiguities: list[str],
    assumptions: list[str],
    acceptance_criteria: list[str],
    risks: list[str],
    confidence: str,
) -> str:
    sections = {
        "REQUIREMENTS": requirements,
        "AMBIGUITIES": ambiguities,
        "ASSUMPTIONS": assumptions,
        "ACCEPTANCE CRITERIA": acceptance_criteria,
        "RISKS": risks,
        "CONFIDENCE": [confidence],
    }
    chunks: list[str] = []
    for title in TARGET_SECTIONS:
        chunks.append(title)
        items = sections[title]
        if not items:
            chunks.append("- None identified")
        else:
            chunks.extend(f"- {clean_text(item)}" for item in items if clean_text(item))
    return "\n".join(chunks).strip()


def candidate_from_dict(row: dict[str, Any]) -> CandidateRow:
    missing = {
        key
        for key in (
            "source",
            "license",
            "url",
            "raw_input",
            "raw_output",
            "candidate_task",
            "candidate_response",
            "quality_score",
            "risk_flags",
        )
        if key not in row
    }
    if missing:
        raise CurationError(f"Candidate row is missing required keys: {sorted(missing)}")
    return CandidateRow(
        source=str(row["source"]),
        license=str(row["license"]),
        url=str(row["url"]),
        raw_input=str(row["raw_input"]),
        raw_output=str(row["raw_output"]),
        candidate_task=str(row["candidate_task"]),
        candidate_response=str(row["candidate_response"]),
        quality_score=int(row["quality_score"]),
        risk_flags=list(row.get("risk_flags") or []),
    )

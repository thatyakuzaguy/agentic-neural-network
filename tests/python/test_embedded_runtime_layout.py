from __future__ import annotations

import shutil
from pathlib import Path

from agentic_network.runtime_engine.local_model_activation import (
    EMBEDDED_RUNTIME_SUBDIRS,
    build_embedded_runtime_layout,
    write_embedded_runtime_layout_artifacts,
)


def _safe_runtime_root(name: str) -> Path:
    return Path("D:/AgenticEngineeringNetwork/outputs/test_runtime_layout") / name


def test_embedded_runtime_layout_dry_run_creates_nothing() -> None:
    root = _safe_runtime_root("dry_run")
    shutil.rmtree(root, ignore_errors=True)

    result = build_embedded_runtime_layout(root, dry_run=True)

    assert result["status"] == "RUNTIME_LAYOUT_PLANNED"
    assert result["created"] == []
    assert not root.exists()


def test_embedded_runtime_layout_confirm_create_creates_only_empty_directories() -> None:
    root = _safe_runtime_root("create")
    shutil.rmtree(root, ignore_errors=True)

    result = build_embedded_runtime_layout(root, dry_run=False, confirm_create=True)

    assert result["status"] == "RUNTIME_LAYOUT_CREATED"
    assert set(result["existing_subdirectories"]) == set(EMBEDDED_RUNTIME_SUBDIRS)
    for name in EMBEDDED_RUNTIME_SUBDIRS:
        path = root / name
        assert path.is_dir()
        assert list(path.iterdir()) == []
    shutil.rmtree(root, ignore_errors=True)


def test_embedded_runtime_layout_blocks_c_root() -> None:
    result = build_embedded_runtime_layout("C:/ANN/runtime", dry_run=False, confirm_create=True)

    assert result["status"] == "RUNTIME_LAYOUT_INVALID_ROOT"
    assert result["created"] == []


def test_embedded_runtime_layout_artifacts(tmp_path: Path) -> None:
    artifacts = write_embedded_runtime_layout_artifacts(tmp_path)
    names = {Path(path).name for path in artifacts}

    assert names == {"168_embedded_runtime_layout.json", "169_embedded_runtime_layout.md"}

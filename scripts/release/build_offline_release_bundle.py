"""Build ANN's hash-verified, split offline Windows release payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Iterable


DEFAULT_REPO_ROOT = Path("D:/AgenticEngineeringNetwork")
DEFAULT_RUNTIME_ROOT = Path("D:/ANN/runtime")
DEFAULT_CHUNK_BYTES = 1_900_000_000
BUFFER_BYTES = 16 * 1024 * 1024
PAYLOAD_MANIFEST_NAME = "RELEASE_PAYLOAD_MANIFEST.json"

INSTALLER_FILES = (
    "ANN_Setup.exe",
    "ANN_Uninstall.exe",
    "ANN_Setup.bat",
    "ANN_Uninstall.bat",
    "install_ann.ps1",
    "uninstall_ann.ps1",
    "ann_launcher.ps1",
    "create_shortcut.ps1",
    "verify_install.ps1",
    "validate_clean_machine.ps1",
    "sign_release.ps1",
    "assemble_release.ps1",
    "README_INSTALLER.md",
    "README_OFFLINE_RELEASE.md",
)
APP_ROOT_FILES = (
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "ATTRIBUTIONS.md",
    "SECURITY.md",
    "start.ps1",
    "stop.ps1",
)
CODE_IGNORED_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".venv-qlora",
    "__pycache__",
    "test-results",
}
CODE_IGNORED_SUFFIXES = {".pyc", ".pyo", ".log"}
MODEL_SUFFIXES = {".gguf", ".safetensors", ".onnx", ".pt", ".pth"}
MODEL_FILENAMES = {"pytorch_model.bin", "adapter_model.bin", "adapter_model.safetensors"}


@dataclass(frozen=True)
class ReleaseItem:
    source: Path
    relative_path: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(BUFFER_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> str:
    pure = PurePosixPath(value.replace("\\", "/"))
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise ValueError(f"Unsafe release path: {value}")
    return pure.as_posix()


def _iter_tree(
    source_root: Path,
    archive_root: str,
    *,
    ignored_names: set[str] | None = None,
    ignored_suffixes: set[str] | None = None,
) -> Iterable[ReleaseItem]:
    ignored_names = ignored_names or set()
    ignored_suffixes = ignored_suffixes or set()
    if not source_root.is_dir():
        raise FileNotFoundError(f"Required release directory missing: {source_root}")
    for path in sorted(source_root.rglob("*"), key=lambda item: item.as_posix().lower()):
        relative = path.relative_to(source_root)
        if any(part in ignored_names for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Symlinks are not allowed in release payloads: {path}")
        if not path.is_file() or path.suffix.lower() in ignored_suffixes:
            continue
        yield ReleaseItem(path, _safe_relative(f"{archive_root}/{relative.as_posix()}"))


def collect_release_items(
    repo_root: Path,
    runtime_root: Path,
    desktop_root: Path | None = None,
) -> list[ReleaseItem]:
    repo_root = repo_root.resolve()
    runtime_root = runtime_root.resolve()
    desktop_root = (desktop_root or _detect_desktop_root(repo_root)).resolve()
    items: list[ReleaseItem] = []

    for name in INSTALLER_FILES:
        source = repo_root / "installer" / name
        if not source.is_file():
            raise FileNotFoundError(f"Required installer file missing: {source}")
        items.append(ReleaseItem(source, f"installer/{name}"))

    for name in APP_ROOT_FILES:
        source = repo_root / name
        if not source.is_file():
            raise FileNotFoundError(f"Required application file missing: {source}")
        items.append(ReleaseItem(source, f"payload/app/{name}"))

    code_trees = (
        (repo_root / "agentic_network", "payload/app/agentic_network"),
        (repo_root / "packages", "payload/app/packages"),
        (repo_root / "config", "payload/app/config"),
        (repo_root / "apps" / "api", "payload/app/apps/api"),
        (repo_root / "scripts" / "runtime", "payload/app/scripts/runtime"),
    )
    for source, target in code_trees:
        items.extend(
            _iter_tree(
                source,
                target,
                ignored_names=CODE_IGNORED_NAMES,
                ignored_suffixes=CODE_IGNORED_SUFFIXES,
            )
        )

    items.extend(
        _iter_tree(
            repo_root / "apps" / "web" / ".next" / "standalone",
            "payload/app/apps/web/.next/standalone",
        )
    )
    items.extend(_iter_tree(desktop_root, "payload/desktop"))
    items.extend(_iter_tree(runtime_root, "payload/runtime", ignored_names={"logs"}))
    return _validate_items(items)


def _detect_desktop_root(repo_root: Path) -> Path:
    dist = repo_root / "apps" / "desktop" / "dist"
    candidates = sorted(
        path
        for path in dist.iterdir()
        if path.is_dir() and (path / "ANN.exe").is_file()
    ) if dist.is_dir() else []
    if len(candidates) != 1:
        raise FileNotFoundError(f"Expected exactly one packaged ANN Desktop directory under {dist}")
    return candidates[0]


def _validate_items(items: list[ReleaseItem]) -> list[ReleaseItem]:
    by_path: dict[str, ReleaseItem] = {}
    for item in items:
        relative = _safe_relative(item.relative_path)
        if not item.source.is_file():
            raise FileNotFoundError(item.source)
        lowered = relative.lower()
        if lowered in by_path:
            raise ValueError(f"Duplicate release path: {relative}")
        if item.source.suffix.lower() in MODEL_SUFFIXES or item.source.name.lower() in MODEL_FILENAMES:
            raise ValueError(f"Model artifact cannot enter the public release payload: {item.source}")
        by_path[lowered] = ReleaseItem(item.source, relative)
    return [by_path[key] for key in sorted(by_path)]


def build_release_archive(
    items: list[ReleaseItem],
    archive_path: Path,
    *,
    version: str,
) -> dict[str, object]:
    items = _validate_items(items)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        raise FileExistsError(archive_path)
    file_entries = [
        {
            "relative_path": item.relative_path,
            "size_bytes": item.source.stat().st_size,
            "sha256": sha256_file(item.source),
        }
        for item in items
    ]
    payload_manifest = {
        "schema_version": "1.0",
        "release_version": version,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "HASH_VERIFIED_SOURCE_SET",
        "files": file_entries,
        "file_count": len(file_entries),
        "model_files_included": False,
        "training_files_included": False,
        "dataset_files_included": False,
        "adapter_files_included": False,
    }
    manifest_bytes = (json.dumps(payload_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with zipfile.ZipFile(
        archive_path,
        "x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        _write_bytes(archive, PAYLOAD_MANIFEST_NAME, manifest_bytes)
        for item in items:
            _write_file(archive, item)
    with zipfile.ZipFile(archive_path, "r", allowZip64=True) as archive:
        expected = {PAYLOAD_MANIFEST_NAME, *(item.relative_path for item in items)}
        if set(archive.namelist()) != expected:
            raise RuntimeError("Release archive member set does not match its source set.")
        corrupt = archive.testzip()
        if corrupt:
            raise RuntimeError(f"Corrupt member in release archive: {corrupt}")
    return {
        "payload_manifest": payload_manifest,
        "payload_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "archive_size_bytes": archive_path.stat().st_size,
        "archive_sha256": sha256_file(archive_path),
    }


def _write_bytes(archive: zipfile.ZipFile, relative_path: str, content: bytes) -> None:
    info = zipfile.ZipInfo(_safe_relative(relative_path), date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)


def _write_file(archive: zipfile.ZipFile, item: ReleaseItem) -> None:
    info = zipfile.ZipInfo(item.relative_path, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    with item.source.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
        shutil.copyfileobj(source, target, length=BUFFER_BYTES)


def split_archive(archive_path: Path, output_root: Path, chunk_bytes: int) -> list[dict[str, object]]:
    if chunk_bytes <= 0:
        raise ValueError("chunk_bytes must be positive")
    parts: list[dict[str, object]] = []
    with archive_path.open("rb") as source:
        index = 1
        while True:
            part_path = output_root / f"{archive_path.name}.part{index:03d}"
            digest = hashlib.sha256()
            written = 0
            with part_path.open("xb") as target:
                while written < chunk_bytes:
                    chunk = source.read(min(BUFFER_BYTES, chunk_bytes - written))
                    if not chunk:
                        break
                    target.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
            if written == 0:
                part_path.unlink()
                break
            parts.append(
                {
                    "index": index,
                    "file_name": part_path.name,
                    "size_bytes": written,
                    "sha256": digest.hexdigest(),
                }
            )
            index += 1
    return parts


def build_bundle(
    *,
    repo_root: Path,
    runtime_root: Path,
    output_root: Path,
    version: str,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    keep_archive: bool = False,
) -> dict[str, object]:
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Release output directory is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    items = collect_release_items(repo_root, runtime_root)
    archive_path = output_root / f"ANN-{version}-windows-offline.zip"
    archive = build_release_archive(items, archive_path, version=version)
    parts = split_archive(archive_path, output_root, chunk_bytes)
    bootstrap = []
    for source_name, target_name in (
        ("assemble_release.ps1", "assemble_release.ps1"),
        ("README_OFFLINE_RELEASE.md", "README_OFFLINE_RELEASE.md"),
    ):
        source = repo_root / "installer" / source_name
        target = output_root / target_name
        shutil.copy2(source, target)
        bootstrap.append(
            {"file_name": target.name, "size_bytes": target.stat().st_size, "sha256": sha256_file(target)}
        )
    manifest = {
        "schema_version": "1.0",
        "release_version": version,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "OFFLINE_RELEASE_BUNDLE_READY",
        "archive_name": archive_path.name,
        "archive_size_bytes": archive["archive_size_bytes"],
        "archive_sha256": archive["archive_sha256"],
        "payload_manifest_sha256": archive["payload_manifest_sha256"],
        "chunk_size_limit_bytes": chunk_bytes,
        "parts": parts,
        "bootstrap_files": bootstrap,
        "file_count": archive["payload_manifest"]["file_count"],
        "models_included": False,
        "model_pack_required_for_real_inference": True,
        "no_download": True,
        "no_dependency_install": True,
        "no_model_load": True,
        "no_inference": True,
    }
    manifest_path = output_root / "ANN_RELEASE_PARTS.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksum_path = output_root / "ANN_RELEASE_PARTS.sha256"
    checksum_path.write_text(f"{sha256_file(manifest_path)}  {manifest_path.name}\n", encoding="ascii")
    if not keep_archive:
        archive_path.unlink()
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--chunk-bytes", type=int, default=DEFAULT_CHUNK_BYTES)
    parser.add_argument("--keep-archive", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = build_bundle(
        repo_root=args.repo_root,
        runtime_root=args.runtime_root,
        output_root=args.output_root,
        version=args.version,
        chunk_bytes=args.chunk_bytes,
        keep_archive=args.keep_archive,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

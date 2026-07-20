"""Security boundary for importing llama-cpp-python without DiskCache.

llama-cpp-python imports ``diskcache`` eagerly even when callers never enable
its persistent prompt cache. DiskCache 5.6.3 has no patched release for
CVE-2025-69872, so ANN substitutes a fail-closed compatibility module while the
binding imports and keeps persistent caching disabled for the process lifetime.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from importlib import metadata
from threading import RLock
from types import ModuleType
from typing import Any, Iterator


DISKCACHE_ADVISORY = "CVE-2025-69872"
_LOCK = RLock()
_MISSING = object()


class PersistentLlamaCacheDisabledError(RuntimeError):
    """Raised when code attempts to enable llama.cpp persistent caching."""


class _DisabledCache:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise PersistentLlamaCacheDisabledError(
            "LlamaDiskCache is disabled by ANN because DiskCache has an unfixed "
            f"unsafe-deserialization advisory ({DISKCACHE_ADVISORY}). Use the default "
            "no-cache mode or llama_cpp.LlamaRAMCache."
        )


def _disabled_diskcache_module() -> ModuleType:
    module = ModuleType("diskcache")
    module.__dict__.update(
        {
            "Cache": _DisabledCache,
            "__all__": ["Cache"],
            "__ann_persistent_cache_disabled__": True,
            "__version__": "disabled-by-ann",
        }
    )
    return module


@contextmanager
def _temporary_diskcache_stub(stub: ModuleType) -> Iterator[None]:
    previous = sys.modules.get("diskcache", _MISSING)
    sys.modules["diskcache"] = stub
    try:
        yield
    finally:
        if previous is _MISSING:
            sys.modules.pop("diskcache", None)
        else:
            sys.modules["diskcache"] = previous  # type: ignore[assignment]


def load_secure_llama_cpp() -> Any:
    """Import llama_cpp while permanently disabling its disk-backed cache.

    The temporary stub avoids importing a real DiskCache distribution. The
    module-global reference retained by ``llama_cpp.llama_cache`` is then pinned
    to the fail-closed stub. Any unrelated preloaded ``diskcache`` module is
    restored immediately after the binding import.
    """

    with _LOCK:
        stub = _disabled_diskcache_module()
        with _temporary_diskcache_stub(stub):
            binding = importlib.import_module("llama_cpp")
            cache_module = sys.modules.get("llama_cpp.llama_cache")
            if cache_module is None and hasattr(binding, "__path__"):
                cache_module = importlib.import_module("llama_cpp.llama_cache")
        if cache_module is None:
            # Tests and explicitly injected bindings may be module-like objects
            # without llama_cpp's package structure. They expose no disk cache.
            return binding
        cache_module.diskcache = stub
        if not llama_cpp_disk_cache_disabled(cache_module):
            raise RuntimeError("ANN could not disable llama.cpp persistent disk caching.")
        return binding


def llama_cpp_disk_cache_disabled(cache_module: Any | None = None) -> bool:
    """Return whether llama.cpp's cache module is pinned to ANN's safe stub."""

    module = cache_module or sys.modules.get("llama_cpp.llama_cache")
    diskcache_module = getattr(module, "diskcache", None)
    return bool(
        getattr(diskcache_module, "__ann_persistent_cache_disabled__", False)
        and getattr(diskcache_module, "Cache", None) is _DisabledCache
    )


def diskcache_distribution_installed() -> bool:
    """Detect the vulnerable third-party distribution without importing it."""

    try:
        metadata.version("diskcache")
    except metadata.PackageNotFoundError:
        return False
    return True


def build_llama_cpp_cache_security_status() -> dict[str, object]:
    """Return auditable state without loading a model or running inference."""

    cache_module = sys.modules.get("llama_cpp.llama_cache")
    return {
        "status": (
            "DISK_CACHE_DISABLED"
            if cache_module is not None and llama_cpp_disk_cache_disabled(cache_module)
            else "NOT_LOADED"
        ),
        "advisory": DISKCACHE_ADVISORY,
        "persistent_disk_cache_enabled": False,
        "diskcache_distribution_installed": diskcache_distribution_installed(),
        "model_load_attempted": False,
        "inference_attempted": False,
    }

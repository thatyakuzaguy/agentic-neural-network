from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from agentic_network.models import llama_cpp_security as security


def _fake_binding_modules() -> tuple[ModuleType, ModuleType]:
    binding = ModuleType("llama_cpp")
    binding.__path__ = []  # type: ignore[attr-defined]
    binding.Llama = object
    cache_module = ModuleType("llama_cpp.llama_cache")
    cache_module.diskcache = SimpleNamespace(Cache=object)

    class LlamaDiskCache:
        def __init__(self) -> None:
            cache_module.diskcache.Cache("unused")

    cache_module.LlamaDiskCache = LlamaDiskCache
    return binding, cache_module


def test_secure_import_disables_persistent_cache_and_restores_global_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding, cache_module = _fake_binding_modules()
    unrelated_diskcache = ModuleType("diskcache")
    monkeypatch.setitem(sys.modules, "llama_cpp", binding)
    monkeypatch.setitem(sys.modules, "llama_cpp.llama_cache", cache_module)
    monkeypatch.setitem(sys.modules, "diskcache", unrelated_diskcache)

    loaded = security.load_secure_llama_cpp()

    assert loaded is binding
    assert sys.modules["diskcache"] is unrelated_diskcache
    assert security.llama_cpp_disk_cache_disabled(cache_module) is True
    with pytest.raises(security.PersistentLlamaCacheDisabledError):
        cache_module.LlamaDiskCache()


def test_secure_status_never_claims_model_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    binding, cache_module = _fake_binding_modules()
    monkeypatch.setitem(sys.modules, "llama_cpp", binding)
    monkeypatch.setitem(sys.modules, "llama_cpp.llama_cache", cache_module)
    monkeypatch.setattr(security.metadata, "version", lambda _name: (_ for _ in ()).throw(
        security.metadata.PackageNotFoundError
    ))

    security.load_secure_llama_cpp()
    status = security.build_llama_cpp_cache_security_status()

    assert status["status"] == "DISK_CACHE_DISABLED"
    assert status["diskcache_distribution_installed"] is False
    assert status["model_load_attempted"] is False
    assert status["inference_attempted"] is False

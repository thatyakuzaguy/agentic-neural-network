from __future__ import annotations

from agentic_network.runtime_engine import local_model_activation as activation


def test_external_runtime_does_not_mark_final_release_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        activation,
        "build_external_runtime_smoke_readiness",
        lambda *_args, **_kwargs: {
            "status": "READY_FOR_CONTROLLED_SMOKE_EXTERNAL",
            "external_runtime": {"status": "EXTERNAL_RUNTIME_READY"},
        },
    )

    precheck = activation.build_final_release_precheck()
    embedded = activation.build_embedded_python_evidence()

    assert precheck["status"] != "FINAL_RELEASE_READY"
    assert precheck["status"] == "PRECHECK_BLOCKED"
    assert embedded["status"] in {"MISSING", "PARTIAL", "READY"}
    assert precheck["qwen3"]["status"] == "BLOCKED"
    assert precheck["deepseek"]["status"] == "BLOCKED"
    assert precheck["deepseek"]["powerful_activated"] is False
    assert precheck["model_load_attempted"] is False
    assert precheck["real_inference_attempted"] is False

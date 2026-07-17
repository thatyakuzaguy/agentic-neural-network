from __future__ import annotations

from agentic_network.runtime_engine.local_model_activation import build_model_identity_correction
from agentic_network.runtime_engine.model_inventory import load_model_inventory, resolve_model_record


def test_model_identity_replaces_qwen14b_with_deepseek14b() -> None:
    report = build_model_identity_correction()
    names = report["inventory_model_names"]

    assert report["status"] == "CORRECTED"
    assert report["qwen14b_present"] is False
    assert report["deepseek14b_present"] is True
    assert "qwen14b" not in names
    assert "deepseek_r1_distill_qwen_14b" in names


def test_model_inventory_exposes_required_v13_fields() -> None:
    inventory = load_model_inventory()
    record = resolve_model_record("qwen2_5_coder_7b_v5")

    assert inventory.version == 2
    assert record is not None
    payload = record.to_dict()
    for key in (
        "model_name",
        "family",
        "mode",
        "source_path",
        "distribution_path",
        "backend",
        "adapter_path",
        "model_declared",
        "path_exists",
        "adapter_exists",
        "backend_available",
        "enabled",
        "load_allowed",
        "load_blocked_reason",
        "estimated_vram_mb",
        "status",
    ):
        assert key in payload

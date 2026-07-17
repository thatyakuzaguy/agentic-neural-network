from __future__ import annotations

from agentic_network.desktop_app.views.first_run_view import build_first_run_state, first_run_snapshot


def test_first_run_guided_status_renders_incomplete_environment() -> None:
    snapshot = first_run_snapshot()

    assert "Guided Runtime Status:" in snapshot
    assert "Runtime compatibility:" in snapshot
    assert "Environment missing:" in snapshot
    assert "Next manual step:" in snapshot
    assert "Ready for real inference:" in snapshot
    assert "Qwen3 blocked:" in snapshot
    assert "DeepSeek blocked:" in snapshot


def test_first_run_state_includes_runtime_compatibility_objects() -> None:
    state = build_first_run_state()

    assert state["external_runtime_matrix"]["status"] in {"ENVIRONMENT_INCOMPLETE", "READY_FOR_REAL_INFERENCE"}
    assert state["embedded_python_release_plan"]["expected_python_executable"] == "D:\\ANN\\runtime\\python\\python.exe"
    assert state["backend_manual_readiness"]["status"] in {"READY", "MANUAL_STEPS_REQUIRED"}
    assert state["real_inference_launch_guard"]["status"] == "BLOCKED"

from __future__ import annotations

import json
from pathlib import Path

from agentic_network.runtime_engine import local_model_activation as activation
from scripts.runtime import plan_autonomous_capability_evidence
from scripts.runtime import run_autonomous_capability_scenarios
from scripts.runtime import verify_autonomous_capability


def _write_passing_summary(root: Path, scenario_id: str) -> None:
    scenario = root / scenario_id
    scenario.mkdir(parents=True)
    (scenario / "summary.json").write_text(
        json.dumps(
            {
                "status": "COMPLETED_VERIFIED",
                "completion_quality": "VERIFIED",
                "verification_evidence": {"evidence_level": "STRONG"},
                "commands_executed": [["python", "-m", "pytest", "-q"]],
                "security_review": "PASSED",
                "protected_paths_modified": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_autonomous_complex_capability_blocks_without_evidence(tmp_path: Path) -> None:
    gate = activation.build_autonomous_complex_capability_gate(tmp_path)

    assert gate["status"] == "AUTONOMOUS_COMPLEX_CAPABILITY_BLOCKED"
    assert gate["passed"] is False
    assert gate["required_scenarios"] == 7
    assert gate["passed_scenarios"] == 0
    assert len(gate["blockers"]) == 7
    assert gate["no_model_load"] is True
    assert gate["no_inference"] is True


def test_autonomous_complex_capability_passes_with_all_strong_evidence(tmp_path: Path) -> None:
    gate = activation.build_autonomous_complex_capability_gate(tmp_path)
    for scenario in gate["scenarios"]:
        _write_passing_summary(tmp_path, scenario["id"])

    gate = activation.build_autonomous_complex_capability_gate(tmp_path)

    assert gate["status"] == "AUTONOMOUS_COMPLEX_CAPABILITY_PASSED"
    assert gate["passed"] is True
    assert gate["passed_scenarios"] == gate["required_scenarios"]
    assert gate["blockers"] == []


def test_autonomous_complex_capability_rejects_weak_evidence(tmp_path: Path) -> None:
    gate = activation.build_autonomous_complex_capability_gate(tmp_path)
    for scenario in gate["scenarios"]:
        _write_passing_summary(tmp_path, scenario["id"])
    weak = tmp_path / "complex_3d_game" / "summary.json"
    payload = json.loads(weak.read_text(encoding="utf-8"))
    payload["verification_evidence"] = {"evidence_level": "WEAK"}
    weak.write_text(json.dumps(payload), encoding="utf-8")

    gate = activation.build_autonomous_complex_capability_gate(tmp_path)

    assert gate["status"] == "AUTONOMOUS_COMPLEX_CAPABILITY_BLOCKED"
    assert any(item["id"] == "complex_3d_game" for item in gate["blockers"])


def test_autonomous_complex_capability_artifacts(tmp_path: Path) -> None:
    artifacts = activation.write_autonomous_complex_capability_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "366_autonomous_complex_capability_gate.json",
        "367_autonomous_complex_capability_gate.md",
    }
    payload = json.loads((tmp_path / "366_autonomous_complex_capability_gate.json").read_text(encoding="utf-8"))
    assert payload["version"] == "18.9.13"


def test_autonomous_capability_evidence_plan_lists_missing_proof(tmp_path: Path) -> None:
    plan = activation.build_autonomous_capability_evidence_plan(tmp_path)

    assert plan["status"] == "EVIDENCE_REQUIRED"
    assert plan["final_release_blocking"] is True
    assert plan["remaining_scenarios"] == 7
    assert plan["does_not_create_fake_evidence"] is True
    assert all("summary.json" in item["missing_requirements"] for item in plan["scenarios"])


def test_autonomous_capability_evidence_plan_artifacts(tmp_path: Path) -> None:
    artifacts = activation.write_autonomous_capability_evidence_plan_artifacts(tmp_path)

    assert {Path(path).name for path in artifacts} == {
        "368_autonomous_capability_evidence_plan.json",
        "369_autonomous_capability_evidence_plan.md",
    }
    payload = json.loads((tmp_path / "368_autonomous_capability_evidence_plan.json").read_text(encoding="utf-8"))
    assert payload["version"] == "18.9.14"


def test_verify_autonomous_capability_cli_blocks_without_evidence(tmp_path: Path, capsys) -> None:
    exit_code = verify_autonomous_capability.main(["--evidence-root", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "AUTONOMOUS_COMPLEX_CAPABILITY_BLOCKED" in output


def test_plan_autonomous_capability_cli_blocks_without_evidence(tmp_path: Path, capsys) -> None:
    exit_code = plan_autonomous_capability_evidence.main(["--evidence-root", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert "EVIDENCE_REQUIRED" in output


def test_run_autonomous_capability_scenarios_plan_mode_does_not_execute(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("plan mode must not run the project builder")

    monkeypatch.setattr(run_autonomous_capability_scenarios, "run_end_to_end_project", fail_if_called)

    exit_code = run_autonomous_capability_scenarios.main(
        ["--evidence-root", str(tmp_path / "evidence"), "--scenario", "crm_saas_multitenant"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called is False
    assert "Execute: false" in output


def test_run_autonomous_capability_scenarios_writes_verified_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class Result:
        def to_dict(self):
            return {
                "status": "COMPLETED_VERIFIED",
                "completion_quality": "VERIFIED",
                "project_root": str(tmp_path / "project"),
                "verification_evidence": {
                    "evidence_level": "STRONG",
                    "commands_executed": [["python", "-m", "pytest", "-q"]],
                },
                "validation_errors": [],
                "artifacts": [],
                "model_routing_status": "READY",
                "next_action": "completed_verified",
            }

    monkeypatch.setattr(run_autonomous_capability_scenarios, "run_end_to_end_project", lambda **_kwargs: Result())
    evidence = tmp_path / "evidence"

    exit_code = run_autonomous_capability_scenarios.main(
        [
            "--evidence-root",
            str(evidence),
            "--target-root",
            str(tmp_path / "targets"),
            "--scenario",
            "crm_saas_multitenant",
            "--approval-token",
            "local-test-token",
            "--execute",
        ]
    )

    assert exit_code == 0
    payload = json.loads((evidence / "crm_saas_multitenant" / "summary.json").read_text(encoding="utf-8"))
    assert payload["status"] == "COMPLETED_VERIFIED"
    assert payload["security_review"] == "PASSED"
    assert payload["protected_paths_modified"] is False


def test_run_autonomous_capability_scenarios_keeps_unverified_blocking(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class Result:
        def to_dict(self):
            return {
                "status": "NEEDS_TESTS",
                "completion_quality": "REVIEW_REQUIRED",
                "project_root": str(tmp_path / "project"),
                "verification_evidence": {"evidence_level": "NONE", "commands_executed": []},
                "validation_errors": ["tests missing"],
                "artifacts": [],
                "model_routing_status": "READY",
                "next_action": "add_project_tests",
            }

    monkeypatch.setattr(run_autonomous_capability_scenarios, "run_end_to_end_project", lambda **_kwargs: Result())
    evidence = tmp_path / "evidence"

    exit_code = run_autonomous_capability_scenarios.main(
        [
            "--evidence-root",
            str(evidence),
            "--target-root",
            str(tmp_path / "targets"),
            "--scenario",
            "crm_saas_multitenant",
            "--execute",
        ]
    )

    assert exit_code == 2
    payload = json.loads((evidence / "crm_saas_multitenant" / "summary.json").read_text(encoding="utf-8"))
    assert payload["status"] == "NEEDS_TESTS"
    assert payload["security_review"] == "REVIEW_REQUIRED"

import json
from pathlib import Path

from agentic_network.patch_quality_agent.runtime import (
    IMPLEMENTATION_READY,
    LOW_VALUE_COMMENT_ONLY,
    NEEDS_RELOCATION,
    NEEDS_REVISION,
    PATCH_QUALITY_OUTPUT_FILE,
    REJECTED,
    UNCONNECTED_LOGIC,
    evaluate_patch_quality,
    parse_patch_quality_report,
    validate_patch_quality_report,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run_dir(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    project_root = tmp_path / "repo"
    run_dir = project_root / "outputs" / "runs" / "run_001"
    (run_dir / "patches").mkdir(parents=True)
    monkeypatch.setattr("agentic_network.patch_quality_agent.runtime._project_root", lambda: project_root)
    monkeypatch.setenv("ANN_ALLOWED_ROOTS", str(project_root))
    monkeypatch.setenv("ANN_BLOCKED_ROOTS", str(tmp_path / "blocked"))
    _write(project_root / "app" / "auth" / "password_reset.py", "def send_password_reset(email):\n    return True\n")
    _write(project_root / "app" / "config.py", "APP_NAME = 'test'\n")
    _write(project_root / "app" / "auth" / "guards.py", "class User:\n    pass\n")
    _write(project_root / "app" / "misc.py", "VALUE = 1\n")
    _write(run_dir / "11_execution_plan.md", "FILES TO MODIFY\n- app/auth/password_reset.py\n")
    _write(
        run_dir / "03_code_revised.md",
        "FILES TO MODIFY\n- app/auth/password_reset.py\n\nCODE CHANGES\n- Add password reset rate limit behavior.\n",
    )
    _write(run_dir / "04_tests_revised.md", "TEST SCENARIOS\n- Verify rate limits.\n")
    _write(run_dir / "05_security_revised.md", "SECURITY FINDINGS\n- Preserve generic responses.\n")
    _write(run_dir / "08_final_review.md", "FINAL DECISION\nApproved\n")
    _write(
        run_dir / "24_experience_context.md",
        "EXPERIENCE CONTEXT\n- Retrieved.\n\nREUSABLE CONSTANTS\n- MAX_ATTEMPTS=7\n- WINDOW_SECONDS=7200\n- THRESHOLD=11\n\nCONFIDENCE\nHigh\n",
    )
    _write(run_dir / "summary.json", json.dumps({"execution_memory_used": True}, indent=2))
    return project_root, run_dir


def _patch(run_dir: Path, name: str, text: str) -> None:
    _write(run_dir / "patches" / name, text)


def test_implementation_ready_patch(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/auth/password_reset.py
+++ b/app/auth/password_reset.py
@@ -1,2 +1,5 @@
 def send_password_reset(email):
+    allowed = check_password_reset_rate_limit(email)["allowed"]
+    if not allowed:
+        return {"message": "If an account exists, password reset instructions will be sent.", "accepted": True}
     return True
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == IMPLEMENTATION_READY
    assert result.score >= 80
    assert result.validation_errors == []
    assert (run_dir / PATCH_QUALITY_OUTPUT_FILE).exists()
    parsed = parse_patch_quality_report(result.report)
    assert parsed[0]["quality"] == IMPLEMENTATION_READY
    assert validate_patch_quality_report(result.report, parsed) == []


def test_needs_relocation_for_useful_logic_in_wrong_file(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/config.py
+++ b/app/config.py
@@ -1,1 +1,5 @@
 APP_NAME = 'test'
+def check_password_reset_rate_limit(email):
+    attempts = 1
+    return {"allowed": attempts <= 5, "message": "If an account exists, password reset instructions will be sent."}
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == NEEDS_RELOCATION
    assert any("wrong file" in reason for reason in result.reasons)


def test_target_selection_metadata_can_justify_selected_target(tmp_path: Path, monkeypatch) -> None:
    project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(
        run_dir / "summary.json",
        json.dumps(
            {
                "execution_memory_used": True,
                "execution_target_selection_used": True,
                "execution_selected_targets": ["app/core/limits.py"],
                "execution_rejected_targets": ["app/ui/password_reset_form.tsx"],
                "execution_target_classes": {"app/core/limits.py": "SERVICE_LAYER"},
                "execution_target_selection_reasons": {
                    "app/core/limits.py": "Selected as SERVICE_LAYER with score 88 for backend security task."
                },
            },
            indent=2,
        ),
    )
    _write(project_root / "app" / "core" / "limits.py", "VALUE = 1\n")
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/core/limits.py
+++ b/app/core/limits.py
@@ -1,1 +1,8 @@
 VALUE = 1
+MAX_ATTEMPTS = 7
+WINDOW_SECONDS = 7200
+THRESHOLD = 11
+def check_password_reset_rate_limit(email):
+    attempts = 1
+    return {"allowed": attempts <= MAX_ATTEMPTS, "message": "If an account exists, password reset instructions will be sent."}
+check_password_reset_rate_limit("demo@example.com")
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == IMPLEMENTATION_READY
    assert "Architecture connection detected." in result.reasons


def test_target_selection_rejected_target_needs_relocation(tmp_path: Path, monkeypatch) -> None:
    project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(
        run_dir / "summary.json",
        json.dumps(
            {
                "execution_target_selection_used": True,
                "execution_selected_targets": ["app/auth/password_reset.py"],
                "execution_rejected_targets": ["app/ui/password_reset_form.tsx"],
            },
            indent=2,
        ),
    )
    _write(project_root / "app" / "ui" / "password_reset_form.tsx", "export const value = 1\n")
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/ui/password_reset_form.tsx
+++ b/app/ui/password_reset_form.tsx
@@ -1,1 +1,5 @@
 export const value = 1
+export function check_password_reset_rate_limit(email) {
+  return { allowed: true }
+}
+check_password_reset_rate_limit("demo@example.com")
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == NEEDS_RELOCATION
    assert any("rejected" in reason.lower() for reason in result.reasons)


def test_multifile_plan_rewards_planned_files(tmp_path: Path, monkeypatch) -> None:
    project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(
        run_dir / "summary.json",
        json.dumps(
            {
                "execution_memory_used": True,
                "execution_multifile_plan_used": True,
                "execution_multifile_plan_type": "RATE_LIMITING_FEATURE",
                "execution_multifile_selected_files": ["app/core/limits.py"],
                "execution_multifile_file_roles": {"app/core/limits.py": "SERVICE_LAYER"},
                "execution_multifile_missing_layers": ["ROUTE_HANDLER"],
            },
            indent=2,
        ),
    )
    _write(project_root / "app" / "core" / "limits.py", "VALUE = 1\n")
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/core/limits.py
+++ b/app/core/limits.py
@@ -1,1 +1,8 @@
 VALUE = 1
+MAX_ATTEMPTS = 7
+WINDOW_SECONDS = 7200
+def check_password_reset_rate_limit(email):
+    attempts = 1
+    return {"allowed": attempts <= MAX_ATTEMPTS, "message": "If an account exists, password reset instructions will be sent."}
+check_password_reset_rate_limit("demo@example.com")
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == IMPLEMENTATION_READY
    assert 80 <= result.score < 100
    assert any("multi-file implementation plan" in reason for reason in result.reasons)
    assert any("Missing implementation layers" in reason for reason in result.reasons)


def test_multifile_plan_penalizes_unplanned_files(tmp_path: Path, monkeypatch) -> None:
    project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(
        run_dir / "summary.json",
        json.dumps(
            {
                "execution_multifile_plan_used": True,
                "execution_multifile_plan_type": "RATE_LIMITING_FEATURE",
                "execution_multifile_selected_files": ["app/auth/password_reset.py"],
                "execution_multifile_file_roles": {"app/auth/password_reset.py": "SERVICE_LAYER"},
                "execution_multifile_missing_layers": [],
            },
            indent=2,
        ),
    )
    _write(project_root / "app" / "misc.py", "VALUE = 1\n")
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/misc.py
+++ b/app/misc.py
@@ -1,1 +1,5 @@
 VALUE = 1
+def check_password_reset_rate_limit(email):
+    attempts = 1
+    return {"allowed": attempts <= 5}
+check_password_reset_rate_limit("demo@example.com")
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == NEEDS_RELOCATION
    assert any("not selected by the multi-file" in reason for reason in result.reasons)


def test_patch_quality_penalizes_planned_service_creation_without_connection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(
        run_dir / "summary.json",
        json.dumps(
            {
                "execution_memory_used": True,
                "execution_layer_creation_used": True,
                "execution_layer_proposed_files": ["app/services/password_reset_rate_limit.py"],
                "execution_layer_rejected_layers": {},
                "execution_layer_creation_validation_passed": True,
                "execution_multifile_plan_used": True,
                "execution_multifile_selected_files": ["app/routes/auth.py"],
                "execution_multifile_missing_layers": ["SERVICE_LAYER"],
            },
            indent=2,
        ),
    )
    _patch(
        run_dir,
        "patch_001.diff",
        '''--- /dev/null
+++ b/app/services/password_reset_rate_limit.py
@@ -0,0 +1,8 @@
+"""Service helpers proposed by ANN layer creation planning."""
+
+from __future__ import annotations
+
+
+def password_reset_rate_limit(identifier: str) -> dict[str, object]:
+    allowed = bool(identifier.strip())
+    return {"allowed": allowed}
''',
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == NEEDS_REVISION
    assert result.validation_errors == []
    assert any("layer creation plan" in reason for reason in result.reasons)
    assert any("not called" in reason for reason in result.reasons)


def test_patch_quality_accepts_connected_service_route_and_test_patch(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(
        run_dir / "summary.json",
        json.dumps(
            {
                "execution_memory_used": True,
                "execution_layer_creation_used": True,
                "execution_layer_proposed_files": [
                    "app/services/password_reset_rate_limit.py",
                    "app/routes/auth.py",
                    "tests/test_password_reset_rate_limit.py",
                ],
                "execution_layer_rejected_layers": {},
                "execution_layer_creation_validation_passed": True,
                "execution_multifile_plan_used": True,
                "execution_multifile_selected_files": [
                    "app/services/password_reset_rate_limit.py",
                    "app/routes/auth.py",
                    "tests/test_password_reset_rate_limit.py",
                ],
                "execution_multifile_missing_layers": [],
            },
            indent=2,
        ),
    )
    _patch(
        run_dir,
        "patch_001.diff",
        '''--- /dev/null
+++ b/app/services/password_reset_rate_limit.py
@@ -0,0 +1,8 @@
+"""Password reset rate limiting service."""
+
+from __future__ import annotations
+
+
+def password_reset_rate_limit(identifier: str) -> dict[str, object]:
+    allowed = bool(identifier.strip())
+    return {"allowed": allowed, "message": "If an account exists, instructions will be sent."}
--- /dev/null
+++ b/app/routes/auth.py
@@ -0,0 +1,12 @@
+from fastapi import APIRouter
+
+from app.services.password_reset_rate_limit import password_reset_rate_limit
+
+router = APIRouter()
+
+
+@router.post("/password-reset")
+def request_password_reset(email: str) -> dict[str, object]:
+    decision = password_reset_rate_limit(email)
+    return {"accepted": decision["allowed"], "message": decision["message"]}
--- /dev/null
+++ b/tests/test_password_reset_rate_limit.py
@@ -0,0 +1,7 @@
+from app.services.password_reset_rate_limit import password_reset_rate_limit
+
+
+def test_password_reset_rate_limit_accepts_identifier() -> None:
+    result = password_reset_rate_limit("demo@example.com")
+    assert result["allowed"] is True
+    assert "instructions" in result["message"]
''',
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == IMPLEMENTATION_READY
    assert result.score == 100
    assert result.validation_errors == []
    assert any("Non-trivial test coverage" in reason for reason in result.reasons)


def test_patch_quality_penalizes_bottom_imports(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/auth/password_reset.py
+++ b/app/auth/password_reset.py
@@ -1,2 +1,6 @@
 def send_password_reset(email):
     return True
+MAX_ATTEMPTS = 7
+from app.auth.guards import User
+def check_password_reset_rate_limit(email):
+    return {"allowed": bool(User)}
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == NEEDS_REVISION
    assert result.score < 100
    assert any("Imports were added below executable code" in reason for reason in result.reasons)


def test_patch_quality_penalizes_route_without_service_call(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(
        run_dir / "summary.json",
        json.dumps(
            {
                "execution_memory_used": True,
                "execution_layer_creation_used": True,
                "execution_layer_proposed_files": [
                    "app/services/password_reset_rate_limit.py",
                    "app/routes/auth.py",
                ],
                "execution_layer_creation_validation_passed": True,
                "execution_multifile_plan_used": True,
                "execution_multifile_selected_files": [
                    "app/services/password_reset_rate_limit.py",
                    "app/routes/auth.py",
                ],
            },
            indent=2,
        ),
    )
    _patch(
        run_dir,
        "patch_001.diff",
        '''--- /dev/null
+++ b/app/services/password_reset_rate_limit.py
@@ -0,0 +1,5 @@
+def password_reset_rate_limit(identifier: str) -> dict[str, object]:
+    return {"allowed": bool(identifier.strip())}
--- /dev/null
+++ b/app/routes/auth.py
@@ -0,0 +1,8 @@
+from fastapi import APIRouter
+
+router = APIRouter()
+
+
+@router.post("/password-reset")
+def request_password_reset(email: str) -> dict[str, object]:
+    return {"accepted": True}
''',
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == NEEDS_REVISION
    assert any("without calling the proposed service layer" in reason for reason in result.reasons)


def test_patch_quality_penalizes_trivial_tests(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(
        run_dir / "summary.json",
        json.dumps(
            {
                "execution_memory_used": True,
                "execution_multifile_plan_used": True,
                "execution_multifile_selected_files": [
                    "app/auth/password_reset.py",
                    "tests/test_password_reset.py",
                ],
            },
            indent=2,
        ),
    )
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/auth/password_reset.py
+++ b/app/auth/password_reset.py
@@ -1,2 +1,5 @@
 def send_password_reset(email):
+    MAX_ATTEMPTS = 7
+    if MAX_ATTEMPTS < 1:
+        return False
     return True
--- /dev/null
+++ b/tests/test_password_reset.py
@@ -0,0 +1,3 @@
+def test_password_reset_constant() -> None:
+    MAX_ATTEMPTS = 7
+    assert MAX_ATTEMPTS == 7
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == NEEDS_REVISION
    assert result.score < 100
    assert any("tests look trivial" in reason for reason in result.reasons)


def test_patch_quality_rejects_unplanned_creation_patch(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(
        run_dir / "summary.json",
        json.dumps(
            {
                "execution_layer_creation_used": True,
                "execution_layer_proposed_files": ["app/services/password_reset_rate_limit.py"],
            },
            indent=2,
        ),
    )
    _patch(
        run_dir,
        "patch_001.diff",
        '''--- /dev/null
+++ b/app/misc_new.py
@@ -0,0 +1,2 @@
+def unrelated_helper() -> bool:
+    return True
''',
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == REJECTED
    assert "unplanned_creation_file" in result.validation_errors


def test_low_value_comment_only_patch(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/auth/password_reset.py
+++ b/app/auth/password_reset.py
@@ -1,2 +1,3 @@
 def send_password_reset(email):
+    # ANN patch proposal: add rate limiting later
     return True
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == LOW_VALUE_COMMENT_ONLY
    assert result.score < 20
    assert any("Comment-only" in reason for reason in result.reasons)


def test_unconnected_logic_patch(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(run_dir / "03_code_revised.md", "FILES TO MODIFY\n- app/auth/guards.py\n\nCODE CHANGES\n- Improve auth guard behavior.\n")
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/misc.py
+++ b/app/misc.py
@@ -1,1 +1,4 @@
 VALUE = 1
+def orphan_security_helper(value):
+    return value == "unused"
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == UNCONNECTED_LOGIC
    assert any("disconnected" in reason.lower() for reason in result.reasons)


def test_dangerous_command_is_rejected(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/auth/password_reset.py
+++ b/app/auth/password_reset.py
@@ -1,2 +1,3 @@
 def send_password_reset(email):
+    os.system("echo unsafe")
     return True
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == REJECTED
    assert result.validation_passed is False
    assert "dangerous_content_present" in result.validation_errors


def test_protected_path_is_rejected(tmp_path: Path, monkeypatch) -> None:
    project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _write(project_root / "training" / "datasets" / "generated.py", "VALUE = 1\n")
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/training/datasets/generated.py
+++ b/training/datasets/generated.py
@@ -1,1 +1,2 @@
 VALUE = 1
+VALUE = 2
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == REJECTED
    assert any("protected_path_modified" in error for error in result.validation_errors)


def test_memory_aware_patch_scores_memory_reuse(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/auth/password_reset.py
+++ b/app/auth/password_reset.py
@@ -1,2 +1,5 @@
 def send_password_reset(email):
+    MAX_ATTEMPTS = 7
+    if MAX_ATTEMPTS < 1:
+        return False
     return True
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == IMPLEMENTATION_READY
    assert any("Memory constants" in reason for reason in result.reasons)
    assert result.score >= 90


def test_mixed_patch_set_uses_worst_quality(tmp_path: Path, monkeypatch) -> None:
    _project_root, run_dir = _run_dir(tmp_path, monkeypatch)
    _patch(
        run_dir,
        "patch_001.diff",
        """--- a/app/auth/password_reset.py
+++ b/app/auth/password_reset.py
@@ -1,2 +1,4 @@
 def send_password_reset(email):
+    if not email:
+        return False
     return True
""",
    )
    _patch(
        run_dir,
        "patch_002.diff",
        """--- a/app/auth/password_reset.py
+++ b/app/auth/password_reset.py
@@ -1,2 +1,3 @@
 def send_password_reset(email):
+    # TODO: implement later
     return True
""",
    )

    result = evaluate_patch_quality(run_dir)

    assert result.decision == LOW_VALUE_COMMENT_ONLY
    assert result.score < 20
    parsed = parse_patch_quality_report(result.report)
    assert [block["patch"] for block in parsed] == ["patch_001.diff", "patch_002.diff"]

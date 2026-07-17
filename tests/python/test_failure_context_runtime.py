import json
from pathlib import Path

from agentic_network.failure_context.runtime import (
    compile_failure_context,
    compile_pipeline_failure_context,
    isolate_cross_domain_root_cause,
    render_failure_context_markdown,
    write_failure_context_artifacts,
)
from agentic_network.fixer_agent.runtime import run_fixer_agent


VALID_FIX_PLAN = """FIX SUMMARY
- Fix the localized failing function.

REQUIREMENT FIXES
- No requirement changes are required.

ARCHITECTURE FIXES
- No architecture changes are required.

IMPLEMENTATION FIXES
- Update only the targeted failing function.

TEST FIXES
- Re-run the failing regression test.

SECURITY FIXES
- Preserve existing validation behavior.

PRIORITY ORDER
- Patch the localized function first.

READY FOR RE-REVIEW
Yes

CONFIDENCE
High"""


def test_compile_failure_context_ast_localizes_python_trace(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text(
        "\n".join(
            [
                "def untouched() -> int:",
                "    return 1",
                "",
                "def calculate_total(value: int) -> int:",
                "    subtotal = value + 1",
                "    return subtotal / 0",
                "",
                "def after() -> int:",
                "    return 3",
            ]
        ),
        encoding="utf-8",
    )
    stderr = f'Traceback\n  File "{source}", line 6, in calculate_total\nZeroDivisionError'

    context = compile_failure_context(project_root=tmp_path, stderr=stderr)

    assert context["status"] == "TARGETED"
    assert context["limits"]["whole_file_sent"] is False
    target = context["targets"][0]
    assert target["ast_node_type"] == "FunctionDef"
    assert target["symbol"] == "calculate_total"
    assert target["line_start"] == 4
    assert target["line_end"] == 6
    assert "return subtotal / 0" in target["source_excerpt"]
    assert "def untouched" not in target["source_excerpt"]
    assert "def after" not in target["source_excerpt"]


def test_compile_failure_context_preserves_code_blocks_in_trace(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_app.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "def test_example():\n    assert generated() == '```python kept```'\n",
        encoding="utf-8",
    )

    report = (
        f"{test_file}:2: AssertionError\n"
        "Captured output:\n"
        "```python\n"
        "print('normal markdown code block')\n"
        "```"
    )

    markdown = render_failure_context_markdown(
        compile_failure_context(project_root=tmp_path, test_report=report)
    )

    assert "normal markdown code block" in markdown
    assert "```python kept```" in markdown


def test_compile_failure_context_excludes_protected_paths(tmp_path: Path) -> None:
    model_file = tmp_path / "models" / "bad.py"
    model_file.parent.mkdir()
    model_file.write_text("def secret_model():\n    return 'do not include'\n", encoding="utf-8")

    context = compile_failure_context(
        project_root=tmp_path,
        stderr=f'File "{model_file}", line 1, in secret_model',
    )

    target = context["targets"][0]
    assert target["excluded"] is True
    assert target["reason"] == "protected_path"
    assert target["source_excerpt"] == ""
    assert "do not include" not in json.dumps(context)


def test_compile_pipeline_failure_context_uses_patch_and_test_refs(tmp_path: Path) -> None:
    app_file = tmp_path / "apps" / "api" / "main.py"
    app_file.parent.mkdir(parents=True)
    app_file.write_text(
        "def create_user(payload):\n    return payload['email']\n",
        encoding="utf-8",
    )
    outputs = {
        "reviewer": "IMPLEMENTATION RISKS\n- Missing validation bug needs fix.",
        "test_runner": "apps/api/main.py:2: AssertionError",
        "execution": "diff --git a/apps/api/main.py b/apps/api/main.py\n@@ -1 +1 @@",
    }

    context = compile_pipeline_failure_context(project_root=tmp_path, outputs=outputs)

    assert context["status"] == "TARGETED"
    assert context["patch_files"] == ["apps/api/main.py"]
    assert context["targets"][0]["symbol"] == "create_user"


def test_write_failure_context_artifacts_creates_json_and_markdown(tmp_path: Path) -> None:
    context = compile_failure_context(reviewer_report="bug: missing edge case")

    json_path, markdown_path = write_failure_context_artifacts(tmp_path, context)

    saved = json.loads(Path(json_path).read_text(encoding="utf-8"))
    markdown = Path(markdown_path).read_text(encoding="utf-8")
    assert saved["status"] == "TRACE_ONLY"
    assert "FAILURE CONTEXT" in markdown
    assert "bug: missing edge case" in markdown


def test_fixer_receives_targeted_failure_context() -> None:
    seen_prompt = ""
    failure_context = "FAILURE CONTEXT\n- Status: TARGETED\n- Path: app.py\n"

    def response(*, prompt: str) -> str:
        nonlocal seen_prompt
        seen_prompt = prompt
        return VALID_FIX_PLAN

    result = run_fixer_agent(
        user_request="Fix failing test",
        product_requirements="REQUIREMENTS\n- Keep behavior stable.",
        architecture_plan="TECHNICAL SUMMARY\n- Localized change.",
        code_plan="CODE CHANGES\n- Update app.py.",
        test_plan="TEST SCENARIOS\n- Re-run failing test.",
        security_review="SECURITY FINDINGS\n- No new auth risk.",
        reviewer_report="APPROVAL STATUS\nNeeds Fixes\n\nCONFIDENCE\nHigh",
        failure_context=failure_context,
        response_generator=response,
    )

    assert result.failure_context_input == failure_context
    assert "TARGETED FAILURE CONTEXT" in seen_prompt
    assert "- Status: TARGETED" in seen_prompt


def test_cross_domain_isolation_ranks_migration_and_compose_for_stripe_failure(
    tmp_path: Path,
) -> None:
    webhook = tmp_path / "apps" / "api" / "billing" / "webhooks.py"
    webhook.parent.mkdir(parents=True)
    webhook.write_text(
        "def handle_stripe_webhook(payload):\n"
        "    return persist_customer(payload['customer'])\n",
        encoding="utf-8",
    )
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n"
        "  redis:\n"
        "    ports:\n"
        "      - '6380:6379'\n"
        "  postgres:\n"
        "    image: postgres:16\n",
        encoding="utf-8",
    )
    migration = tmp_path / "apps" / "api" / "alembic" / "versions" / "001_billing.py"
    migration.parent.mkdir(parents=True)
    migration.write_text(
        "def upgrade():\n"
        "    op.add_column('accounts', sa.Column('stripe_id', sa.String()))\n",
        encoding="utf-8",
    )
    test_file = tmp_path / "tests" / "integration" / "test_billing.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "def test_webhook_signature():\n"
        "    assert signed_webhook() == 200\n",
        encoding="utf-8",
    )
    stderr = (
        f'Traceback\n  File "{webhook}", line 2, in handle_stripe_webhook\n'
        "psycopg.errors.UndefinedTable: relation stripe_customers does not exist\n"
        "FAILED tests/integration/test_billing.py::test_webhook_signature"
    )

    context = compile_failure_context(
        project_root=tmp_path,
        stderr=stderr,
        commands=[["python", "-m", "pytest", "tests/integration/test_billing.py"]],
    )
    isolation = context["root_cause_isolation"]

    assert isolation["failure_type"] == "integration_boundary_failure"
    assert {"Stripe", "PostgreSQL"}.issubset(set(isolation["systems"]))
    suspect_paths = [suspect["path"] for suspect in isolation["ranked_suspects"]]
    assert "apps/api/alembic/versions/001_billing.py" in suspect_paths
    assert "tests/integration/test_billing.py" in suspect_paths
    assert isolation["fix_policy"][
        "do_not_rewrite_symptom_node_until_cross_domain_suspects_checked"
    ] is True
    assert isolation["ranked_suspects"][0]["confidence"] > isolation["symptom"]["confidence"]


def test_cross_domain_isolation_ranks_frontend_config_for_typescript_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "apps" / "web" / "src" / "App.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("export function App() { return <main /> }\n", encoding="utf-8")
    vite = tmp_path / "vite.config.ts"
    vite.write_text(
        "import react from '@vitejs/plugin-react'\n"
        "export default { plugins: [react()] }\n",
        encoding="utf-8",
    )
    package_json = tmp_path / "package.json"
    package_json.write_text(
        '{"scripts":{"test":"vitest"},"devDependencies":{"vite":"latest","typescript":"latest"}}',
        encoding="utf-8",
    )
    report = (
        "FAIL apps/web/src/App.test.tsx\n"
        "Error: Transform failed with 1 error\n"
        "vite Node API failed while compiling TypeScript React component\n"
        "at apps/web/src/App.tsx:1:31"
    )

    isolation = isolate_cross_domain_root_cause(
        project_root=tmp_path,
        trace_text=report,
        targets=[],
        commands=["npm test"],
    )

    assert isolation["failure_type"] == "integration_boundary_failure"
    assert "Frontend" in isolation["systems"]
    suspect_domains = {suspect["domain"] for suspect in isolation["ranked_suspects"]}
    assert {"frontend_config", "package_manifest"}.issubset(suspect_domains)


def test_failure_context_markdown_includes_cross_domain_policy(tmp_path: Path) -> None:
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services:\n  redis:\n    ports: ['6380:6379']\n", encoding="utf-8")
    context = compile_failure_context(
        project_root=tmp_path,
        stderr="redis connection refused on port 6379 during integration test",
    )

    markdown = render_failure_context_markdown(context)

    assert "CROSS-DOMAIN ROOT CAUSE ISOLATION" in markdown
    assert "do_not_rewrite_symptom_node_until_cross_domain_suspects_checked" in markdown
    assert "docker-compose.yml" in markdown


def test_failure_context_includes_test_validity_gate_for_bad_test_contract(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_billing.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_total_type():\n    assert isinstance(total(), int)\n", encoding="utf-8")

    context = compile_failure_context(
        project_root=tmp_path,
        test_report=f"{test_file}:2: AssertionError: expected int got float",
        product_requirements="Billing totals must preserve cents as decimal float values.",
        test_plan="Assert billing total is a float with cents preserved.",
    )
    markdown = render_failure_context_markdown(context)

    assert context["test_validity"]["status"] == "TEST_EXPECTATION_SUSPECT"
    assert context["test_validity"]["fix_policy"][
        "do_not_modify_code_under_test_until_test_contract_validated"
    ] is True
    assert context["test_validity"]["contract_evidence"]["contract_authority"]["owner"] == "PRODUCT_AGENT_REQUIREMENTS"
    assert "TEST VALIDITY GATE" in markdown
    assert "Contract authority" in markdown
    assert "repair_or_regenerate_test_before_code_fix" in markdown

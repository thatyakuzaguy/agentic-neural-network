import json
from pathlib import Path

from dataset_generation.export_product_jsonl import export_approved_examples
from dataset_generation.generate_product_dataset import TaskRow, generate_raw_examples, load_tasks
from dataset_generation.generate_tasks import DOMAINS, generate_tasks, write_tasks
from dataset_generation.review_product_dataset import review_raw_directory, review_response


VALID_RESPONSE = """REQUIREMENTS
- Build tenant-scoped CSV import for authorized users.

AMBIGUITIES
- Maximum CSV size is not specified.

ASSUMPTIONS
- Tenant identity comes from authenticated context.

ACCEPTANCE CRITERIA
- Unauthorized users receive 403.
- Successful imports create an auditable job.

RISKS
- Large imports may exceed worker capacity.

CONFIDENCE
Medium
"""


class _FakeProductAgent:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def run(self, input_text: str) -> str:
        self.seen.append(input_text)
        return VALID_RESPONSE


def test_generate_tasks_writes_requested_count_and_covers_domains(tmp_path: Path) -> None:
    tasks = generate_tasks(22, seed=7)
    output = tmp_path / "tasks.jsonl"

    write_tasks(tasks, output)

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    covered_domains = {domain for row in rows for domain in row["domains"]}
    assert len(rows) == 22
    assert {domain.id for domain in tasks} == {f"product-task-{index:06d}" for index in range(1, 23)}
    assert set(DOMAINS) <= covered_domains


def test_load_tasks_accepts_generated_jsonl(tmp_path: Path) -> None:
    output = tmp_path / "tasks.jsonl"
    write_tasks(generate_tasks(3), output)

    tasks = load_tasks(output)

    assert [task.id for task in tasks] == [
        "product-task-000001",
        "product-task-000002",
        "product-task-000003",
    ]
    assert all(task.instruction for task in tasks)


def test_generate_raw_examples_saves_product_agent_output_and_resumes(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    agent = _FakeProductAgent()
    tasks = [TaskRow("product-task-000001", "Create a FastAPI import feature.", ["FastAPI"])]

    first_count = generate_raw_examples(tasks, agent, raw_dir)
    second_count = generate_raw_examples(tasks, agent, raw_dir)

    payload = json.loads((raw_dir / "product-task-000001.json").read_text(encoding="utf-8"))
    assert first_count == 1
    assert second_count == 0
    assert agent.seen == ["Create a FastAPI import feature."]
    assert payload["response"] == VALID_RESPONSE.strip()
    assert payload["teacher_model"] == "deepseek"


def test_review_response_approves_required_product_shape() -> None:
    review = review_response("Create a FastAPI import feature.", VALID_RESPONSE)

    assert review.approved is True
    assert review.findings == []
    assert "STATIC SANITY CHECK FINDINGS" in review.static_sanity


def test_review_response_rejects_bad_shape_and_static_sanity_findings() -> None:
    response = """<think>hidden</think>
REQUIREMENTS
- Claim 100% coverage without execution evidence.

CONFIDENCE
Sure
"""

    review = review_response("Create a monitored API.", response)

    assert review.approved is False
    assert "Static sanity checker reported blocking findings." in review.findings
    assert "Response contains DeepSeek reasoning tags." in review.findings
    assert any("Missing required sections" in finding for finding in review.findings)


def test_review_raw_directory_splits_approved_and_rejected(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    approved_dir = tmp_path / "approved"
    rejected_dir = tmp_path / "rejected"
    raw_dir.mkdir()
    (raw_dir / "good.json").write_text(
        json.dumps(
            {
                "id": "good",
                "instruction": "Create a FastAPI import feature.",
                "response": VALID_RESPONSE,
            }
        ),
        encoding="utf-8",
    )
    (raw_dir / "bad.json").write_text(
        json.dumps(
            {
                "id": "bad",
                "instruction": "Create a FastAPI import feature.",
                "response": "REQUIREMENTS\n- Missing most sections.",
            }
        ),
        encoding="utf-8",
    )

    approved_count, rejected_count = review_raw_directory(raw_dir, approved_dir, rejected_dir)

    assert approved_count == 1
    assert rejected_count == 1
    assert (approved_dir / "good.json").exists()
    assert (rejected_dir / "bad.json").exists()


def test_export_approved_examples_writes_instruction_response_jsonl(tmp_path: Path) -> None:
    approved_dir = tmp_path / "approved"
    approved_dir.mkdir()
    (approved_dir / "example.json").write_text(
        json.dumps(
            {
                "instruction": "Create a FastAPI import feature.",
                "response": VALID_RESPONSE,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "product_agent_gold_v1.jsonl"

    count = export_approved_examples(approved_dir, output)

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert count == 1
    assert rows == [
        {
            "instruction": "Create a FastAPI import feature.",
            "response": VALID_RESPONSE.strip(),
        }
    ]

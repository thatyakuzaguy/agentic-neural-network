"""Generate realistic Product Agent self-instruct tasks."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_OUTPUT = Path("training/datasets/product_agent/tasks.jsonl")
DEFAULT_SEED = 20260612

DOMAINS = (
    "FastAPI",
    "Django",
    "APIs",
    "Security",
    "DevOps",
    "Monitoring",
    "RBAC",
    "Audit logging",
    "Data pipelines",
    "CLI tools",
    "Microservices",
)

_SYSTEMS = (
    "multi-tenant SaaS CRM",
    "billing operations platform",
    "developer portal",
    "internal compliance console",
    "customer support workflow tool",
    "identity administration service",
    "data ingestion platform",
    "marketplace back office",
)

_CONSTRAINTS = (
    "must preserve tenant isolation and avoid leaking cross-tenant data",
    "must be observable with structured logs, metrics, and trace identifiers",
    "must support retries without duplicate side effects",
    "must include human-reviewable audit evidence",
    "must fail closed on missing permissions or invalid configuration",
    "must be deployable through Docker Compose and CI validation",
)

_BLUEPRINTS = (
    (
        ("FastAPI", "APIs", "RBAC"),
        "Design a FastAPI endpoint for {system} that lets authorized users {action}; "
        "{constraint}.",
    ),
    (
        ("Django", "Security", "Audit logging"),
        "Plan a Django feature for {system} where administrators {action}; "
        "{constraint}.",
    ),
    (
        ("APIs", "Microservices", "Monitoring"),
        "Define product requirements for an API gateway flow in {system} that needs to {action}; "
        "{constraint}.",
    ),
    (
        ("Security", "RBAC", "Audit logging"),
        "Specify requirements for a sensitive operation in {system} that allows users to "
        "{action}; {constraint}.",
    ),
    (
        ("DevOps", "Monitoring", "Microservices"),
        "Plan the rollout requirements for a microservice in {system} that will {action}; "
        "{constraint}.",
    ),
    (
        ("Data pipelines", "Monitoring", "APIs"),
        "Define a data pipeline feature for {system} that needs to {action}; {constraint}.",
    ),
    (
        ("CLI tools", "DevOps", "Security"),
        "Write product requirements for a CLI tool used by platform engineers to {action}; "
        "{constraint}.",
    ),
    (
        ("FastAPI", "Data pipelines", "Audit logging"),
        "Plan a FastAPI-backed ingestion workflow for {system} that can {action}; "
        "{constraint}.",
    ),
    (
        ("Django", "RBAC", "Monitoring"),
        "Define requirements for a Django admin workflow in {system} where managers "
        "{action}; {constraint}.",
    ),
    (
        ("Microservices", "Security", "DevOps"),
        "Specify a cross-service workflow in {system} for teams that need to {action}; "
        "{constraint}.",
    ),
    (
        ("Audit logging", "APIs", "Monitoring"),
        "Create product requirements for audit-friendly API behavior in {system} when users "
        "{action}; {constraint}.",
    ),
)

_ACTIONS = (
    "import customer records from CSV files",
    "rotate API credentials for an integration",
    "approve high-risk account changes",
    "trigger asynchronous report generation",
    "sync webhook events from external providers",
    "bulk update user roles",
    "export filtered audit logs",
    "quarantine suspicious records for review",
    "replay failed background jobs",
    "create tenant-scoped service accounts",
    "publish data quality findings",
    "manage feature flags across environments",
)


@dataclass(frozen=True)
class ProductTask:
    """One instruction row for Product Agent dataset generation."""

    id: str
    instruction: str
    domains: list[str]


def generate_tasks(count: int, *, seed: int = DEFAULT_SEED) -> list[ProductTask]:
    """Return deterministic, varied software engineering product tasks."""

    if count < 1:
        raise ValueError("--count must be at least 1")

    rng = random.Random(seed)
    tasks: list[ProductTask] = []
    for index in range(count):
        domains, template = _BLUEPRINTS[index % len(_BLUEPRINTS)]
        instruction = template.format(
            system=rng.choice(_SYSTEMS),
            action=rng.choice(_ACTIONS),
            constraint=rng.choice(_CONSTRAINTS),
        )
        tasks.append(
            ProductTask(
                id=f"product-task-{index + 1:06d}",
                instruction=instruction,
                domains=list(domains),
            )
        )
    return tasks


def write_tasks(tasks: list[ProductTask], output: Path) -> None:
    """Write tasks as JSONL."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        for task in tasks:
            file.write(json.dumps(asdict(task), ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Product Agent self-instruct tasks.")
    parser.add_argument("--count", type=int, required=True, help="Number of tasks to generate.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Task JSONL output path.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Deterministic task seed.")
    return parser.parse_args()


def _reject_c_drive(path: Path) -> None:
    resolved = path.resolve()
    if resolved.drive.upper() == "C:":
        raise ValueError(f"Refusing to write dataset artifacts on C: {resolved}")


def main() -> int:
    args = parse_args()
    _reject_c_drive(args.output)
    tasks = generate_tasks(args.count, seed=args.seed)
    write_tasks(tasks, args.output)
    print(f"Saved {len(tasks)} tasks to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

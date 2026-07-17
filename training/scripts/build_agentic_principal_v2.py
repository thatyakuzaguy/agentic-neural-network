import json
from pathlib import Path

OUT_FILE = Path("training/datasets/agentic_principal_v2.jsonl")

SWEBENCH_FILE = Path("training/datasets/swebench_v2.jsonl")

ADR_DIRS = [
    Path("/mnt/e/datasets/premium/architecture-decision-record"),
]

OWASP_DIRS = [
    Path("/mnt/e/datasets/premium/CheatSheetSeries"),
    Path("/mnt/e/datasets/premium/ASVS"),
]


def write_example(f, system, user, assistant):
    row = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }
    f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_swebench(out):
    if not SWEBENCH_FILE.exists():
        print("SWE-Bench file not found, skipping.")
        return 0

    count = 0

    with open(SWEBENCH_FILE, "r", encoding="utf-8") as f:
        for line in f:
            out.write(line)
            count += 1

    return count


def load_markdown_documents(out, root_dirs, doc_type):
    count = 0

    for root in root_dirs:
        if not root.exists():
            print(f"Missing: {root}")
            continue

        for file in root.rglob("*.md"):
            try:
                content = file.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )

                content = content.strip()

                if len(content) < 500:
                    continue

                content = content[:12000]

                if doc_type == "adr":
                    system = (
                        "You are a principal software architect. "
                        "Explain architecture decisions, tradeoffs, risks, "
                        "alternatives and consequences."
                    )

                    user = (
                        f"Review this Architecture Decision Record and "
                        f"summarize the decision, tradeoffs, risks and "
                        f"implementation guidance.\n\n{content[:4000]}"
                    )

                    assistant = (
                        content
                    )

                elif doc_type == "security":
                    system = (
                        "You are a senior application security engineer. "
                        "Provide security reviews, threat models, "
                        "mitigations and compliance recommendations."
                    )

                    user = (
                        f"Review the following security guidance and "
                        f"produce implementation recommendations.\n\n"
                        f"{content[:4000]}"
                    )

                    assistant = (
                        content
                    )

                else:
                    continue

                write_example(
                    out,
                    system,
                    user,
                    assistant,
                )

                count += 1

            except Exception as e:
                print("Failed:", file, e)

    return count


def main():
    OUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    total = 0

    with open(
        OUT_FILE,
        "w",
        encoding="utf-8",
    ) as out:

        print("Adding SWE-Bench...")
        total += load_swebench(out)

        print("Adding ADRs...")
        total += load_markdown_documents(
            out,
            ADR_DIRS,
            "adr",
        )

        print("Adding OWASP...")
        total += load_markdown_documents(
            out,
            OWASP_DIRS,
            "security",
        )

    print()
    print(f"Created: {OUT_FILE}")
    print(f"Total examples: {total}")


if __name__ == "__main__":
    main()

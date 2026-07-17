from agentic_engineering_network.security.review import SecurityReviewer


def test_security_reviewer_detects_secrets() -> None:
    review = SecurityReviewer().review_generated_files(
        {"app.py": "OPENAI_API_KEY = 'sk-abcdefghijklmnopqrstuvwxyz'\n"}
    )

    assert not review.passed
    assert review.findings


def test_security_reviewer_passes_clean_files() -> None:
    review = SecurityReviewer().review_generated_files({"README.md": "No secrets here.\n"})

    assert review.passed


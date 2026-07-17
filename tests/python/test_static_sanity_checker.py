from agentic_network.pipeline.static_sanity_checker import (
    StaticSanityInput,
    run_static_sanity_checker,
)


def test_static_sanity_checker_catches_datetime_fromisoformat_without_import() -> None:
    output = run_static_sanity_checker(
        StaticSanityInput(
            task="Parse timestamps",
            code='parsed = datetime.fromisoformat(payload["timestamp"])',
        )
    )

    assert "datetime.fromisoformat" in output


def test_static_sanity_checker_allows_datetime_fromisoformat_with_import() -> None:
    output = run_static_sanity_checker(
        StaticSanityInput(
            task="Parse timestamps",
            code=(
                "from datetime import datetime\n\n"
                'parsed = datetime.fromisoformat(payload["timestamp"])'
            ),
        )
    )

    assert "- No findings." in output


def test_static_sanity_checker_catches_pytest_fail_without_import() -> None:
    output = run_static_sanity_checker(
        StaticSanityInput(task="Write tests", tests='pytest.fail("missing branch")')
    )

    assert "pytest.fail" in output


def test_static_sanity_checker_catches_test_client_without_import() -> None:
    output = run_static_sanity_checker(
        StaticSanityInput(task="Write FastAPI tests", tests="client = TestClient(app)")
    )

    assert "TestClient" in output


def test_static_sanity_checker_catches_naive_utcnow_isoformat_when_utc_required() -> None:
    output = run_static_sanity_checker(
        StaticSanityInput(
            task="Return a UTC timestamp",
            code="timestamp = datetime.utcnow().isoformat()",
        )
    )

    assert "utcnow().isoformat" in output


def test_static_sanity_checker_catches_naive_utcnow_isoformat_in_fixer_output() -> None:
    output = run_static_sanity_checker(
        StaticSanityInput(
            task="Return an ISO 8601 UTC timestamp with a Z suffix",
            code="timestamp = datetime.utcnow().isoformat()",
            reviewer="- Replace naive UTC timestamp generation.",
            fixer=(
                "FIXED IMPLEMENTATION\n"
                "```python\n"
                "timestamp = datetime.utcnow().isoformat()\n"
                "```\n"
                "CHANGE SUMMARY\n"
                "- Fixed the UTC timestamp issue."
            ),
        )
    )

    assert "BLOCKING: Naive UTC timestamp detected" in output
    assert "Fixer repeats the original UTC timestamp defect" in output


def test_static_sanity_checker_catches_timestamp_z_suffix_mismatch() -> None:
    output = run_static_sanity_checker(
        StaticSanityInput(
            task="Return a UTC timestamp with a Z suffix",
            code="timestamp = datetime.utcnow().isoformat()",
            tests='assert response.json()["timestamp"].endswith("Z")',
        )
    )

    assert "Tests require a Z timestamp suffix" in output
    assert "Implementation and tests contradict" in output


def test_static_sanity_checker_accepts_timezone_aware_z_timestamp() -> None:
    output = run_static_sanity_checker(
        StaticSanityInput(
            task="Return a UTC timestamp with a Z suffix",
            code=(
                "from datetime import datetime, timezone\n\n"
                "timestamp = (\n"
                "    datetime.now(timezone.utc)\n"
                "    .isoformat()\n"
                '    .replace("+00:00", "Z")\n'
                ")"
            ),
            tests='assert response.json()["timestamp"].endswith("Z")',
        )
    )

    assert "- No findings." in output


def test_static_sanity_checker_catches_unverified_coverage_claims() -> None:
    output = run_static_sanity_checker(
        StaticSanityInput(task="Write tests", tests="COVERAGE NOTES\n- 100% coverage")
    )

    assert "Coverage or test-pass claims" in output

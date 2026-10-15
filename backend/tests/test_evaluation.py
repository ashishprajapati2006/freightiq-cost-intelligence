"""Unit tests for the 3-run reproducibility and deterministic evaluation harness."""

from backend.app.services.evaluation import run_reproducibility_check, verify_guardrails


def test_three_run_reproducibility():
    """Verify that three consecutive runs on the same input produce bit-for-bit identical results."""
    report = run_reproducibility_check(num_runs=3)

    assert report["is_reproducible"] is True
    assert report["num_runs"] == 3
    assert report["total_records"] == 728
    assert report["discrepancies"] == []


def test_guardrails_pass_all_notes():
    """Verify that all 10 context notes pass the guardrail test."""
    guardrails = verify_guardrails()
    assert guardrails["all_guardrails_passed"] is True
    assert guardrails["total_notes_tested"] == 10

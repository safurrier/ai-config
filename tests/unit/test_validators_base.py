"""Tests for ai_config.validators.base module."""


from ai_config.validators.base import ValidationReport, ValidationResult


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_pass_status(self) -> None:
        """ValidationResult with pass status."""
        result = ValidationResult(
            check_name="test_check",
            status="pass",
            message="Check passed",
        )
        assert result.check_name == "test_check"
        assert result.status == "pass"
        assert result.message == "Check passed"
        assert result.details is None
        assert result.fix_hint is None

    def test_warn_status(self) -> None:
        """ValidationResult with warn status."""
        result = ValidationResult(
            check_name="test_check",
            status="warn",
            message="Check has warning",
            details="Some additional context",
        )
        assert result.status == "warn"
        assert result.details == "Some additional context"

    def test_fail_status(self) -> None:
        """ValidationResult with fail status."""
        result = ValidationResult(
            check_name="test_check",
            status="fail",
            message="Check failed",
            details="Error details",
            fix_hint="Run this command to fix",
        )
        assert result.status == "fail"
        assert result.fix_hint == "Run this command to fix"

    def test_all_fields(self) -> None:
        """ValidationResult with all fields populated."""
        result = ValidationResult(
            check_name="full_check",
            status="fail",
            message="Full message",
            details="Full details",
            fix_hint="Full hint",
        )
        assert result.check_name == "full_check"
        assert result.status == "fail"
        assert result.message == "Full message"
        assert result.details == "Full details"
        assert result.fix_hint == "Full hint"


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_passed_with_all_pass(self) -> None:
        """Report with all pass results should have passed=True."""
        report = ValidationReport(
            target="test_target",
            results=[
                ValidationResult(check_name="check1", status="pass", message="OK"),
                ValidationResult(check_name="check2", status="pass", message="OK"),
            ],
        )
        assert report.passed is True
        assert report.has_warnings is False

    def test_passed_with_warnings_only(self) -> None:
        """Report with warnings but no failures should have passed=True."""
        report = ValidationReport(
            target="test_target",
            results=[
                ValidationResult(check_name="check1", status="pass", message="OK"),
                ValidationResult(check_name="check2", status="warn", message="Warning"),
            ],
        )
        assert report.passed is True
        assert report.has_warnings is True

    def test_not_passed_with_failure(self) -> None:
        """Report with any failure should have passed=False."""
        report = ValidationReport(
            target="test_target",
            results=[
                ValidationResult(check_name="check1", status="pass", message="OK"),
                ValidationResult(check_name="check2", status="fail", message="Failed"),
            ],
        )
        assert report.passed is False

    def test_not_passed_with_failure_and_warnings(self) -> None:
        """Report with failures and warnings should have passed=False."""
        report = ValidationReport(
            target="test_target",
            results=[
                ValidationResult(check_name="check1", status="warn", message="Warning"),
                ValidationResult(check_name="check2", status="fail", message="Failed"),
            ],
        )
        assert report.passed is False
        assert report.has_warnings is True

    def test_empty_results(self) -> None:
        """Report with no results should have passed=True."""
        report = ValidationReport(target="test_target", results=[])
        assert report.passed is True
        assert report.has_warnings is False

    def test_target_field(self) -> None:
        """Report should preserve target field."""
        report = ValidationReport(target="claude", results=[])
        assert report.target == "claude"

    def test_multiple_failures(self) -> None:
        """Report with multiple failures should have passed=False."""
        report = ValidationReport(
            target="test_target",
            results=[
                ValidationResult(check_name="check1", status="fail", message="Failed 1"),
                ValidationResult(check_name="check2", status="fail", message="Failed 2"),
                ValidationResult(check_name="check3", status="fail", message="Failed 3"),
            ],
        )
        assert report.passed is False
        assert report.has_warnings is False

    def test_multiple_warnings(self) -> None:
        """Report with multiple warnings should have has_warnings=True."""
        report = ValidationReport(
            target="test_target",
            results=[
                ValidationResult(check_name="check1", status="warn", message="Warn 1"),
                ValidationResult(check_name="check2", status="warn", message="Warn 2"),
                ValidationResult(check_name="check3", status="pass", message="OK"),
            ],
        )
        assert report.passed is True
        assert report.has_warnings is True

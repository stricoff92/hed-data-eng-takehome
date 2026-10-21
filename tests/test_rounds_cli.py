import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import rounds

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SUPPLIED_FIXTURES = REPOSITORY_ROOT / "takehome-packet" / "fixtures"


class CheckCommandTest(unittest.TestCase):
    def run_check(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = rounds.main(["check", *arguments])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_check_reports_success_against_the_supplied_fixture_pack(self) -> None:
        exit_code, stdout, stderr = self.run_check("--fixtures", str(SUPPLIED_FIXTURES))

        self.assertEqual(exit_code, rounds.EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertNotEqual(stdout, "")

    def test_check_exits_with_a_usage_error_when_the_fixtures_directory_does_not_exist(self) -> None:
        exit_code, stdout, stderr = self.run_check("--fixtures", str(REPOSITORY_ROOT / "no-such-pack"))

        self.assertEqual(exit_code, rounds.EXIT_USAGE)
        self.assertIn("no fixture pack at", stderr)
        self.assertEqual(stdout, "")

    def test_check_exits_with_a_usage_error_when_the_directory_is_not_a_fixture_pack(self) -> None:
        exit_code, _, stderr = self.run_check("--fixtures", str(REPOSITORY_ROOT))

        self.assertEqual(exit_code, rounds.EXIT_USAGE)
        self.assertIn("is not a fixture pack", stderr)

    def test_check_refuses_an_as_of_with_no_timezone_rather_than_guessing_one(self) -> None:
        exit_code, _, stderr = self.run_check(
            "--fixtures", str(SUPPLIED_FIXTURES), "--as-of", "2026-10-21T07:30:00",
        )

        self.assertEqual(exit_code, rounds.EXIT_USAGE)
        self.assertIn("has no timezone", stderr)

    def test_check_refuses_an_as_of_that_is_not_a_timestamp_at_all(self) -> None:
        exit_code, _, stderr = self.run_check(
            "--fixtures", str(SUPPLIED_FIXTURES), "--as-of", "yesterday",
        )

        self.assertEqual(exit_code, rounds.EXIT_USAGE)
        self.assertIn("--as-of", stderr)

    def test_check_refuses_an_as_of_from_before_the_snapshot_was_captured(self) -> None:
        # Earlier than the snapshot would date its runs and commits to the future.
        exit_code, _, stderr = self.run_check(
            "--fixtures", str(SUPPLIED_FIXTURES), "--as-of", "2026-10-18T07:30:00Z",
        )

        self.assertEqual(exit_code, rounds.EXIT_USAGE)
        self.assertIn("cannot be un-seen", stderr)

    def test_check_accepts_an_as_of_after_the_snapshot_so_a_coming_breach_can_be_seen(self) -> None:
        exit_code, stdout, stderr = self.run_check(
            "--fixtures", str(SUPPLIED_FIXTURES), "--as-of", "2026-10-21T07:30:00Z",
            "--out", str(REPOSITORY_ROOT / "tests" / "written-by-the-cli-test"),
        )

        self.assertEqual(exit_code, rounds.EXIT_OK)
        self.assertEqual(stderr, "")
        self.assertIn("as of 2026-10-21T07:30:00Z", stdout)

        written = REPOSITORY_ROOT / "tests" / "written-by-the-cli-test"
        for name in ("report.json", "report.md", "telemetry.ndjson"):
            (written / name).unlink()
        written.rmdir()

    def test_check_refuses_to_write_its_report_where_a_file_already_sits(self) -> None:
        exit_code, _, stderr = self.run_check(
            "--fixtures", str(SUPPLIED_FIXTURES), "--out", str(REPOSITORY_ROOT / "README.md"),
        )

        self.assertEqual(exit_code, rounds.EXIT_USAGE)
        self.assertIn("is a file", stderr)

    def test_check_refuses_to_write_its_report_inside_the_read_only_fixture_pack(self) -> None:
        exit_code, _, stderr = self.run_check(
            "--fixtures", str(SUPPLIED_FIXTURES), "--out", str(SUPPLIED_FIXTURES / "reports"),
        )

        self.assertEqual(exit_code, rounds.EXIT_USAGE)
        self.assertIn("read-only", stderr)


if __name__ == "__main__":
    unittest.main()

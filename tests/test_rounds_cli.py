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

    def test_check_refuses_to_write_its_report_inside_the_read_only_fixture_pack(self) -> None:
        exit_code, _, stderr = self.run_check(
            "--fixtures", str(SUPPLIED_FIXTURES), "--out", str(SUPPLIED_FIXTURES / "reports"),
        )

        self.assertEqual(exit_code, rounds.EXIT_USAGE)
        self.assertIn("read-only", stderr)


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import zju_cc98


class CC98WrapperTests(unittest.TestCase):
    def test_cli_installed_checks_for_cc98_binary(self):
        with patch("zju_cc98.shutil.which", return_value="/usr/local/bin/cc98") as which:
            self.assertTrue(zju_cc98._cc98_cli_installed())
        which.assert_called_once_with("cc98")

    def test_help_returns_error_when_cc98_cli_missing(self):
        with (
            patch.object(sys, "argv", ["zju_cc98.py", "--help"]),
            patch("zju_cc98._cc98_cli_installed", return_value=False),
            patch("zju_cc98.subprocess.run") as run,
        ):
            self.assertEqual(zju_cc98.main(), 1)
        run.assert_not_called()

    def test_help_delegates_to_cc98_help_when_installed(self):
        with (
            patch.object(sys, "argv", ["zju_cc98.py", "--help"]),
            patch("zju_cc98._cc98_cli_installed", return_value=True),
            patch("zju_cc98.subprocess.run") as run,
        ):
            self.assertEqual(zju_cc98.main(), 0)
        run.assert_called_once_with(["cc98", "--help"])

    def test_subcommand_is_passed_through_unchanged(self):
        completed = MagicMock(returncode=7)
        with (
            patch.object(sys, "argv", ["zju_cc98.py", "search", "常微分", "--json"]),
            patch("zju_cc98._cc98_cli_installed", return_value=True),
            patch("zju_cc98.subprocess.run", return_value=completed) as run,
        ):
            self.assertEqual(zju_cc98.main(), 7)
        run.assert_called_once_with(["cc98", "search", "常微分", "--json"])

    def test_subcommand_returns_error_when_cc98_cli_missing(self):
        with (
            patch.object(sys, "argv", ["zju_cc98.py", "me"]),
            patch("zju_cc98._cc98_cli_installed", return_value=False),
            patch("zju_cc98.subprocess.run") as run,
        ):
            self.assertEqual(zju_cc98.main(), 1)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

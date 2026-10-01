import sys
from pathlib import Path
import subprocess
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from playwright_session_action import cli_action_result


class CliActionResultTests(unittest.TestCase):
    def test_stderr_failure_preserved(self):
        result = subprocess.CompletedProcess([], 1, "", '{"ok":false,"status":"DOWNLOAD_PATH_UNAVAILABLE","allow_new_export":false}')
        self.assertEqual(cli_action_result(result)["status"], "DOWNLOAD_PATH_UNAVAILABLE")

    def test_success(self):
        self.assertTrue(cli_action_result(subprocess.CompletedProcess([], 0, '{"ok":true}', ""))["ok"])

    def test_nonzero_success_is_uncertain(self):
        result = cli_action_result(subprocess.CompletedProcess([], 1, '{"ok":true}', "crash"))
        self.assertFalse(result["ok"])
        self.assertFalse(result["allow_new_export"])

    def test_unstructured_failure_is_not_lost(self):
        result = cli_action_result(subprocess.CompletedProcess([], 1, "", "closed"))
        self.assertEqual(result["message"], "closed")


if __name__ == "__main__":
    unittest.main()

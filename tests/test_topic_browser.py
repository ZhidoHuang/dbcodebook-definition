import concurrent.futures
import importlib.util
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "topic_browser", Path(__file__).resolve().parents[1] / "scripts/topic_browser.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TopicBrowserTests(unittest.TestCase):
    def test_distinct_topics_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            inputs = [Path(directory) / str(i) for i in range(20)]
            with concurrent.futures.ThreadPoolExecutor() as pool:
                results = list(pool.map(module.browser_paths, inputs))
            for field in ("session", "session_workdir", "profile"):
                self.assertEqual(len({result[field] for result in results}), 20)

    def test_resume_preserves_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "topic"
            self.assertEqual(module.browser_paths(path),
                             module.browser_paths(path / ".." / "topic"))


if __name__ == "__main__":
    unittest.main()

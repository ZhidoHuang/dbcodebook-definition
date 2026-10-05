"""Website preparation validation and browser-state regression tests (no website writes)."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_website import browser_code


class WebsitePrepareTests(unittest.TestCase):
    def test_inputs(self):
        good = dict(base_url='http://localhost:8000', post_id='132', identity_title_parts=['CHARLS', 'ADL'])
        self.assertIn('prepareWebsite(page', browser_code(good))
        for bad in [dict(base_url='http://user:pass@localhost'), dict(create=True),
                    dict(post_id='../edit'), dict(edit_id=True), dict(identity_title_parts=[]),
                    dict(base_url='http://localhost/path')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                browser_code({**good, **bad})
        browser_code(dict(base_url=good['base_url'], create=True))

    def test_browser_states(self):
        result = subprocess.run(['node', str(ROOT / 'tests/website_prepare_cases.js')],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()

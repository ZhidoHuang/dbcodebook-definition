import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from nhanes_export_contract import validate_package
from prepare_source_selection import build_action, browser_code
from recover_dbcodebook_export import database_page_url
from check_definition_output import check_long_table, expected_raw_header


class NhanesAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.write('raw_codebook.csv', [['Variable', 'File type', 'newname'], ['RIAGENDR', 'uniqID', 'A_sex']])

    def write(self, name, rows):
        with (self.root / name).open('w', encoding='utf-8', newline='') as f:
            csv.writer(f).writerows(rows)

    def package(self, rows):
        self.write('raw_data.csv', [['SEQN', 'YEAR', 'A_sex'], *rows])
        return validate_package(self.root, ['raw_data.csv'], ['A_sex'])

    def test_distinct_overlapping_cycles_preserved(self):
        self.assertEqual(self.package([['1.0', '2017-2018', 'female'], ['1.0', '2017-2020', 'female']])['rows'], 2)

    def test_duplicate_numeric_equivalent_person_rejected(self):
        with self.assertRaises(ValueError):
            self.package([['1', '2017-2018', 'female'], ['1.0', '2017-2018', 'female']])

    def test_bad_period_and_missing_person_rejected(self):
        for row in [['1', '2018-2017', 'female'], ['', '2017-2018', 'female'], ['1', '2018', 'female']]:
            with self.assertRaises(ValueError):
                self.package([row])

    def test_repeated_source_not_accepted(self):
        self.write('raw_codebook.csv', [['Variable', 'File type', 'newname'], ['RIAGENDR', 'reID', 'A_sex']])
        with self.assertRaises(ValueError):
            self.package([['1', '2017-2018', 'female']])

    def test_explicit_source_type_required(self):
        action = build_action('RIAGENDR (常规(唯一SEQN))=A_sex', 'http://localhost:8000/home/')
        action['database'] = 'nhanes'
        self.assertIn('data-source-type', browser_code(action, 'select'))
        action = build_action('RIAGENDR (pooled)=A_sex', action['url'])
        action['database'] = 'nhanes'
        with self.assertRaises(ValueError):
            browser_code(action, 'select')

    def test_home_route(self):
        self.assertEqual(database_page_url("http://localhost:8000", "nhanes"), "http://localhost:8000/home/")

    def test_long_table_keys(self):
        header = expected_raw_header('nhanes', ['A_sex'])
        self.assertEqual(header, ['SEQN', 'YEAR', 'A_sex'])
        self.assertTrue(check_long_table([header, ['1', '2017-2018', 'female']], header, [], 'nhanes'))
        self.assertFalse(check_long_table([header, ['1', '2017-2018', 'female'], ['1', '2017-2018', 'female']], header, [], 'nhanes'))


if __name__ == '__main__':
    unittest.main()

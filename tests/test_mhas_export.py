import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from mhas_export_contract import CORE, RAW_NAME, validate_package


class MhasExport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        with (self.root / 'raw_codebook.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows([['Variable', 'newname'], ['H13 (' + CORE + ')', 'dress']])

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rows, header=None):
        with (self.root / RAW_NAME).open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(header or ['ID', 'Wave_id', 'UNHHIDNP', 'dress'])
            w.writerows(rows)

    def check(self):
        return validate_package(self.root, [RAW_NAME], ['dress'])

    def test_person_period_and_leading_zero(self):
        self.write([['2001|001', '2001', '001', '1'], ['2003|001', '2003', '001', '2']])
        self.assertEqual(self.check()['rows'], 2)

    def test_invalid_identity_period_and_extra_source(self):
        for rows, header in [
            ([['a', '2001', '', '1']], None),
            ([['a', '2016', '001', '1']], None),
            ([['a', '2001', '001', '1'], ['b', '2001', '001', '2']], None),
            ([['a', '2001', '001', '1', 'unselected']], ['ID','Wave_id','UNHHIDNP','dress','other']),
        ]:
            self.write(rows, header)
            with self.assertRaises(ValueError): self.check()

    def test_core_without_canonical_key_and_component_mismatch(self):
        header = ['ID', 'Wave_id', 'unhhid', 'ps3', 'cunicah', 'np', 'dress']
        rows = [['2001|00100|1', '2001', '00100', '1', '', '', '1'],
                ['2012|00100|1', '2012', '', '', '00100', '1', '2']]
        self.write(rows, header)
        self.assertEqual(self.check()['key'], ['ID', 'Wave_id'])
        rows[1][5] = '2'
        self.write(rows, header)
        with self.assertRaises(ValueError): self.check()

    def test_no_flattening_or_other_module(self):
        self.write([['a', '2001', '001', '1']])
        with self.assertRaises(ValueError):
            validate_package(self.root, ['raw_data.csv'], ['dress'])
        (self.root/'raw_codebook.csv').write_text('Variable,newname\nH13 (OTHER),dress\n')
        with self.assertRaises(ValueError): self.check()


if __name__ == '__main__': unittest.main()

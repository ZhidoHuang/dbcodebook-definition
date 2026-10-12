"""Local receipts are explicit, portable evidence, not an exemption from source checks."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from local_source_evidence import validate_local_evidence
from check_definition_source_record import validate_directory_entries


class LocalEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.binding = {'schema': 'dbcodebook.local-binding.v1', 'ok': True,
                        'database': 'share', 'language': None,
                        'website_url': 'http://fixture/home/share/',
                        'dictionary_sha256': 'a'*64,
                        'mapping': {'kind': 'runtime_settings_same_file'}}
        self.bref = self.save('binding.json', self.binding)
        self.receipt = {'schema': 'dbcodebook.local-source.v1', 'ok': True,
                        'database': 'share', 'language': None,
                        'binding_sha256': self.bref['sha256'], 'dictionary_sha256': 'a'*64,
                        'request': {'kind': 'detail'},
                        'sources': [{'file': 'F', 'directory_paths': [['Core', 'Mental health']],
                                     'periods': [{'period': 'Wave 1', 'available': True,
                                                  'actual_variable': 'euro1',
                                                  'source_identity': 'euro1 (F)'}]}]}
        self.rref = self.save('detail.json', self.receipt)
        self.record = {'database': 'SHARE', 'dbcodebook_url': 'http://fixture/home/share/',
                       'source_access': {'mode': 'local_dictionary', 'binding': self.bref,
                                         'receipts': [self.rref]},
                       'source_groups': [{'source_identities': ['euro1 (F)'], 'periods': ['Wave 1'],
                                          'discovery': {'mode': 'local_dictionary'}}]}

    def save(self, name, data):
        path = self.root/name
        path.write_text(json.dumps(data), encoding='utf-8')
        return {'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

    def validate(self):
        return validate_local_evidence(self.record, self.root/'record.json')

    def test_valid_and_ordinary_unchanged(self):
        data = self.validate()
        local = [{'full_path': 'Core > Mental health', 'verified_in_ui': False,
                  'verified_in_local_dictionary': True, 'purpose': 'actual discovery'}]
        self.assertEqual(validate_directory_entries(local, 'SHARE', data), {'Core > Mental health'})
        with self.assertRaises(ValueError):
            validate_directory_entries(local, 'SHARE')
        web = copy.deepcopy(local)
        web[0]['verified_in_ui'] = True
        validate_directory_entries(web, 'SHARE')
        with self.assertRaises(ValueError):
            validate_directory_entries(web, 'SHARE', data)
        self.assertIsNone(validate_local_evidence({}, self.root/'record.json'))

    def test_wrong_database_site_period_source(self):
        original = copy.deepcopy(self.record)
        for change in [
            lambda r: r.update(database='ELSA'),
            lambda r: r.update(dbcodebook_url='http://other/home/share/'),
            lambda r: r['source_groups'][0].update(periods=['Wave 2']),
            lambda r: r['source_groups'][0].update(source_identities=['euro1 (Wrong)']),
        ]:
            self.record = copy.deepcopy(original)
            change(self.record)
            with self.assertRaises(ValueError):
                self.validate()

    def test_modified_missing_failed_and_mixed_evidence(self):
        (self.root/'detail.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.validate()
        for field, value in [('ok', False), ('binding_sha256', 'b'*64),
                             ('dictionary_sha256', 'b'*64), ('language', 'ko')]:
            data = copy.deepcopy(self.receipt)
            data[field] = value
            self.record['source_access']['receipts'] = [self.save('detail.json', data)]
            with self.assertRaises(ValueError):
                self.validate()
        (self.root/'detail.json').unlink()
        with self.assertRaises(OSError):
            self.validate()

    def test_unseen_directory_rejected(self):
        with self.assertRaises(ValueError):
            validate_directory_entries([{'full_path': 'Invented', 'verified_in_ui': False,
                                         'verified_in_local_dictionary': True, 'purpose': 'x'}],
                                       'SHARE', self.validate())


if __name__ == '__main__':
    unittest.main()

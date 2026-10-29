import csv
import sys
import tempfile
import unittest
import zipfile
import io
from contextlib import redirect_stdout
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from mhas_export_contract import (CORE, NOK, RAW_NAME, ANTHROPOMETRICS, HEAVY_METALS,
                                  raw_files, primary_raw, validate_package)


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

    def ancillary(self, sources=(ANTHROPOMETRICS, HEAVY_METALS), provenance=False):
        aliases = {ANTHROPOMETRICS: 'crp_12', HEAVY_METALS: 'ti'}
        book = [['Variable', 'newname', 'File type']]
        for source in sources:
            alias = aliases[source]
            book.append([alias + ' (' + source + ')', alias, 'uniqPersonID'])
            if source == ANTHROPOMETRICS:
                header = ['ID', 'Wave_id', 'cunicah', 'np', 'acthog', 'ent2', 'unhhid', 'ps3', alias]
                rows = [['2001|38|1', '2001', '', '', '', '', '38', '1', ''],
                        ['2003|38|1|2', '2003', '38', '', '1', '2', '', '', ''],
                        ['2012|38|1', '2012', '38', '1', '', '', '', '', '3'],
                        ['2016|38|1', '2016', '38', '1', '', '', '', '', '']]
            else:
                header = ['ID', 'Wave_id', 'cunicah', 'np', alias]
                rows = [['2018|001|10', '2018', '001', '10', '0.5']]
            if provenance:
                header += ['source_file', 'source_row']
                rows = [r + ['released-file', str(i)] for i, r in enumerate(rows, 1)]
            with (self.root / ('raw_data_' + source + '.csv')).open('w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerows([header, *rows])
        with (self.root / 'raw_codebook.csv').open('w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(book)
        return ['raw_data_' + s + '.csv' for s in sources], [aliases[s] for s in sources]

    def mutate_csv(self, name, change):
        path = self.root / name
        with path.open(encoding='utf-8', newline='') as f:
            rows = list(csv.reader(f))
        change(rows)
        with path.open('w', encoding='utf-8', newline='') as f:
            csv.writer(f).writerows(rows)

    def test_ancillary_separate_files_and_single_product(self):
        for sources in [(ANTHROPOMETRICS,), (HEAVY_METALS,), (ANTHROPOMETRICS, HEAVY_METALS)]:
            for path in self.root.glob('raw_data*.csv'): path.unlink()
            members, expected = self.ancillary(sources)
            result = validate_package(self.root, members, expected)
            self.assertEqual(set(result['files']), set(members))
            self.assertEqual(result['rows'], 5 if len(sources) == 2 else (4 if sources[0] == ANTHROPOMETRICS else 1))
            self.assertEqual([p.name for p in raw_files(self.root)], sorted(members))
            self.assertIn(primary_raw(self.root).name, members)
            for fact in result['files'].values():
                self.assertNotIn('source_row', fact['header'])
            if ANTHROPOMETRICS in sources:
                self.assertEqual(result['files'][members[0]]['periods'], ['2001', '2003', '2012', '2016'])

    def test_optional_provenance_and_decimal_identity_components(self):
        members, expected = self.ancillary((HEAVY_METALS,), provenance=True)
        self.mutate_csv(members[0], lambda rows: rows[1].__setitem__(3, '10.0'))
        result = validate_package(self.root, members, expected)
        self.assertIn('source_row', result['identity_columns'])

    def test_ancillary_wrong_period_identity_duplicate_or_row_shape(self):
        for change in [lambda rows: rows[1].__setitem__(1, '2016'),
                       lambda rows: rows[1].__setitem__(0, ''),
                       lambda rows: rows[1].__setitem__(3, '11'),
                       lambda rows: rows.append(rows[1].copy()),
                       lambda rows: rows[0].__setitem__(1, 'wrong'),
                       lambda rows: rows[0].__setitem__(3, 'cunicah'),
                       lambda rows: rows[1].append('extra'),
                       lambda rows: rows[1].pop()]:
            members, expected = self.ancillary((HEAVY_METALS,))
            self.mutate_csv(members[0], change)
            with self.assertRaises(ValueError): validate_package(self.root, members, expected)
        members, expected = self.ancillary((ANTHROPOMETRICS,))
        (self.root / ('raw_data_' + HEAVY_METALS + '.csv')).unlink()
        self.mutate_csv(members[0], lambda rows: rows[4].__setitem__(1, '2015'))
        with self.assertRaises(ValueError): validate_package(self.root, members, expected)
        members, expected = self.ancillary((ANTHROPOMETRICS,))
        def wrong_period_components(rows):
            rows[4] = ['2016|38|1', '2016', '', '', '', '', '38', '1', '']
        self.mutate_csv(members[0], wrong_period_components)
        with self.assertRaises(ValueError): validate_package(self.root, members, expected)

    def test_ancillary_dictionary_and_per_file_alias_boundaries(self):
        for change in [lambda rows: rows[1].__setitem__(0, 'crp_12 (' + CORE + ')'),
                       lambda rows: rows[1].__setitem__(0, ' (' + ANTHROPOMETRICS + ')'),
                       lambda rows: rows[1].__setitem__(2, 'rePersonID'),
                       lambda rows: rows[1].__setitem__(1, 'other'),
                       lambda rows: rows.append(rows[1].copy()),
                       lambda rows: rows[1].__setitem__(0, 'crp_12 (OTHER)')]:
            members, expected = self.ancillary()
            self.mutate_csv('raw_codebook.csv', change)
            with self.assertRaises(ValueError): validate_package(self.root, members, expected)
        members, expected = self.ancillary()
        self.mutate_csv(members[0], lambda rows: rows[0].__setitem__(-1, 'ti'))
        with self.assertRaises(ValueError): validate_package(self.root, members, expected)
        members, expected = self.ancillary()
        self.mutate_csv(members[1], lambda rows: rows[0].__setitem__(2, 'unhhid'))
        with self.assertRaises(ValueError): validate_package(self.root, members, expected)

    def test_ancillary_extra_missing_flattened_and_core_mixed_files(self):
        members, expected = self.ancillary()
        for names in [members[:1], members + [members[0]], members + [RAW_NAME],
                      ['raw_data.csv'], members + ['raw_data_OTHER.csv']]:
            with self.assertRaises(ValueError): validate_package(self.root, names, expected)
        (self.root / 'raw_data_OTHER.csv').write_text('unselected')
        with self.assertRaises(ValueError): validate_package(self.root, members, expected)

    def test_analysis_identity_reads_both_ancillary_files(self):
        from check_definition_output import check_identity_values
        members, expected = self.ancillary()
        contract = validate_package(self.root, members, expected)
        paths = raw_files(self.root)
        header = contract['header']
        rows = [header]
        for path in paths:
            with path.open(encoding='utf-8', newline='') as f:
                for row in csv.DictReader(f):
                    if row['Wave_id'] in {'2012', '2018'}:
                        rows.append([row.get(name, '') for name in header])
        results = []
        check_identity_values(paths[0], header, rows, header, results,
                              db='mhas', raw_paths=paths)
        self.assertTrue(all(r['ok'] for r in results), results)
        rows[-1][header.index('ID')] = '2018|001|99'
        results = []
        check_identity_values(paths[0], header, rows, header, results,
                              db='mhas', raw_paths=paths)
        self.assertTrue(any(not r['ok'] for r in results), results)

    def test_archive_receiver_keeps_both_file_facts(self):
        from recover_dbcodebook_export import inspect_archive
        members, expected = self.ancillary()
        archive = self.root / 'download.zip'
        with zipfile.ZipFile(archive, 'w') as target:
            for name in [*members, 'raw_codebook.csv']:
                target.write(self.root / name, name)
        result = inspect_archive(archive, expected, 'mhas')
        self.assertEqual(set(result['data']), set(members))
        self.assertEqual(sum(x['rows'] for x in result['data'].values()), 5)

    def test_output_checker_reports_unsupported_raw_file(self):
        from check_definition_output import main
        (self.root / 'raw_data_OTHER.csv').write_text('unselected')
        output = io.StringIO()
        with patch.object(sys, 'argv', ['check_definition_output.py', '--formal-dir', str(self.root), '--db', 'mhas']), redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertIn('MHAS source-file contracts', output.getvalue())

    def nok_package(self):
        self.write([['2003|001|1|2', '2003', '001', '1', '2', '1']],
                   ['ID', 'Wave_id', 'cunicah', 'acthog', 'ent2', 'dress'])
        name = 'raw_data_' + NOK + '.csv'
        with (self.root / name).open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['ID', 'Wave_id', 'cunicah', 'acthog', 'ent2', 'UNHHIDNP', 'sc1'])
            w.writerow(['2003|001|1|2', '2003', '001', '1', '2', '', '1'])
            w.writerow(['2018|00012', '2018', '', '', '', '00012', ''])
        with (self.root / 'raw_codebook.csv').open('w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows([
                ['Variable', 'newname', 'File type'],
                ['H13 (' + CORE + ')', 'dress', 'uniqPersonID'],
                ['sc1 (' + NOK + ')', 'sc1', 'uniqPersonID']])
        return name

    def test_core_nok_same_id_stays_in_separate_files(self):
        name = self.nok_package()
        facts = validate_package(self.root, [RAW_NAME, name], ['dress', 'sc1'])
        self.assertEqual(facts['rows'], 3)
        self.assertEqual(facts['key'], ['source_module', 'ID', 'Wave_id'])
        self.assertEqual(facts['files'][name]['periods'], ['2003', '2018'])

    def test_nok_preview_default_unhhid_is_preserved(self):
        from mhas_export_contract import validate_scoped_analysis
        name = self.nok_package()
        def add_default(rows):
            rows[0].append('unhhid')
            for row in rows[1:]: row.append('')
        self.mutate_csv(name, add_default)
        facts = validate_package(self.root, [RAW_NAME, name], ['dress', 'sc1'])
        self.assertIn('unhhid', facts['files'][name]['identity_columns'])
        header=['source_module', 'ID','Wave_id','cunicah','acthog','ent2','UNHHIDNP','unhhid','core_result','nok_result']
        rows=[header,[CORE,'2003|001|1|2','2003','001','1','2','','','1',''],
              [NOK,'2003|001|1|2','2003','001','1','2','','','','1']]
        record={'approved_analysis_vars':['core_result','nok_result'], 'mhas_analysis_scope':{
            CORE:{'analysis_periods':['2003'],'result_variables':['core_result']},
            NOK:{'analysis_periods':['2003'],'result_variables':['nok_result']}}}
        self.assertEqual(validate_scoped_analysis(raw_files(self.root),rows,header,record)['rows'],2)
        index=header.index('unhhid')
        with self.assertRaises(ValueError):
            validate_scoped_analysis(raw_files(self.root),[row[:index]+row[index+1:] for row in rows],header[:index]+header[index+1:],record)

    def test_nok_period_identity_shape_is_strict(self):
        name = self.nok_package()
        path = self.root / name
        text = path.read_text()
        path.write_text(text.replace('2003|001|1|2,2003,001,1,2,,1',
                                     '2003|00012,2003,,,,00012,1'))
        with self.assertRaises(ValueError):
            validate_package(self.root, [RAW_NAME, name], ['dress', 'sc1'])

    def test_nok_scoped_analysis_and_missing_boundaries(self):
        from check_definition_output import check_identity_values
        name = self.nok_package()
        paths = raw_files(self.root)
        header = ['source_module','ID','Wave_id','cunicah','acthog','ent2','UNHHIDNP','core_result','nok_result']
        rows = [header, [CORE,'2003|001|1|2','2003','001','1','2','','1',''],
                [NOK,'2003|001|1|2','2003','001','1','2','','','1']]
        record = {'approved_analysis_vars':['core_result','nok_result'], 'identity_keys':['source_module','ID','Wave_id'], 'mhas_analysis_scope': {
            CORE: {'analysis_periods':['2003'], 'result_variables':['core_result']},
            NOK: {'analysis_periods':['2003'], 'result_variables':['nok_result']}}}
        def check(candidate, rec=record):
            results=[]
            check_identity_values(paths[0],header,candidate,header,results,db='mhas',raw_paths=paths,source_record=rec)
            return all(r['ok'] for r in results)
        self.assertTrue(check(rows))
        from mhas_export_contract import validate_scoped_analysis
        with self.assertRaises(ValueError):
            validate_scoped_analysis(paths,[r[1:] for r in rows],header[1:],record)

        import copy
        scoped=copy.deepcopy(record)
        scoped['source_groups']=[{'source_identities':['sc1 ('+NOK+')'], 'raw_variables':['sc1']}]
        scoped['mhas_selection']={'mode':'raw_columns','dictionary_sha256':'a'*64,'inputs':[
            {'file':NOK,'variable_id':'sc1','available_periods':['2003'],
             'period_bindings':{'2003':'sc1'},'aliases':{'sc1':'sc1'}}]}
        self.assertTrue(check(rows,scoped))
        raw=self.root/name; original=raw.read_text()
        raw.write_text(original.replace('2018|00012,2018,,,,00012,','2018|00012,2018,,,,00012,1'))
        self.assertFalse(check(rows,scoped))
        raw.write_text(original)

        from check_definition_source_record import analysis_identity_contract, validate_render_identity_contract
        self.assertEqual(analysis_identity_contract(record, 'MHAS')['identity_keys'], ['source_module','ID','Wave_id'])
        validate_render_identity_contract('render_definition_bundle(identity_keys=c("source_module","ID","Wave_id"))',record,'MHAS')
        with self.assertRaises(ValueError):
            validate_render_identity_contract('render_definition_bundle()',record,'MHAS')
        import copy
        broken=copy.deepcopy(record); broken['mhas_analysis_scope'][NOK]['result_variables']=['source_module']
        self.assertFalse(check(rows,broken))
        broken=copy.deepcopy(record); broken['approved_analysis_vars'].append('missing_result')
        self.assertFalse(check(rows,broken))
        self.assertFalse(check(rows, {}))
        self.assertFalse(check(rows[:2]))
        self.assertFalse(check(rows+[rows[-1]]))
        for index,value in [(0,CORE),(1,'2003|009|1|2'),(3,'9'),(7,'1'),(2,'2018')]:
            changed=[list(r) for r in rows];changed[-1][index]=value
            self.assertFalse(check(changed), (index,value))
        later=rows+[[NOK,'2018|00012','2018','','','','00012','','']]
        self.assertFalse(check(later))

    def test_nok_six_periods_and_rejected_packages(self):
        name=self.nok_package()
        path=self.root/name
        with path.open('a',newline='',encoding='utf-8') as f:
            csv.writer(f).writerows([
                ['2012|001|2','2012','001','','','',''],
            ])
        # Missing np rejects a seemingly plausible later ID.
        with self.assertRaises(ValueError): validate_package(self.root,[RAW_NAME,name],['dress','sc1'])
        with path.open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(['ID','Wave_id','cunicah','acthog','ent2','UNHHIDNP','np','sc1'])
            w.writerow(['2003|001|1|2','2003','001','1','2','','','1'])
            for period in ['2012','2015','2021']:
                w.writerow([period+'|001|02',period,'001','','','','02',''])
            for period in ['2018','2024']:
                w.writerow([period+'|00012',period,'','','','00012','',''])
        self.assertEqual(validate_package(self.root,[RAW_NAME,name],['dress','sc1'])['files'][name]['rows'],6)
        for extra in ['raw_data_MHAS_SURVEY_SAB.csv','raw_data_linked.csv','raw_data_MHAS_ANCILLARY_HEAVY_METALS.csv']:
            p=self.root/extra;p.write_text('ID,Wave_id\n')
            with self.assertRaises(ValueError): raw_files(self.root)
            p.unlink()
        with self.assertRaises(ValueError): validate_package(self.root,[name],['dress','sc1'])

    def test_nok_receiver_keeps_attached_later_raw_rows(self):
        from recover_dbcodebook_export import inspect_archive
        name=self.nok_package()
        archive=self.root/'nok.zip'
        with zipfile.ZipFile(archive,'w') as target:
            for member in [RAW_NAME,name,'raw_codebook.csv']:
                target.write(self.root/member,member)
        facts=inspect_archive(archive,['dress','sc1'],'mhas')
        self.assertEqual(facts['data'][name]['rows'],2)


if __name__ == '__main__': unittest.main()

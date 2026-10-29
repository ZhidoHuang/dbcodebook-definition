import csv
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from nhanes_export_contract import validate_package, validate_medicine_package, build_medicine_download_action, medicine_source_columns
from prepare_source_selection import build_action, browser_code
from recover_dbcodebook_export import database_page_url
from check_definition_output import check_long_table, expected_raw_header, workbook_source_columns


class NhanesAdapterTests(unittest.TestCase):
    def test_medicine_export_preserves_seqn_only_contract(self):
        specs = [{'variable':'drug_I', 'list_id':'iVariables', 'selected_values':['CATEGORY']}]
        archive = self.root / 'medicine.zip'
        for rows, valid in [('1,1\n2,0\n', True), ('1,1\n1.0,0\n', False), ('1,2\n', False)]:
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('raw_drug.csv', 'SEQN,drug_I\n' + rows)
                package.writestr('raw_drug_detail.txt', '变量名: drug_I\n输入字段: CATEGORY\n')
            if valid:
                self.assertEqual(validate_medicine_package(archive, specs)['keys'], ['SEQN'])
                target = self.root / 'bookapp_medicine_download.zip'
                target.write_bytes(archive.read_bytes())
                with zipfile.ZipFile(target) as package:
                    for filename in ('raw_drug.csv','raw_drug_detail.txt'):
                        (self.root / filename).write_bytes(package.read(filename))
                record = {'medicine_export':{'variables':specs,'used_fields':['drug_I']}}
                self.assertEqual(medicine_source_columns(self.root, record), ['drug_I'])
                (self.root / 'raw_drug.csv').write_text('SEQN,drug_I\n1,0\n2,0\n')
                with self.assertRaises(ValueError):
                    medicine_source_columns(self.root, record)
            else:
                with self.assertRaises(ValueError):
                    validate_medicine_package(archive, specs)
        action = build_medicine_download_action('http://localhost:8000', 'one', self.root/'claim.json', specs)
        self.assertIn('downloadCapture', action['run_script'])
        self.assertIn('dbCodeBookMarkDownloadClickRequested();', action['run_script'])
        self.assertIn('Medicine selection differs', action['run_script'])

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

    def test_explicit_repeated_types_keep_person_rows(self):
        self.write('raw_codebook.csv', [['Variable', 'File type', 'newname'],
            ['RIAGENDR', 'uniqID', 'sex'], ['PADLEVEL (PAQIAF)', 'reID', 'level'],
            ['RXDUSE (RXQ_RX)', 'reID', 'use']])
        self.write('raw_data.csv', [['SEQN', 'YEAR', 'sex'], ['1', '2003-2004', 'female']])
        for name,column,value,document in [('PAQIAF','level','moderate','PAQIAF_C'),('RXQ_RX','use','yes','RXQ_RX_C')]:
            self.write('raw_data_'+name+'.csv', [['RowIndex','DOC_FILE','SEQN','YEAR',column],
                ['1',document,'1','2003-2004',value], ['2',document,'1','2003-2004',value]])
        data=validate_package(self.root,['raw_data.csv','raw_data_PAQIAF.csv','raw_data_RXQ_RX.csv'],['sex','level','use'])['files']
        self.assertEqual(data['raw_data_PAQIAF.csv']['rows'],2)
        self.assertEqual(data['raw_data_PAQIAF.csv']['person_periods'],1)
        self.assertEqual(data['raw_data_RXQ_RX.csv']['repeated_rows'],1)
        action=build_action('PADLEVEL (PAQIAF)=level\nRXDUSE (RXQ_RX)=use','http://localhost:8000/home/')
        action['database']='nhanes'
        self.assertIn('data-source-type',browser_code(action,'select'))

    def test_repeated_provenance_cannot_be_a_join_key_or_disappear(self):
        self.write('raw_codebook.csv',[['Variable','File type','newname'],['PADLEVEL (PAQIAF)','reID','level']])
        for row in [['1','','1','2003-2004','moderate'],['2','PAQIAF_C','1','2003-2004','moderate']]:
            self.write('raw_data_PAQIAF.csv',[['RowIndex','DOC_FILE','SEQN','YEAR','level'],row])
            with self.assertRaises(ValueError):
                validate_package(self.root,['raw_data_PAQIAF.csv'],['level'])

    def test_verified_document_cycle_without_year(self):
        self.write('raw_codebook.csv',[['Variable','File type','newname'],['PADLEVEL (PAQIAF)','reID','level']])
        self.write('raw_data_PAQIAF.csv',[['RowIndex','DOC_FILE','SEQN','level'],['1','PAQIAF.xpt','5.0','1.0'],['2','PAQIAF_B.xpt','5.0','1.0']])
        data=validate_package(self.root,['raw_data_PAQIAF.csv'],['level'])['files']['raw_data_PAQIAF.csv']
        self.assertEqual(data['person_periods'],2)
        self.assertEqual(data['document_periods'],{'PAQIAF.xpt':'1999-2000','PAQIAF_B.xpt':'2001-2002'})
        for header,row in [(['RowIndex','DOC_FILE','SEQN','level'],['1','PAQIAF_UNKNOWN.xpt','5','1']),(['RowIndex','DOC_FILE','SEQN','YEAR','level'],['1','PAQIAF.xpt','5','2001-2002','1'])]:
            self.write('raw_data_PAQIAF.csv',[header,row])
            with self.assertRaises(ValueError):validate_package(self.root,['raw_data_PAQIAF.csv'],['level'])

    def test_home_route(self):
        self.assertEqual(database_page_url("http://localhost:8000", "nhanes"), "http://localhost:8000/home/")

    def test_repeated_source_summary_preserves_explicit_lineage(self):
        self.write('raw_codebook.csv', [['Variable', 'File type', 'newname'],
            ['AGE', 'uniqID', 'age'], ['LEVEL (PAQIAF)', 'reID', 'level'],
            ['MINUTES (PAQIAF)', 'reID', 'minutes']])
        raw = ['age', 'level', 'minutes']
        summaries = [{'variable': 'moderate', 'source_variables': ['level', 'minutes'], 'method': '按人期及强度求和'},
                     {'variable': 'vigorous', 'source_variables': ['level', 'minutes'], 'method': '按人期及强度求和'}]
        columns, mapping = workbook_source_columns(self.root, raw, ['total'], summaries)
        self.assertEqual(columns, ['age', 'moderate', 'vigorous'])
        self.assertEqual(mapping['moderate'], ['level', 'minutes'])
        self.assertEqual(workbook_source_columns(self.root, raw, ['total'], None), (raw, {}))
        for invalid in [dict(summaries[0], source_variables=['age']),
                        dict(summaries[0], source_variables=['absent']),
                        dict(summaries[0], variable='total'), dict(summaries[0], method='')]:
            with self.assertRaises(ValueError):
                workbook_source_columns(self.root, raw, ['total'], [invalid])

    def test_long_table_keys(self):
        header = expected_raw_header('nhanes', ['A_sex'])
        self.assertEqual(header, ['SEQN', 'YEAR', 'A_sex'])
        self.assertTrue(check_long_table([header, ['1', '2017-2018', 'female']], header, [], 'nhanes'))
        self.assertFalse(check_long_table([header, ['1', '2017-2018', 'female'], ['1', '2017-2018', 'female']], header, [], 'nhanes'))


class NHANESIIIContractTests(unittest.TestCase):
    def test_default_period_projects_to_year_and_is_compared(self):
        from check_definition_output import check_identity_values
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / 'raw_data_NHANES_III.csv'
            with raw.open('w', encoding='utf-8', newline='') as stream:
                csv.writer(stream).writerows([['SEQN','_survey_period','age'],['01.0','1988-1991','44']])
            for year, expected in [('1988-1991', True), ('1991-1994', False)]:
                results = []
                check_identity_values(raw, ['SEQN','_survey_period','age'],
                                      [['SEQN','YEAR','age'],['01.0',year,44]],
                                      ['SEQN','YEAR','age'], results, 'nhanesiii')
                self.assertEqual(all(item['ok'] for item in results), expected, results)

    def test_unique_person_export_and_rejection_boundaries(self):
        from nhanesiii_export_contract import validate_package as historical, RAW_NAME
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def write(name, rows):
                with (root/name).open('w', encoding='utf-8-sig', newline='') as stream:
                    csv.writer(stream).writerows(rows)
            dictionary = [['Survey', 'Variable', 'Label', 'File type', 'newname'],
                          ['NHANES III', 'AGE (Adult)', 'Age', 'uniqPersonID', 'age']]
            write('raw_codebook.csv', dictionary)
            write(RAW_NAME, [['SEQN', '_survey_period', 'age'], ['01.0', '1988-1994', '44']])
            before = (root/RAW_NAME).read_bytes()
            self.assertEqual(historical(root, [RAW_NAME], ['age'])['files'][RAW_NAME]['rows'], 1)
            self.assertEqual(before, (root/RAW_NAME).read_bytes())
            for rows in [[['SEQN','age'],['1','44'],['01.0','45']],
                         [['SEQN','age'],['','44']],
                         [['SEQN','age','unselected'],['1','44','x']],
                         [['SEQN','_survey_period','age'],['1','1963-1994','44']]]:
                write(RAW_NAME, rows)
                with self.assertRaises(ValueError): historical(root, [RAW_NAME], ['age'])
            write(RAW_NAME, [['SEQN','age'],['1','44']])
            for field, value in [(0,'NHANES I'),(3,'rePersonID')]:
                changed = [dictionary[0], dictionary[1].copy()]
                changed[1][field] = value
                write('raw_codebook.csv', changed)
                with self.assertRaises(ValueError): historical(root, [RAW_NAME], ['age'])
            write('raw_codebook.csv', dictionary)
            with self.assertRaises(ValueError): historical(root, [RAW_NAME,'raw_data_imputations.csv'], ['age'])
            self.assertTrue(check_long_table([['SEQN','YEAR','age'],['1','1988-1994',44]],
                                            ['SEQN','YEAR','age'],[], 'nhanesiii'))


if __name__ == '__main__':
    unittest.main()

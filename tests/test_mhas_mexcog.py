"""Mex-Cog exports keep target-person identity, case and independent source rows."""
import csv
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from mhas_export_contract import (CORE, NOK, MEXCOG_COGNITIVE as MC,
    MEXCOG_INFORMANT as MI, HEAVY_METALS, validate_package,
    validate_analysis_scope, validate_scoped_analysis, raw_files)
from check_definition_output import check_identity_values


class MexCogExport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, modules=(CORE, NOK, MC, MI)):
        aliases = {CORE:'core_q', NOK:'nok_q', MC:'mc_q', MI:'mi_q'}
        book = [['Variable','newname','File type']]
        self.record = {'approved_analysis_vars':[], 'mhas_analysis_scope':{},
            'dbcodebook_url':'http://localhost/home/mhas/', 'source_groups':[],
            'mhas_selection':{'mode':'raw_columns','dictionary_sha256':'a'*64,'inputs':[]}}
        self.raw = {}; self.paths = []
        for module in modules:
            alias = aliases[module]
            header = ['ID','Wave_id','cunicah','np']
            if module in (MC, MI):
                header += ['CUNICAH','NP',alias]
                rows = [['2016|001|02','2016','001','02','','',''],
                        ['2021|001|02','2021','','','001','02','1']]
            else:
                header += [alias]
                rows = [['2021|001|02','2021','001','02','1']]
                if module == CORE: rows += [['2024|001|02','2024','001','02','']]
            path = self.root / ('raw_data_'+module+'.csv')
            with path.open('w',newline='',encoding='utf-8') as f:
                csv.writer(f).writerows([header,*rows])
            self.paths.append(path);self.raw[module]=(header,rows)
            book.append(['q ('+module+')',alias,'uniqPersonID'])
            result = alias+'_result'
            self.record['approved_analysis_vars'].append(result)
            self.record['mhas_analysis_scope'][module]={'analysis_periods':['2021'],'result_variables':[result]}
            self.record['source_groups'].append({'raw_variables':[alias],'source_identities':['q ('+module+')']})
            self.record['mhas_selection']['inputs'].append({'variable_id':'q_'+module,'file':module,
                'available_periods':['2021'],'available_bindings':{'2021':'q'},
                'period_bindings':{'2021':'q'},'aliases':{'q':alias}})
        with (self.root/'raw_codebook.csv').open('w',newline='',encoding='utf-8') as f:
            csv.writer(f).writerows(book)
        self.aliases=[aliases[m] for m in modules]
        return [p.name for p in self.paths]

    def analysis(self):
        header=['source_module','ID','Wave_id','cunicah','np','CUNICAH','NP']+self.record['approved_analysis_vars']
        rows=[header]
        for module,(fields,records) in self.raw.items():
            original=next(dict(zip(fields,v)) for v in records if v[1]=='2021')
            original['source_module']=module
            original[self.record['mhas_analysis_scope'][module]['result_variables'][0]]=1
            rows.append([original.get(k,'') for k in header])
        return rows

    def test_four_files_do_not_join_equal_ids_or_import_other_periods(self):
        members=self.fixture()
        facts=validate_package(self.root,members,self.aliases)
        self.assertEqual(facts['rows'],7)
        self.assertEqual(facts['key'],['source_module','ID','Wave_id'])
        rows=self.analysis()
        fact=validate_scoped_analysis(self.paths,rows,rows[0],self.record)
        self.assertEqual(fact['rows'],4)
        self.assertEqual(len({v[1] for v in rows[1:]}),1)

    def test_single_mex_cog_output_uses_scoped_validation_without_nok(self):
        self.fixture((MI,));rows=self.analysis();checks=[]
        check_identity_values(self.paths[0],self.raw[MI][0],rows,rows[0],checks,'mhas',self.paths,self.record)
        self.assertTrue(checks[0]['ok'])
        self.assertEqual(checks[0]['detail']['rows'],1)
        rows[1][rows[0].index('NP')]='2'
        checks=[]
        check_identity_values(self.paths[0],self.raw[MI][0],rows,rows[0],checks,'mhas',self.paths,self.record)
        self.assertFalse(checks[0]['ok'])

    def test_2021_identity_cannot_fall_back_to_lowercase_values(self):
        members=self.fixture((MC,))
        path=self.paths[0];fields,rows=self.raw[MC]
        rows[1][fields.index('cunicah')]='001';rows[1][fields.index('np')]='02'
        rows[1][fields.index('CUNICAH')]='999'
        with path.open('w',newline='',encoding='utf-8') as f:csv.writer(f).writerows([fields,*rows])
        with self.assertRaises(ValueError):validate_package(self.root,members,self.aliases)

    def test_missing_rows_cross_source_results_and_identity_changes_fail(self):
        self.fixture();rows=self.analysis()
        with self.assertRaises(ValueError):validate_scoped_analysis(self.paths,rows[:-1],rows[0],self.record)
        changed=copy.deepcopy(rows);changed[2][rows[0].index('mc_q_result')]=1
        with self.assertRaises(ValueError):validate_scoped_analysis(self.paths,changed,rows[0],self.record)
        changed=copy.deepcopy(rows);changed[3][rows[0].index('CUNICAH')]='1'
        with self.assertRaises(ValueError):validate_scoped_analysis(self.paths,changed,rows[0],self.record)

    def test_unverified_period_and_biomarker_mixing_remain_rejected(self):
        self.fixture((MC,))
        scopes=copy.deepcopy(self.record['mhas_analysis_scope']);scopes[MC]['analysis_periods']=['2024']
        with self.assertRaises(ValueError):validate_analysis_scope(scopes)
        (self.root/('raw_data_'+HEAVY_METALS+'.csv')).write_text('unselected',encoding='utf-8')
        with self.assertRaises(ValueError):raw_files(self.root)


if __name__=='__main__':unittest.main()

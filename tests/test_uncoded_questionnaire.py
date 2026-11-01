"""Narrow unencoded multiple-selection contract; no database-specific inputs."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from questionnaire_display import validate_uncoded_options, original_option_comparison
import check_definition_source_record as source_checker
from check_reader_copy import read_questionnaire_copy, questionnaire_copy_errors
from check_definition_readability import validate_questionnaire_rendering
from test_questionnaire_display_answers import markup


def fixture():
    item = {
        'evidence_id': 'q1', 'source_group':'group', 'question_id':'Q001',
        'question_text':'Original question.', 'question_text_mode':'verified_quote',
        'question_text_complete':True, 'periods':['2011'], 'response_type':'closed_options',
        'options':[{'value':'item_a','original_code':None,'label':'Apple'},
                   {'value':'item_b','original_code':None,'label':'None'}],
        'options_complete':True, 'skip_logic_status':'none', 'skip_logic':[],
        'local_material_status':'verified', 'rendered_in_copy':True, 'copy_locator':'问卷',
        'uncoded_options':{'selection':'multiple','value_role':'local_identity_not_original_code',
                           'evidence':'Source page 3 has unnumbered options.'},
        'display':{'question_text':'您拥有下列物品吗？', 'instructions':[],
                   'options':[{'value':'item_a','label':'苹果'}, {'value':'item_b','label':'None 没有'}],
                   'skip_logic':[]}}
    return {'schema_version':6, 'questionnaire_display_policy':'chinese_v1',
            'questionnaire_evidence':[item]}


def copy_text():
    return '### 2011 年\n问卷说明。\n\n#### Q001\n您拥有下列物品吗？\n- 苹果\n- None 没有\n'


class UncodedTests(unittest.TestCase):
    def check_both(self, text, record, good):
        errors = questionnaire_copy_errors({'questionnaire':read_questionnaire_copy(text)},record)
        self.assertEqual(not errors, good, errors)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p/'definition_search_record.json').write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
            (p/'note.md').write_text(markup(text),encoding='utf-8')
            if good:
                validate_questionnaire_rendering(p,p,'note.md')
            else:
                with self.assertRaises((ValueError,SystemExit)):
                    validate_questionnaire_rendering(p,p,'note.md')

    def test_text_and_render_exact_labels_and_order(self):
        r=fixture();s=copy_text();self.check_both(s,r,True)
        for bad in [s.replace('苹果','橙子'), s.replace('- 苹果\n- None 没有','- None 没有\n- 苹果'),
                    s.replace('- None 没有','- 2 None 没有')]:
            with self.subTest(bad=bad): self.check_both(bad,r,False)

    def test_declaration_fails_closed(self):
        mutations=[lambda q:q.update(uncoded_options=None),lambda q:q['uncoded_options'].update(evidence=''),
          lambda q:q['uncoded_options'].update(selection='unspecified'),
          lambda q:q['uncoded_options'].update(value_role='original_code'),
          lambda q:q['options'][0].pop('original_code'),lambda q:q['options'][0].update(original_code='1'),
          lambda q:q.update(periods=['2011','2013']),lambda q:q.update(skip_logic_status='unknown'),
          lambda q:q.update(local_material_status='missing'),lambda q:q.update(options_complete=False),
          lambda q:q.update(question_text_complete=False),lambda q:q.update(response_type='open_value'),
          lambda q:q['display'].update(combined_options={}),
          lambda q:q['display'].update(record_only_option_values=['item_a'])]
        self.assertTrue(validate_uncoded_options(fixture()['questionnaire_evidence'][0]))
        for change in mutations:
            q=fixture()['questionnaire_evidence'][0];change(q)
            with self.subTest(change=change),self.assertRaises(ValueError): validate_uncoded_options(q)

    def test_single_selection_keeps_uncoded_labels_and_order(self):
        r=fixture(); q=r['questionnaire_evidence'][0]
        q['uncoded_options']['selection']='single'
        q['display']['question_text']='过去两周睡眠情况频率如何？'
        q['options']=[{'value':f'option_{i}', 'original_code':None, 'label':label}
                      for i,label in enumerate(['None','Several days','At least a week','Nearly daily'],1)]
        q['display']['options']=[{'value':f'option_{i}', 'label':label}
                                 for i,label in enumerate(['完全没有','有几天','至少一周','几乎每天'],1)]
        text='### 2011 年\n问卷说明。\n\n#### Q001\n过去两周睡眠情况频率如何？\n- 完全没有\n- 有几天\n- 至少一周\n- 几乎每天\n'
        self.check_both(text,r,True)
        self.check_both(text.replace('- 有几天\n- 至少一周','- 至少一周\n- 有几天'),r,False)
        self.check_both(text.replace('- 完全没有','- 0 完全没有'),r,False)
        bad=copy.deepcopy(r);bad['questionnaire_evidence'][0]['options'][0]['original_code']='0'
        with self.assertRaises(ValueError): validate_uncoded_options(bad['questionnaire_evidence'][0])

    def test_source_gate_validates_even_omitted_questions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'source.txt').write_text('Source.',encoding='utf-8')
            old=source_checker.LOCAL_EVIDENCE_ROOTS.get('CHARLS')
            source_checker.LOCAL_EVIDENCE_ROOTS['CHARLS']=root
            try:
                r=fixture(); r['database']='CHARLS'; q=r['questionnaire_evidence'][0]
                q.update(local_material_path='source.txt', locator='page 3',
                         evidence_steps=[1], missing_reason='', supplemental_official_url='',
                         applicable_population='adult', recall_period='not applicable',
                         display_required=False, display_omission_reason='test omitted',
                         rendered_in_copy=False, copy_locator='不展示：test')
                r['questionnaire_coverage']=[{'source_group':'group','period':'2011',
                    'status':'questionnaire','evidence_ids':['q1'],'reason':'covered'}]
                args=(r,[{'step':1,'action':'official_material_review'}],{'group':{'2011'}})
                source_checker.validate_questionnaire_evidence(*args)
                q['uncoded_options']['selection']='single'
                source_checker.validate_questionnaire_evidence(*args)
                q['uncoded_options']=None
                with self.assertRaises(ValueError): source_checker.validate_questionnaire_evidence(*args)
            finally:
                if old is None: source_checker.LOCAL_EVIDENCE_ROOTS.pop('CHARLS',None)
                else: source_checker.LOCAL_EVIDENCE_ROOTS['CHARLS']=old

    def test_ordinary_codes_unchanged(self):
        item=fixture()['questionnaire_evidence'][0];item.pop('uncoded_options')
        self.assertEqual(original_option_comparison(item,[{'value':'01','label':'是'},
                         {'value':'2','label':'否'}]),['01 是','2 否'])


if __name__=='__main__': unittest.main()

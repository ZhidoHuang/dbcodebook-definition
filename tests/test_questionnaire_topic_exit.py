"""An evidenced topic exit can be abbreviated without losing the source route."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from test_questionnaire_display_answers import evidence, block as old_block, markup
from questionnaire_display import display_answers
from check_reader_copy import route_matches, read_questionnaire_copy, questionnaire_copy_errors
from check_definition_readability import validate_questionnaire_rendering


def block(period):
    return ('### 测试主题\n' + old_block(period).replace('#### DN014', '##### DN014')
            .replace('### '+period, '#### '+period).replace('问卷设计说明。', '##### 问卷设计\n问卷设计说明。'))


def exit_record(periods=('Wave 1',)):
    record = evidence(list(periods))
    item = record['questionnaire_evidence'][0]
    item['questionnaire_module'] = '测试主题'
    jump = item['display']['skip_logic'][0]
    jump.update(presentation='topic_exit', topic_exit_evidence=[
        {'period': period, 'destination': 'DN005', 'returns_to_topic': False,
         'evidence': '合成夹具：原路径转入另一模块且不返回本题组。'} for period in periods])
    return record


class TopicExitTests(unittest.TestCase):
    def check_both(self, text, record, good):
        original = copy.deepcopy(record)
        errors = questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(text)}, record)
        self.assertEqual(not errors, good, errors)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'definition_search_record.json').write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
            html = markup(text).replace('data-raw-source-period=', 'data-questionnaire-module="测试主题" data-raw-source-period=')
            (root/'note.md').write_text(html, encoding='utf-8')
            if good:
                validate_questionnaire_rendering(root, root, 'note.md')
            else:
                with self.assertRaises((ValueError, SystemExit)):
                    validate_questionnaire_rendering(root, root, 'note.md')
        self.assertEqual(record, original)

    def test_plain_and_existing_explicit_destination(self):
        record = exit_record()
        self.check_both(block('Wave 1').replace('转到 DN005', '结束该主题'), record, True)
        self.check_both(block('Wave 1'), record, True)
        self.check_both(block('Wave 1').replace('转到 DN005', '结束该主题（转到 DN005）'), record, True)
        self.check_both(block('Wave 1').replace('转到 DN005', '结束该主题（转到 DN006）'), record, False)
        self.check_both(block('Wave 1').replace('转到 DN005', '结束该主题后返回 DN014'), record, False)
        self.check_both(block('Wave 1').replace('转到 DN005', '结束该主题'), evidence(['Wave 1']), False)

    def test_missing_or_partial_exit_evidence(self):
        mutations = [
            lambda j: j.pop('topic_exit_evidence'),
            lambda j: j.update(topic_exit_evidence=[]),
            lambda j: j['topic_exit_evidence'][0].update(evidence=' '),
            lambda j: j['topic_exit_evidence'][0].update(returns_to_topic=True),
            lambda j: j['topic_exit_evidence'][0].update(returns_to_topic='false'),
            lambda j: j['topic_exit_evidence'][0].update(period='Wave 2'),
            lambda j: j['topic_exit_evidence'][0].update(destination='DN006'),
            lambda j: j.update(destination='结束该主题'),
            lambda j: j.update(destination='转到 DN006'),
            lambda j: j.update(when='1 是'),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                r = exit_record();item = r['questionnaire_evidence'][0]
                mutate(item['display']['skip_logic'][0])
                with self.assertRaises(ValueError): display_answers(item, r)

    def test_each_period_requires_its_own_finding(self):
        r = exit_record(('Wave 1', 'Wave 2'))
        text = block('Wave 1').replace('转到 DN005', '结束该主题') + '\n' + block('Wave 2').replace('### 测试主题\n','').replace('转到 DN005', '结束该主题')
        self.check_both(text, r, True)
        item = r['questionnaire_evidence'][0]
        for rows in [item['display']['skip_logic'][0]['topic_exit_evidence'][:1],
                     [item['display']['skip_logic'][0]['topic_exit_evidence'][0]] * 2]:
            bad = copy.deepcopy(r);q=bad['questionnaire_evidence'][0]
            q['display']['skip_logic'][0]['topic_exit_evidence'] = rows
            with self.assertRaises(ValueError): display_answers(q, bad)

    def test_internal_target_is_not_an_exit_even_if_omitted(self):
        r = exit_record();item = r['questionnaire_evidence'][0]
        target = copy.deepcopy(item)
        target.update(question_id='DN005_OtherCountry', display_required=False)
        r['questionnaire_evidence'].append(target)
        with self.assertRaisesRegex(ValueError, 'inside'): display_answers(item, r)
        target['periods'] = ['Wave 2']
        display_answers(item, r)  # A different-period question does not change this route.
        target['periods'] = ['Wave 1'];target['questionnaire_module'] = '另一主题'
        display_answers(item, r)

    def test_sequence_and_exit_are_distinct(self):
        r = exit_record();item = r['questionnaire_evidence'][0]
        item['display']['skip_logic'][0]['presentation'] = 'sequence'
        with self.assertRaises(ValueError): display_answers(item, r)

    def test_letter_and_full_identifier_destinations(self):
        for identifier in ['HESKE', 'DN005_OtherCountry', 'C.60']:
            r=exit_record();item=r['questionnaire_evidence'][0]
            item['skip_logic'][0]['destination']=identifier
            jump=item['display']['skip_logic'][0]
            jump['destination']='转到 '+identifier
            jump['topic_exit_evidence'][0]['destination']=identifier
            display_answers(item,r)
            jump['destination']='转到 WRONG'
            with self.assertRaises(ValueError):display_answers(item,r)

    def test_dotted_original_identifier_keeps_route_and_internal_checks(self):
        r=exit_record();item=r['questionnaire_evidence'][0]
        item['skip_logic'][0]['destination']='C.60'
        jump=item['display']['skip_logic'][0]
        jump['destination']='转到 C.60'
        jump['topic_exit_evidence'][0]['destination']='C.60'
        self.check_both(block('Wave 1').replace('转到 DN005','结束该主题'),r,True)
        wrong=copy.deepcopy(r);wrong['questionnaire_evidence'][0]['display']['skip_logic'][0]['destination']='转到 C.61'
        with self.assertRaises(ValueError):display_answers(wrong['questionnaire_evidence'][0],wrong)
        target=copy.deepcopy(item);target.update(question_id='C.60',display_required=False)
        r['questionnaire_evidence'].append(target)
        with self.assertRaisesRegex(ValueError,'inside'):display_answers(item,r)

    def test_abbreviation_is_exact_and_keeps_trigger_matching(self):
        self.assertTrue(route_matches('转到 DN005', '结束该主题。', allow_topic_exit=True))
        for text in ['不结束该主题', '结束该主题后继续', '结束', '结束该主题（转到 DN006）']:
            self.assertFalse(route_matches('转到 DN005', text, allow_topic_exit=True))
        text=block('Wave 1').replace('- 1 是', '- 1 是 → 结束该主题').replace(' → 转到 DN005','')
        self.check_both(text, exit_record(), False)


if __name__ == '__main__':
    unittest.main()

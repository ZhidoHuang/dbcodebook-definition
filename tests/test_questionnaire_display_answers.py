"""Focused copy/HTML tests for optional translation and period references."""
import copy
from html import escape
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from questionnaire_display import display_answers, cross_period_options
from check_reader_copy import read_questionnaire_copy, questionnaire_copy_errors, route_matches
from check_definition_readability import validate_questionnaire_rendering


def evidence(periods, qid='DN014', jump=True):
    return {'schema_version': 6, 'questionnaire_display_policy': 'chinese_v1',
            'questionnaire_evidence': [{
                'question_id': qid, 'question_text': 'Source question', 'periods': periods,
                'response_type': 'closed_options', 'rendered_in_copy': True, 'copy_locator': '文案问卷',
                'options': [{'value': '1', 'label': 'Yes'}, {'value': '5', 'label': 'No'}],
                'skip_logic': [{'when': '5 No', 'destination': 'DN005_OtherCountry'}] if jump else [],
                'routing_verbatim': 'IF DN004 = a5 THEN DN005_OtherCountry',
                'display': {'question_text': '请回答这个问题。', 'instructions': [],
                            'options': [{'value': '1', 'label': '是'}, {'value': '5', 'label': '否'}],
                            'skip_logic': [{'source_index': 0, 'when': '5 否', 'destination': '转到 DN005'}] if jump else []}}]}


def block(period, options=True, route=True, reference=''):
    text = f'### {period}\n问卷设计说明。\n\n#### DN014\n请回答这个问题。\n'
    if reference:
        text += reference + '\n'
    if options:
        text += '- 1 是\n- 5 否' + (' → 转到 DN005' if route else '') + '\n'
    elif route:
        text += '跳题说明：5 否 → 转到 DN005\n'
    return text


def markup(text):
    sections = []
    for key, group in read_questionnaire_copy(text).items():
        body = []
        for q in group['questions']:
            details = []
            for option in q['options']:
                details.append('<div data-summary-question-detail="true"><span data-summary-question-option="true">'
                               + escape(option['text']) + '</span>'
                               + ('<span data-summary-question-instruction="true">' + escape(option['jump']) + '</span>' if option['jump'] else '') + '</div>')
            details.extend('<span data-summary-question-instruction="true">' + escape(i) + '</span>' for i in q['instructions'])
            body.append('<div data-summary-questionnaire-line="true"><b data-summary-question-id="true">'
                        + escape(q['id']) + '</b>' + escape(q['text']) + ''.join(details) + '</div>')
        sections.append('<section data-raw-source-period="' + key + '" data-label="' + escape(group['label']) + '">'
                        '<div data-summary-period-note="true"><b data-summary-period-note-title="true">问卷设计</b>'
                        + escape(group['design']) + '</div>' + ''.join(body) + '</section>')
    return ''.join(sections)


class DisplayAnswersTests(unittest.TestCase):
    def test_explicit_omission_keeps_evidence(self):
        record = evidence(['Wave 1'])
        record['questionnaire_evidence'][0].update(display_required=False,
            display_omission_reason='官方分类直接保留，定义逻辑已说明含义。',
            rendered_in_copy=False, copy_locator='不展示：官方分类直接保留')
        self.check_both('', record, True)
        # A missing required question must still fail in a mixed topic.
        record['questionnaire_evidence'].append(evidence(['Wave 2'])['questionnaire_evidence'][0])
        self.check_both('', record, False)
        self.check_both(block('Wave 2'), record, True)

    def test_omission_requires_reason_and_honest_display_state(self):
        from questionnaire_display import requires_questionnaire_display
        for item in [dict(display_required='false'), dict(display_required=False),
                     dict(display_required=False, display_omission_reason=' ', rendered_in_copy=False),
                     dict(display_required=False, display_omission_reason='采用官方结果', rendered_in_copy=True)]:
            with self.assertRaises(ValueError):
                requires_questionnaire_display(item)
        self.check_both('', evidence(['Wave 1']), False)

    def check_both(self, text, record, good):
        original = copy.deepcopy(record)
        errors = questionnaire_copy_errors({'questionnaire': read_questionnaire_copy(text) if text else {}}, record)
        self.assertEqual(not errors, good, errors)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'definition_search_record.json').write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
            (path/'note.md').write_text(markup(text) if text else '## 定义\n', encoding='utf-8')
            if good:
                validate_questionnaire_rendering(path, path, 'note.md')
            else:
                with self.assertRaises((ValueError, SystemExit)):
                    validate_questionnaire_rendering(path, path, 'note.md')
        self.assertEqual(record, original)

    def test_translated_and_preserved(self):
        self.check_both(block('Wave 1'), evidence(['Wave 1']), True)

    def test_bad_registered_answers(self):
        mutations = [
            lambda d: d['options'].pop(),
            lambda d: d['options'][1].update(value='0'),
            lambda d: d['options'].reverse(),
            lambda d: d['options'][0].update(label='Yes'),
            lambda d: d.update(skip_logic=[]),
            lambda d: d['skip_logic'][0].update(source_index=1),
            lambda d: d['skip_logic'][0].update(source_index=True),
            lambda d: d['skip_logic'][0].update(destination='转到 DN006'),
            lambda d: d['skip_logic'][0].update(destination='转到 DN0050'),
            lambda d: d['skip_logic'][0].update(when='1 是'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                r = evidence(['Wave 1'])
                mutate(r['questionnaire_evidence'][0]['display'])
                self.check_both(block('Wave 1'), r, False)

    def test_missing_rendered_option_or_route(self):
        r = evidence(['Wave 1'])
        self.check_both(block('Wave 1').replace('- 1 是\n', ''), r, False)
        self.check_both(block('Wave 1', route=False), r, False)
        self.check_both(block('Wave 1').replace('DN005', 'DN006'), r, False)

    def test_optional_fields_legacy(self):
        r = evidence(['Wave 1'])
        r['questionnaire_evidence'][0]['display'].pop('options')
        r['questionnaire_evidence'][0]['display'].pop('skip_logic')
        self.check_both(block('Wave 1').replace('1 是','1 Yes').replace('5 否','5 No').replace('转到 DN005','DN005_OtherCountry'), r, True)
        r.pop('questionnaire_display_policy')
        r['questionnaire_evidence'][0].pop('display')
        self.check_both(block('Wave 1').replace('请回答这个问题。','Source question').replace('1 是','1 Yes').replace('5 否','5 No').replace('转到 DN005','DN005_OtherCountry'), r, True)

    def test_cross_period_same_question(self):
        ref = 'DN014 的两个选项与 Wave 1、Wave 2、Wave 4–5 的 DN014 相同。'
        text = block('Wave 1', route=False) + block('Wave 2', route=False) + block('Wave 4–5', route=False) + block('Wave 6', options=False, route=False, reference=ref)
        r = evidence(['Wave 1','Wave 2','Wave 4','Wave 5','Wave 6'], jump=False)
        self.check_both(text, r, True)
        self.check_both(text.replace('### Wave 2\n问卷设计说明。\n\n#### DN014\n请回答这个问题。\n- 1 是\n- 5 否',
                                     '### Wave 2\n问卷设计说明。\n\n#### DN014\n请回答这个问题。\n- 1 是\n- 5 未确定'), r, False)
        self.check_both(text.replace('Wave 1、Wave 2、Wave 4–5 的', 'Wave 1、Wave 3、Wave 4–5 的'), r, False)
        self.check_both(text.replace(ref, ref + '\n- 1 是\n- 5 否'), r, False)

    def test_cross_period_does_not_inherit_routes(self):
        ref = 'DN014 的两个选项与 Wave 1 的 DN014 相同。'
        r = evidence(['Wave 1','Wave 2'])
        text = block('Wave 1') + block('Wave 2', options=False, route=False, reference=ref)
        self.check_both(text, r, False)
        text = block('Wave 1') + block('Wave 2', options=False, route=True, reference=ref)
        self.check_both(text, r, True)

    def test_duplicate_source_index(self):
        r = evidence(['Wave 1'])
        item = r['questionnaire_evidence'][0]
        item['skip_logic'].append(copy.deepcopy(item['skip_logic'][0]))
        item['display']['skip_logic'].append(copy.deepcopy(item['display']['skip_logic'][0]))
        with self.assertRaisesRegex(ValueError, 'source_index'):
            display_answers(item, r)

    def test_six_options_and_ambiguous_period(self):
        options = [f'{i} 类别{ i }' for i in range(1, 7)]
        ref = 'DN014 的六个选项与 Wave 1、Wave 2、Wave 4–5 的 DN014 相同。'
        periods = [(wave, [('DN014', options)], '') for wave in ['Wave 1','Wave 2','Wave 4–5','Wave 6']]
        self.assertEqual(cross_period_options(ref, 'Wave 6', 'DN014', periods), options)
        ambiguous = periods[:2] + [('Wave 1–2', [('DN014', options)], '')] + periods[2:]
        with self.assertRaisesRegex(ValueError, 'one earlier period'):
            cross_period_options(ref, 'Wave 6', 'DN014', ambiguous)
        with self.assertRaisesRegex(ValueError, 'same question'):
            cross_period_options(ref.replace('的 DN014 相同', '的 DN015 相同'), 'Wave 6', 'DN014', periods)

    def test_share_long_id_and_other_module_same_wave(self):
        ref = 'DN014 的两个选项与 Wave 1、Wave 2、Wave 4–5 的 DN014 相同。'
        text = block('Wave 1', route=False) + block('Wave 2', route=False) + block('Wave 4–5', route=False) + block('Wave 6', options=False, route=False, reference=ref)
        text = text.replace('#### DN014\n', '#### DN014_MaritalStatus\n')
        r = evidence(['Wave 1','Wave 2','Wave 4','Wave 5','Wave 6'], qid='DN014_MaritalStatus', jump=False)
        self.check_both(text, r, True)
        options = ['1 是','5 否']
        periods = [('Wave 1；出生', [('DN004_CountryOfBirth', options)], ''),
                   ('Wave 1；婚姻', [('DN014_MaritalStatus', options)], ''),
                   ('Wave 2', [('DN014_MaritalStatus', options)], ''),
                   ('Wave 4–5', [('DN014_MaritalStatus', options)], ''),
                   ('Wave 6', [('DN014_MaritalStatus', [])], '')]
        self.assertEqual(cross_period_options(ref, 'Wave 6', 'DN014_MaritalStatus', periods), options)
        with self.assertRaisesRegex(ValueError, 'same question'):
            cross_period_options(ref.replace('的 DN014 相同','的 DN0140 相同'), 'Wave 6', 'DN014_MaritalStatus', periods)

    def test_trigger_question_and_program_flag_ids(self):
        r = evidence(['Wave 1'])
        item = r['questionnaire_evidence'][0]
        item['skip_logic'][0]['when'] = 'DN004_CountryOfBirth = a5 AND MN101_Longitudinal = 0'
        item['display']['skip_logic'][0]['when'] = 'DN004=5 且 MN101=0（非访谈国出生的基线受访者）'
        self.assertEqual(display_answers(item, r)[1][0]['source_index'], 0)
        for bad in ['DN007=5 且 MN101=0（非访谈国出生）',
                    'DN004=5 且 MN102=0（基线受访者）',
                    'DN004=5 且 0（基线受访者）']:
            with self.subTest(bad=bad):
                item['display']['skip_logic'][0]['when'] = bad
                with self.assertRaisesRegex(ValueError, 'trigger question/flag id'):
                    display_answers(item, r)

    def test_own_question_id_may_be_omitted(self):
        r = evidence(['Wave 1'], qid='DN004_CountryOfBirth')
        item = r['questionnaire_evidence'][0]
        item['skip_logic'][0]['when'] = 'DN004_CountryOfBirth=a5'
        item['display']['skip_logic'][0]['when'] = '5 否'
        display_answers(item, r)
        item['display']['skip_logic'][0]['when'] = 'DN007=5 否'
        with self.assertRaisesRegex(ValueError, 'trigger question/flag id'):
            display_answers(item, r)

    def test_same_period_short_alias_options(self):
        r = evidence(['Wave 1'], qid='DN004_CountryOfBirth', jump=False)
        other = copy.deepcopy(r['questionnaire_evidence'][0])
        other['question_id'] = 'DN007_Citizenship'
        r['questionnaire_evidence'].append(other)
        text = ('### Wave 1\n问卷设计说明。\n\n#### DN004_CountryOfBirth\n请回答这个问题。\n'
                '- 1 是\n- 5 否\nDN007 的选项与 DN004 相同。\n\n'
                '#### DN007_Citizenship\n请回答这个问题。\n')
        self.check_both(text, r, True)
        # Full-name declarations remain valid alongside short references.
        self.check_both(text.replace('DN007 的选项与 DN004 相同。',
                                    'DN007_Citizenship 的选项与 DN004_CountryOfBirth 相同。'), r, True)
        with self.assertRaises(ValueError):
            read_questionnaire_copy(text.replace('DN004 相同','DN0040 相同'))

    def test_same_wave_different_chinese_modules(self):
        ref = 'DN014 的两个选项与 Wave 1 的 DN014 相同。'
        text = block('Wave 1：出生模块', route=False).replace('#### DN014\n','#### DN004_CountryOfBirth\n')
        text += block('Wave 1：婚姻模块', route=False).replace('#### DN014\n','#### DN014_MaritalStatus\n')
        text += block('Wave 2：婚姻模块', options=False, route=False, reference=ref).replace('#### DN014\n','#### DN014_MaritalStatus\n')
        r = evidence(['Wave 1','Wave 2'], qid='DN014_MaritalStatus', jump=False)
        self.check_both(text, r, True)

    def test_destination_chinese_adjacency(self):
        r = evidence(['Wave 1'])
        item = r['questionnaire_evidence'][0]
        item['skip_logic'][0]['destination'] = '跳过DN005和DN006，至DN007'
        item['display']['skip_logic'][0]['destination'] = '跳过 DN005 和 DN006，转到 DN007'
        display_answers(item, r)
        item['display']['skip_logic'][0]['destination'] = '跳过 DN005 和 DN0060，转到 DN007'
        with self.assertRaisesRegex(ValueError, 'destination question id'):
            display_answers(item, r)

    def test_compound_when_requires_all_local_fragments(self):
        r = evidence(['Wave 1'])
        item = r['questionnaire_evidence'][0]
        item['skip_logic'][0]['when'] = 'DN014=a5 AND MN101=0'
        item['display']['skip_logic'][0]['when'] = '5 “否”，且 MN101=0'
        text = block('Wave 1').replace('→ 转到 DN005', '→ MN101=0，转到 DN005')
        self.check_both(text, r, True)
        self.check_both(text.replace('MN101=0', 'MN101=1'), r, False)
        self.check_both(text.replace('MN101=0，', ''), r, False)
        # A condition elsewhere on the page must not satisfy this question.
        other = text.replace('MN101=0，', '') + '\n#### DN099\n另一题。\n跳题说明：MN101=0，转到 DN005\n'
        self.check_both(other, r, False)
        paragraph = block('Wave 1', route=False) + '\n跳题说明：当“5 否”时，MN101=0，转到 DN005。\n'
        self.check_both(paragraph, r, True)
        separated = block('Wave 1', route=False) + '\n跳题说明：5 否，转到 DN005。\n跳题说明：MN101=0。\n'
        self.check_both(separated, r, False)

    def test_destination_period_and_flags_are_not_question_targets(self):
        r = evidence(['Wave 1'])
        item = r['questionnaire_evidence'][0]
        item['skip_logic'][0]['destination'] = 'DN503（W5起）；否则跳过DN008'
        item['display']['skip_logic'][0]['destination'] = 'Wave 5 起转到 DN503；其他时期跳过 DN008'
        display_answers(item, r)
        item['skip_logic'][0]['destination'] = 'W6起MN005=a1时进入DN040'
        item['display']['skip_logic'][0]['destination'] = '本期转到 DN040'
        display_answers(item, r)  # Question IDs are checked; translation is human-reviewed.

    def test_route_markdown_and_spaces_preserve_id_boundaries(self):
        self.assertTrue(route_matches('转到 DN005', '转到 `DN005`'))
        self.assertTrue(route_matches('MN005_ModeQues=1 时进入 DN040', '`MN005_ModeQues` = `1` 时进入 **DN040**'))
        self.assertTrue(route_matches('DN005', 'go to `DN005`'))
        self.assertFalse(route_matches('DN005', 'go to `DN0050`'))
        self.assertFalse(route_matches('DN005', 'go to `XDN005`'))
        self.assertFalse(route_matches('转到 DN005', '转到 `DN006`'))


if __name__ == '__main__':
    unittest.main()

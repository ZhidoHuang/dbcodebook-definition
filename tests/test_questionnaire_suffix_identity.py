"""Distinct suffix questions coexist; only unambiguous short references alias."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_reader_copy import read_questionnaire_copy
from questionnaire_display import referenced_options, shared_question_info, referenced_jump_options


class SuffixIdentityTests(unittest.TestCase):
    def test_distinct_smoking_questions_in_same_period(self):
        text = ('### 吸烟\n#### 2020 年\n##### 问卷设计\n按当前或戒烟前分别询问。\n'
                '##### DA050_1\n现在每天吸多少支？\n'
                '##### DA050_2\n戒烟前每天吸多少支？\n')
        period = next(iter(read_questionnaire_copy(text).values()))
        self.assertEqual([q['id'] for q in period['questions']], ['DA050_1', 'DA050_2'])

    def test_full_suffix_reference_preserves_distinct_options(self):
        entries = [('DA061', ['1 当前', '2 戒烟'], ''),
                   ('DA061_W3', ['1 过去', '2 戒烟', '3 从未'],
                    'DA061_W4 的选项与 DA061_W3 相同。'), ('DA061_W4', [], '')]
        self.assertEqual(referenced_options('', 'DA061_W4', entries), entries[1][1])
        self.assertEqual(referenced_options('', 'DA061', entries), [])
        self.assertEqual(referenced_jump_options('DA061_W4', entries), [])

    def test_unique_short_reference_survives_other_collisions(self):
        entries = [('DA050_1', [], ''), ('DA050_2', [], ''),
                   ('DN004_CountryOfBirth', ['1 是', '5 否'],
                    'DN007 的选项与 DN004 相同。'), ('DN007_Citizenship', [], '')]
        self.assertEqual(referenced_options('', 'DN007_Citizenship', entries), ['1 是', '5 否'])
        design = '共同选项（DA050_1）：1=当前；2=不吸烟。'
        self.assertEqual(shared_question_info(design, 'DA050_1', ['DA050_1', 'DA050_2'])[0],
                         ['1 当前', '2 不吸烟'])
        self.assertEqual(shared_question_info(design, 'DA050_2', ['DA050_1', 'DA050_2'])[0], [])

    def test_duplicate_full_id_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate questionnaire question ids'):
            referenced_options('', 'DA050_1', [('DA050_1', [], ''), ('DA050_1', [], '')])


if __name__ == '__main__':
    unittest.main()

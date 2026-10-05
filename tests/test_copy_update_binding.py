"""Presentation changes must reuse evidence; business changes must invalidate it."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import execution_report as er
import update_reader_copy as update
from exploration_handoff import plan_hash
from source_record_binding import SOURCE_SCOPE


def rejects(fn):
    try:
        fn()
    except (ValueError, SystemExit):
        return
    raise AssertionError('Expected rejection')


with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    source = p / 'definition_search_record.json'
    original = {'definition_plan': {'formula': 'x + y', 'missing': 'all valid'},
                'source_groups': [{'raw_variables': ['x', 'y']}],
                'questionnaire_evidence': [{'question_id': 'Q1', 'question_text': 'Official question',
                    'question_variable': 'x', 'skip_logic': '1 -> Q3', 'display_required': True,
                    'display': {'question_text': '译文'}}],
                'questionnaire_path_closure': [{'observed_count': 10}]}
    update.write(source, original)
    baseline = er.input_hashes([source], source_scope=SOURCE_SCOPE)
    legacy = er.input_hashes([source])
    plan = plan_hash(source, 2)
    changed = deepcopy(original)
    changed['questionnaire_evidence'][0].update(display_required=False,
        display_omission_reason='用户要求省略', copy_locator='不展示', rendered_in_copy=False,
        display={'question_text': '另一种译文'})
    update.write(source, changed)
    assert er.input_hashes([source], source_scope=SOURCE_SCOPE) == baseline
    assert er.input_hashes([source]) != legacy  # Legacy bindings are not silently weakened.
    assert plan_hash(source, 2) == plan
    for field, value in [('question_text', 'Different official question'),
                         ('question_variable', 'z'), ('skip_logic', '1 -> Q4')]:
        bad = deepcopy(changed); bad['questionnaire_evidence'][0][field] = value
        update.write(source, bad)
        assert er.input_hashes([source], source_scope=SOURCE_SCOPE) != baseline
        assert plan_hash(source, 2) != plan
    for key, value in [('formula', 'x - y'), ('missing', 'any valid')]:
        bad = deepcopy(changed); bad['definition_plan'][key] = value
        update.write(source, bad)
        assert er.input_hashes([source], source_scope=SOURCE_SCOPE) != baseline
        assert plan_hash(source, 2) != plan
    bad = deepcopy(changed); bad['questionnaire_path_closure'][0]['observed_count'] = 11
    update.write(source, bad)
    assert er.input_hashes([source], source_scope=SOURCE_SCOPE) != baseline

    # Production pre-generation guard: edits to copy are allowed, raw/R are not.
    formal = p / 'formal'; formal.mkdir()
    backup = p / 'backup'; backup.mkdir()
    update.write(source, original); update.write(backup / source.name, original)
    for name in ['文案.md', 'define.R', 'raw_data.csv']:
        (formal / name).write_text('original', encoding='utf-8')
    (backup / '文案.md').write_bytes((formal / '文案.md').read_bytes())
    binding = {'folder': str(backup), 'source_hash': update.digest(backup / source.name),
               'result': {'artifacts': {f.name: update.digest(f) for f in formal.iterdir()}},
               'review': {'inputs': er.input_hashes([source, formal / 'define.R'], source_scope=SOURCE_SCOPE),
                          'source_scope': SOURCE_SCOPE}}
    (formal / '文案.md').write_text('new wording', encoding='utf-8')
    update.write(source, changed)
    update.check_unchanged(formal, p, binding)
    for name in ['define.R', 'raw_data.csv']:
        (formal / name).write_text('changed', encoding='utf-8')
        rejects(lambda: update.check_unchanged(formal, p, binding))
        (formal / name).write_text('original', encoding='utf-8')
    update.write(source, bad)
    rejects(lambda: update.check_unchanged(formal, p, binding))

    # Real import command logic, synthetic log record with one historical turn.
    report = {'status': 'running', 'started_at': '2026-01-02T00:00:00+00:00'}
    turns = [dict(turn_id=k, started_at=start, finished_at=end, elapsed_seconds=10,
                  gap_before_seconds=999, outcome='completed') for k,start,end in [
        ('old', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:10+00:00'),
        ('new', '2026-01-02T00:00:00+00:00', '2026-01-02T00:00:10+00:00')]]
    log = {'agent_id': 'fixture', 'created_at': '2026-01-01T00:00:00+00:00',
           'rounds': turns, 'unfinished_turns': 0}
    args = SimpleNamespace(process_dir=p, log=p/'fixture.jsonl', role='review',
                           closed=False, close_unavailable='test host', turn_id=None)
    with patch.object(er, 'load', return_value=report), patch.object(er, 'save'), \
         patch.object(er, 'read_review_log', side_effect=lambda *a: deepcopy(log)):
        result = er.command_review_import(args)
        assert result['turn_count'] == 1 and result['running_seconds'] == 10
        assert result['between_rounds_seconds'] == 0
        args.turn_id = ['old']; rejects(lambda: er.command_review_import(args))
        args.turn_id = ['new', 'new']; rejects(lambda: er.command_review_import(args))

print('COPY_UPDATE_BINDING_PASS: display reuse, legacy isolation, business/data guards, scoped timing')

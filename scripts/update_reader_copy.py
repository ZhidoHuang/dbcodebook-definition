#!/usr/bin/env python3
"""Prepare before editing; rebuild a copy-only change without new research/review.

No browser access, downloads, or publishing. Existing runner/checkers remain the
production path. A changed research input or calculation fails before generation.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import zipfile

import execution_report as er
from exploration_handoff import validate_exploration
from source_record_binding import research_record, SOURCE_SCOPE
from hrs_export_contract import record_defaults

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def call(script, *args, log=None):
    result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / script),
                             *map(str, args)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if log:
        Path(log).write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise ValueError(result.stderr or result.stdout)
    return result


def reports(process):
    yield process / er.REPORT_NAME
    yield from sorted(process.glob("archived_runs/*/execution_report.json"),
                      key=lambda x: x.stat().st_mtime, reverse=True)


def same_topic(previous, current):
    return (str(previous.get('database', '')).lower() == str(current.get('database', '')).lower()
            and previous.get('topic_id') == current.get('topic_id'))


def find_review(process, required, relocation=None):
    for path in reports(process):
        report = read(path)
        if er.COMBINED_REVIEW_ROLE in report.get("stage_reviews", {}):
            # A newer pending/failed/stale review must never fall back to an old pass.
            if relocation:
                report = relocation.report(path, roles=(er.COMBINED_REVIEW_ROLE,))
                current = read(process / er.REPORT_NAME)
                if not same_topic(report, current):
                    raise ValueError("迁移的 R 复核报告与当前主题不同")
            review = deepcopy(er.validate_stage_review(report, er.COMBINED_REVIEW_ROLE, required))
            agent = review.get("prior_agent_record") or next(
                a for a in report.get("reviews", []) if a["agent_id"] == review["agent_id"])
            review.update(prior_agent_record=agent, reused_from=str(path))
            return review
    raise ValueError("没有可沿用的独立 R 复核")


def inherit_relocated_exploration(report, previous, original_snapshot, source):
    """Keep verified relocated exploration usable on the next copy-only update."""
    from exploration_handoff import POLICY, ROLES
    report['exploration_policy'] = POLICY
    report['primary_agent_id'] = os.environ.get('CODEX_THREAD_ID', '')
    exploration = deepcopy(previous['exploration'])
    exploration.update(from_report=original_snapshot['snapshot'],
                       from_report_hash=original_snapshot['sha256'], reused_at=er.iso())
    report['exploration'] = exploration
    for role in ROLES.values():
        prior = deepcopy(previous['stage_reviews'][role])
        agent = prior.get('prior_agent_record') or next(
            item for item in previous.get('reviews', []) if item['agent_id'] == prior['agent_id'])
        prior.update(prior_agent_record=deepcopy(agent), reused_from=original_snapshot['snapshot'])
        report.setdefault('stage_reviews', {})[role] = prior
    validate_exploration(report, source)


def prepare(args):
    formal, process = args.formal_dir.resolve(), args.process_dir.resolve()
    current = read(process / er.REPORT_NAME)
    if current["status"] == "running":
        raise ValueError("先结束当前任务；不能覆盖执行中的报告")
    result = read(process / "result_check.json")
    if not result.get("ok") or result.get("scope") != "complete":
        raise ValueError("须有修改前的完整成果检查报告")
    for name, sha in result["artifacts"].items():
        if Path(name).name != name or digest(formal / name) != sha:
            raise ValueError("修改前成果已变化；不能事后补基线：" + name)
    source = process / "definition_search_record.json"
    if digest(source) != result["source_sha256"]:
        raise ValueError("来源记录已变化；请先解决原有变化")
    relocation = None
    if getattr(args, 'path_map', None):
        from report_relocation import ReportRelocation
        relocation = ReportRelocation(args.path_map, formal, process)
    legacy_used = False
    relocated_exploration = None
    for path in reports(process):
        prior = read(path)
        if prior.get("exploration_policy"):
            if relocation:
                prior = relocation.report(path, exploration=True)
                if not same_topic(prior, current):
                    raise ValueError("迁移的探索报告与当前主题不同")
            validate_exploration(prior, source)
            if relocation:
                relocated_exploration = (str(path.resolve()), prior)
            break
    else:
        legacy_path = getattr(args, 'legacy_report', None)
        if legacy_path is None:
            raise ValueError("未找到双路探索登记；旧主题核对既有方案和证据后，可用 --legacy-report 指定已完成的历史 R 复核报告；实质证据缺口或未决研究问题须先解决")
        legacy = read(legacy_path)
        if (legacy.get('exploration_policy') or
                legacy.get('status') not in ('completed', 'completed_with_issues') or
                str(legacy.get('database', '')).lower() != str(current.get('database', '')).lower() or
                legacy.get('topic_id') != current.get('topic_id') or
                er.COMBINED_REVIEW_ROLE not in legacy.get('stage_reviews', {})):
            raise ValueError("指定的历史报告与当前主题或已完成R复核不符")
        legacy_used = True
        # Explicit historical evidence does not replace the current R/source
        # verification below or any existing dual-exploration registration.
    rfiles = [n for n in result["artifacts"] if n.lower().endswith('.r')]
    if len(rfiles) != 1:
        raise ValueError("须有唯一正式 R")
    review = find_review(process, [formal / rfiles[0], source, formal / 'raw_codebook.csv'], relocation)
    audit = read(process / 'readability_audit.json')
    if audit.get('unresolved_issues') or any(i.get('status') == 'open' for i in current.get('issues', [])):
        raise ValueError("现有问题尚未解决，不能作为纯文案更新")
    folder = process / 'copy_updates' / str(uuid.uuid4())
    folder.mkdir(parents=True)
    for name in result['artifacts']:
        if name.endswith('.xlsx') or name in ('文案.md', audit['artifacts'].get('note', {}).get('path')):
            shutil.copy2(formal / name, folder / name)
    write(folder / 'result_check.json', result)
    for name in ('reader_comprehension_review.json', 'ordinary_reader_input.md'):
        if (process / name).is_file():
            shutil.copy2(process / name, folder / name)
    shutil.copy2(source, folder / source.name)
    shutil.copy2(process / 'definition_change_impact.json', folder / 'definition_change_impact.json')
    relocation_evidence = relocation.save_evidence(folder / 'relocation') if relocation else None
    # Validate legacy bindings while originals still exist, then record explicit
    # migration to the new comparison. This is reuse, not a new reviewer verdict.
    review.update(source_scope=SOURCE_SCOPE,
                  inputs=er.input_hashes(review['inputs'], review.get('r_scope', 'full'), SOURCE_SCOPE))
    call('execution_report.py', 'init', '--process-dir', process, '--database', current['database'],
         '--topic-id', current['topic_id'], '--topic-name', current['topic_name'],
         '--task', args.reason, '--workflow', 'general')
    if review['reused_from'] == str(process / er.REPORT_NAME):
        review['reused_from'] = str(process / 'archived_runs' / current['run_id'] / er.REPORT_NAME)
    report = read(process / er.REPORT_NAME)
    binding = {'formal_dir': str(formal), 'folder': str(folder), 'reason': args.reason,
               'source_hash': digest(folder / source.name), 'result': result,
               'r_script': rfiles[0], 'audit_artifacts': audit['artifacts'],
               'review': review, 'status': 'prepared', 'issue_numbers': [], 'attempts': []}
    if relocation_evidence:
        binding['relocation'] = relocation_evidence
    if legacy_used:
        legacy_path = args.legacy_report.resolve()
        if legacy_path == (process / er.REPORT_NAME).resolve():
            legacy_path = process / 'archived_runs' / current['run_id'] / er.REPORT_NAME
        binding['legacy_evidence'] = {'path': str(legacy_path), 'sha256': digest(legacy_path)}
    report['copy_update'] = binding
    report['stage_reviews'] = {er.COMBINED_REVIEW_ROLE: review}
    if relocated_exploration:
        original_path, previous = relocated_exploration
        snapshot = next(item for item in relocation_evidence['reports']
                        if item['original_path'] == original_path)
        inherit_relocated_exploration(report, previous, snapshot, source)
    er.save(*er.paths(process), report)
    call('execution_report.py', 'stage-start', '--process-dir', process, '--stage-id', 'copy',
         '--name', '局部文案修改', '--role', '主执行')
    return {'ok': True, 'status': 'PREPARED', 'next': '修改文案后运行 run；改变研究或计算则返回相应环节。'}


def check_unchanged(formal, process, binding):
    folder = Path(binding['folder'])
    if digest(folder / 'definition_search_record.json') != binding['source_hash']:
        raise ValueError('修改前来源副本已变化')
    if research_record(read(folder / 'definition_search_record.json')) != research_record(read(process / 'definition_search_record.json')):
        raise ValueError('研究内容已变化，不能按纯文案更新')
    for name, sha in binding['result']['artifacts'].items():
        current = digest(formal / name) if (formal / name).is_file() else None
        immutable = name.startswith('raw_') or name.lower().endswith(('.r', '.zip'))
        expected = sha if immutable else binding.get('recovery_artifacts', {}).get(name, sha)
        if name != '文案.md' and current != expected:
            raise ValueError('文案以外成果已变化：' + name)
        if (name.endswith('.xlsx') or name == '文案.md') and digest(folder / name) != sha:
            raise ValueError('修改前成果副本已变化：' + name)
    review = binding['review']
    if er.input_hashes(review['inputs'], review.get('r_scope', 'full'), SOURCE_SCOPE) != review['inputs']:
        raise ValueError('研究或计算复核输入已变化')


def workbook_content(path):
    with zipfile.ZipFile(path) as archive:
        return {name: hashlib.sha256(archive.read(name)).hexdigest()
                for name in archive.namelist() if name != 'docProps/core.xml'}


def previous_raw_order(result, planned):
    # A copy-only update keeps the accepted download order, even when source
    # groups are organized by meaning rather than CSV position.
    previous = next((item.get('detail') for item in result.get('checks', [])
                     if item.get('check') == 'raw_codebook vars' and item.get('ok')), None)
    if previous is None:
        return planned
    if (not isinstance(previous, list) or len(previous) != len(set(previous))
            or set(previous) != set(planned)):
        raise ValueError('原始变量清单与修改前已验证清单不同')
    return previous


TEXT_SECTIONS = ('摘要导读', '小book提示', '参考资料说明')
TEXT_FIELDS = ('summary', 'summary_blocks', 'insight', 'references')


def outside_text_sections(text):
    pattern = r'(?ms)^## (' + '|'.join(TEXT_SECTIONS) + r')\s*\n.*?(?=^## |\Z)'
    return re.sub(pattern, lambda m: '## ' + m[1] + '\n', text)


def text_update_changes(before, after, source, variables):
    """Return supported display changes, never infer that a formula edit is prose."""
    from check_reader_copy import read_copy
    if outside_text_sections(before.read_text(encoding='utf-8-sig')) != outside_text_sections(after.read_text(encoding='utf-8-sig')):
        return None
    old, new = (read_copy(path, variables, source) for path in (before, after))
    if {k:v for k,v in old.items() if k not in TEXT_FIELDS} != {k:v for k,v in new.items() if k not in TEXT_FIELDS}:
        return None
    return [key for key in ('summary', 'insight', 'references') if old[key] != new[key]]


def apply_fragment_patches(note, patches):
    spans = []
    for patch in patches:
        before = patch['before']
        if not before or note.count(before) != 1:
            raise ValueError('旧笔记不能唯一匹配当前生成器的栏目：' + patch['field'])
        start = note.index(before)
        spans.append((start, start + len(before), patch['after']))
    spans.sort()
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError('文案栏目替换范围重叠')
    for start, end, replacement in reversed(spans):
        note = note[:start] + replacement + note[end:]
    return note


def complete_result(record):
    return (record.get('ok') is True and record.get('scope') == 'complete'
            and record.get('status') == 'MACHINE_CHECK_PASS' and record.get('checks')
            and all(item.get('ok') is True for item in record['checks'])
            and record.get('checker_sha256') == digest(ROOT/'scripts/check_definition_output.py'))


def original_result(record, process):
    seen = set()
    while record.get('copy_sections'):
        receipt = record['copy_sections']
        path = (process/receipt['baseline']).resolve()
        path.relative_to(process.resolve())
        if path in seen or digest(path) != receipt['baseline_sha256']:
            raise ValueError('完整检查基线链无效')
        seen.add(path)
        record = read(path)
    return record


def text_tool_hashes():
    return {name: digest(ROOT/'scripts'/name) for name in (
        'update_reader_copy.py', 'render_definition_bundle.R', 'summary_fact_helpers.R',
        'check_reader_copy.py', 'reference_format.py')}


def previous_check_options(baseline):
    options = {'forbidden formal content': '--forbid-vars',
               'required user text': '--required-user-text',
               'Criteria evolution structure': '--criteria-evolution-text'}
    args = []
    for item in baseline['checks']:
        if item['check'] not in options:
            continue
        values = item.get('detail')
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            raise ValueError('旧检查缺少可复用的约束：' + item['check'])
        args += [options[item['check']], ','.join(values)]
    return args


def text_constraints(baseline, copy_text, note_text):
    from check_definition_output import visible_text
    checks = [{'check':'summary prose indentation', 'ok':'&emsp;' not in copy_text + note_text}]
    for item in baseline['checks']:
        if item['check'] not in ('forbidden formal content', 'required user text'):
            continue
        values = item.get('detail')
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            raise ValueError('旧文本检查缺少可复用的约束：' + item['check'])
        passed = (all(x not in copy_text + note_text for x in values)
                  if item['check'] == 'forbidden formal content'
                  else all(x in visible_text(note_text) for x in values))
        checks.append({'check':item['check'], 'ok':passed, 'detail':values})
    if not all(item['ok'] for item in checks):
        raise ValueError('修改后的文本不满足原检查条件：' + json.dumps(checks, ensure_ascii=False))
    return checks


def validate_text_result(record, formal, process, note_path=None, copy_path=None, seen=None):
    """Verify inherited checks against retained evidence, not a relabelled old PASS."""
    if not complete_result(record):
        raise ValueError('局部更新缺少有效完整检查基线')
    receipt = record.get('copy_sections')
    if receipt is None:
        if record.get('validation_mode') == 'copy_sections':
            raise ValueError('局部更新缺少继承证据')
        return
    if record.get('validation_mode') != 'copy_sections' or not isinstance(receipt, dict):
        raise ValueError('局部更新证据与检查模式不一致')
    if receipt.get('tools') != text_tool_hashes():
        raise ValueError('局部更新检查或生成器已变化，需重新核对受影响成果')
    baseline_path = (process/receipt['baseline']).resolve()
    baseline_path.relative_to(process.resolve())
    seen = set() if seen is None else seen
    if baseline_path in seen:
        raise ValueError('局部更新证据循环引用')
    seen.add(baseline_path)
    if digest(baseline_path) != receipt['baseline_sha256']:
        raise ValueError('局部更新检查基线已变化')
    baseline = read(baseline_path)
    folder = baseline_path.parent
    note_name = receipt['note']
    if Path(note_name).name != note_name or note_name == '文案.md':
        raise ValueError('局部更新笔记名称无效')
    old_copy, old_note = folder/'文案.md', folder/note_name
    if not complete_result(baseline) or set(baseline['artifacts']) != set(record['artifacts']):
        raise ValueError('局部更新成果清单或完整基线无效')
    source_path = process/'definition_search_record.json'
    if not (baseline['source_sha256'] == record['source_sha256'] == digest(source_path)):
        raise ValueError('局部更新来源记录已变化')
    if baseline['analysis_vars'] != record['analysis_vars'] or baseline['database'] != record['database']:
        raise ValueError('局部更新定义范围已变化')
    for name, sha in baseline['artifacts'].items():
        if Path(name).name != name:
            raise ValueError('基线成果路径无效')
        path = folder/name if name in ('文案.md', note_name) else formal/name
        if digest(path) != sha:
            raise ValueError('局部更新基线输入已变化：' + name)
        if name not in ('文案.md', note_name) and record['artifacts'][name] != sha:
            raise ValueError('局部更新包含数据或其他产物变化：' + name)
    validate_text_result(baseline, formal, process, old_note, old_copy, seen)
    copy_path, note_path = copy_path or formal/'文案.md', note_path or formal/note_name
    changes = text_update_changes(old_copy, copy_path, read(source_path), record['analysis_vars'])
    if changes is None or changes != receipt['changed_fields']:
        raise ValueError('局部更新超出已验证栏目')
    if [p['field'] for p in receipt['patches']] != changes:
        raise ValueError('局部更新栏目与生成片段不一致')
    expected = apply_fragment_patches(old_note.read_text(encoding='utf-8-sig'), receipt['patches'])
    if expected != note_path.read_text(encoding='utf-8-sig'):
        raise ValueError('局部更新笔记在生成范围外发生变化')
    text_constraints(original_result(baseline, process), copy_path.read_text(encoding='utf-8-sig'), expected)


def render_text_update(args, formal, process, binding, attempt):
    """Try the existing renderers without calculating data; unsupported layouts fall back."""
    from skill_config import load_config, configured_executable
    from r_runtime import runtime_plan
    from check_definition_output import check_summary_prose
    folder, baseline = Path(binding['folder']), binding['result']
    note_name = binding['audit_artifacts']['note']['path']
    old_note = folder/note_name
    source = process/'definition_search_record.json'
    if (not complete_result(baseline) or not old_note.is_file()
            or not (folder/'result_check.json').is_file()
            or digest(source) != binding['source_hash']
            or {p.name for p in formal.iterdir() if p.is_file()} != set(baseline['artifacts'])):
        return False
    if baseline.get('copy_sections', {}).get('tools', text_tool_hashes()) != text_tool_hashes():
        return False
    if any(digest(formal/name) != sha for name, sha in baseline['artifacts'].items()
           if name not in ('文案.md', note_name)):
        return False
    try:
        changes = text_update_changes(folder/'文案.md', formal/'文案.md', read(source), baseline['analysis_vars'])
    except ValueError as exc:
        write(attempt/'text-fallback.json', {'reason': '旧文案不适用局部渲染：' + str(exc)})
        return False
    if changes is None:
        return False
    text = old_note.read_text(encoding='utf-8-sig')
    # This is the actual theme recorded in the generated card, not a database guess.
    title = re.search(r'<div\b[^>]*data-summary-insight-title="true"[^>]*>', text)
    color = re.search(r'(?:[;"\s])color:([^;" ]+)', title[0]) if title else None
    if not color:
        return False
    config = load_config(args.config)
    rscript = configured_executable(config, 'rscript') or shutil.which('Rscript')
    if not rscript:
        raise ValueError('未找到 Rscript，无法调用现有文案生成器')
    request = attempt/'text-render-input.json'
    output = attempt/'text-fragments.json'
    write(request, {'root': str(ROOT), 'before': str(folder/'文案.md'),
                   'after': str(formal/'文案.md'), 'variables': baseline['analysis_vars'],
                   'color': color[1], 'output': str(output)})
    script = attempt/'render-text.R'
    script.write_text('''x <- jsonlite::read_json(commandArgs(TRUE)[1])
source(file.path(x$root, "scripts", "summary_fact_helpers.R"), encoding="UTF-8")
source(file.path(x$root, "scripts", "render_definition_bundle.R"), encoding="UTF-8")
v <- unlist(x$variables, use.names=FALSE)
out <- list(before=render_copy_fragments(x$before, v, x$color), after=render_copy_fragments(x$after, v, x$color))
jsonlite::write_json(out, x$output, auto_unbox=TRUE)
''', encoding='utf-8')
    env = dict(os.environ, DBCODEBOOK_DEFINITION_SKILL_ROOT=str(ROOT),
               DBCODEBOOK_DEFINITION_PYTHON=sys.executable)
    for key, value in runtime_plan(config)['environment'].items():
        if value is None: env.pop(key, None)
        else: env[key] = value
    if args.config:
        env['DBCODEBOOK_DEFINITION_CONFIG'] = str(args.config.resolve())
    with (attempt/'text-render.log').open('w', encoding='utf-8') as log:
        outcome = subprocess.run([rscript, '--vanilla', '--encoding=UTF-8', str(script), str(request)],
                                 cwd=formal, env=env, stdout=log, stderr=subprocess.STDOUT)
    if outcome.returncode:
        raise ValueError('局部文案渲染失败，见 ' + str(attempt/'text-render.log'))
    fragments = read(output)
    patches = [{'field': key, 'before': fragments['before'][key], 'after': fragments['after'][key]} for key in changes]
    try:
        candidate = apply_fragment_patches(text, patches)
    except ValueError as exc:
        write(attempt/'text-fallback.json', {'reason': str(exc)})
        return False
    candidate_path = attempt/note_name
    candidate_path.write_text(candidate, encoding='utf-8')
    call('check_reader_copy.py', '--copy', formal/'文案.md', '--record', source,
         '--analysis-vars', ','.join(baseline['analysis_vars']), '--note', candidate_path,
         log=attempt/'text-note-check.log')
    checks = text_constraints(original_result(baseline, process), formal.joinpath('文案.md').read_text(encoding='utf-8-sig'), candidate)
    from check_reader_copy import read_copy
    policy = read_copy(formal/'文案.md', baseline['analysis_vars'], read(source))['display_policy']
    check_summary_prose(candidate, checks, policy['compact_module'])
    if not all(item['ok'] for item in checks):
        raise ValueError('局部文案显示检查失败：' + json.dumps(checks, ensure_ascii=False))
    current = deepcopy(baseline)
    current.update(validation_mode='copy_sections', checks=[
        {'check':'unchanged baseline data and calculation', 'ok': True},
        {'check':'current copy and generated note', 'ok': True}, *checks],
        reused_checks=[item for item in baseline['checks'] if item['check'] not in {c['check'] for c in checks}], copy_sections={
            'baseline': str((folder/'result_check.json').relative_to(process)),
            'baseline_sha256': digest(folder/'result_check.json'), 'note': note_name,
            'changed_fields': changes, 'patches': patches, 'tools': text_tool_hashes()})
    current['artifacts']['文案.md'] = digest(formal/'文案.md')
    current['artifacts'][note_name] = digest(candidate_path)
    validate_text_result(current, formal, process, candidate_path)
    # Commit only after all fragment and unchanged-input checks passed.
    shutil.copy2(candidate_path, formal/note_name)
    write(process/'result_check.json', current)
    write(attempt/'result-check.json', current)
    return True


def run(args):
    formal, process = args.formal_dir.resolve(), args.process_dir.resolve()
    report = read(process / er.REPORT_NAME)
    binding = report.get('copy_update', {})
    if report['status'] != 'running' or binding.get('status') != 'prepared' or binding.get('formal_dir') != str(formal):
        raise ValueError('先在修改前运行 prepare；已完成或失败的尝试不能重复执行')
    check_unchanged(formal, process, binding)
    folder = Path(binding['folder'])
    source_path = process / 'definition_search_record.json'
    source = read(source_path)
    impact = read(folder / 'definition_change_impact.json')
    impact.update(schema_version=3, status='CHANGE_SCOPE_RECORDED',
                  change_summary=binding['reason'], changed_dimensions=['copy'])
    omit_questionnaire = args.omit_questionnaire or binding.get('omit_questionnaire')
    if omit_questionnaire:
        if any(line.strip() == '## 问卷' for line in
               (formal / '文案.md').read_text(encoding='utf-8-sig').splitlines()):
            raise ValueError('正文仍有问卷，不能登记为全部省略')
        for question in source.get('questionnaire_evidence', []):
            question.update(display_required=False, display_omission_reason=omit_questionnaire,
                            rendered_in_copy=False, copy_locator='不展示：' + omit_questionnaire)
        write(source_path, source)
        impact.update(question_groups=[], question_groups_not_applicable_reason=omit_questionnaire)
    write(process / 'definition_change_impact.json', impact)
    binding['omit_questionnaire'] = omit_questionnaire
    attempt_folder = folder / 'attempts' / str(len(binding.get('attempts', [])) + 1)
    attempt_folder.mkdir(parents=True, exist_ok=False)
    binding.setdefault('attempts', []).append({'folder': str(attempt_folder), 'status': 'running'})
    report['copy_update'] = binding
    er.save(*er.paths(process), report)
    stage = 'copy'
    try:
        call('check_reader_copy.py', '--copy', formal / '文案.md', '--record', source_path,
             '--process-dir', process, log=attempt_folder / 'copy-check.log')
        call('execution_report.py', 'stage-finish', '--process-dir', process, '--stage-id', stage,
             '--status', 'completed', '--copy', formal / '文案.md', '--summary', binding['reason'])
        stage = 'generate'
        call('execution_report.py', 'stage-start', '--process-dir', process, '--stage-id', stage,
             '--name', '重新生成并核对成果', '--role', '固定程序')
        art = binding['audit_artifacts']
        incremental = render_text_update(args, formal, process, binding, attempt_folder)
        if not incremental:
            lognames = [n for n in binding['result']['artifacts'] if '_run_' in n and n.endswith('.log')]
            if len(lognames) != 1:
                raise ValueError('原成果日志前缀不唯一')
            prefix = lognames[0].rsplit('_run_', 1)[0]
            pwsh = args.pwsh or shutil.which('pwsh')
            if not pwsh:
                raise ValueError('未找到 PowerShell 7，请传入 --pwsh')
            cmd = [pwsh, '-NoProfile', '-File', str(ROOT / 'scripts/run_r_definition.ps1'),
                   '-WorkDir', str(formal), '-Script', binding['r_script'], '-LogPrefix', prefix,
                   '-ProcessDir', str(process), '-Database', source['database']]
            if args.config:
                cmd += ['-Config', str(args.config.resolve())]
            with (attempt_folder / 'generate.log').open('w', encoding='utf-8') as log:
                outcome = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            if outcome.returncode:
                raise ValueError('正式生成失败，见 ' + str(attempt_folder / 'generate.log'))
            for name in binding['result']['artifacts']:
                if not name.endswith('.xlsx'):
                    continue
                same = workbook_content(formal / name) == workbook_content(folder / name)
                if (name.startswith('db_') or name.startswith('analysis_db_')) and not same:
                    raise ValueError('纯文案修改产生数据变化：' + name)
                if same:
                    shutil.copy2(folder / name, formal / name)
            old = original_result(binding['result'], process)
            columns = next(c['detail'] for c in old['checks'] if c['check'] == 'analysis_db columns')
            art = binding['audit_artifacts']
            defaults = record_defaults(source)
            raw = list(dict.fromkeys(v for group in source['source_groups'] for v in group['raw_variables'] if v not in defaults))
            raw = previous_raw_order(old, raw)
            params = ['--complete', '--db', source['database'].lower(), '--formal-dir', formal,
                      '--process-dir', process, '--expected-files', ','.join(n for n in old['artifacts'] if not n.endswith('.log')),
                      '--raw-vars', ','.join(raw), '--analysis-db', art['analysis_db']['path'],
                      '--analysis-codebook', art['analysis_codebook']['path'], '--analysis-columns', ','.join(columns),
                      '--analysis-vars', ','.join(old['analysis_vars']), '--check-summary-facts',
                      '--require-log-exit-code', '--log-prefix', prefix, '--report', process / 'result_check.json']
            if source.get('language'):
                params += ['--language', source['language']]
            params += previous_check_options(old)
            call('check_definition_output.py', *params, log=attempt_folder / 'result-check.log')
        reader_exists = (process / 'reader_comprehension_review.json').exists()
        previous_audit = read(process / 'readability_audit.json')
        previous_note = previous_audit.get('artifacts', {}).get('note', {})
        note_unchanged = digest(formal / art['note']['path']).lower() == previous_note.get('sha256', '').lower()
        reader_required = reader_exists or previous_audit.get('reader_review_required', False)
        preserve = ['--preserve-reader'] if reader_exists and note_unchanged else []
        # Keep the previous evidence before init invalidates an obsolete review.
        for name in ('reader_comprehension_review.json', 'ordinary_reader_input.md'):
            if (process / name).is_file():
                shutil.copy2(process / name, attempt_folder / name)
        call('check_definition_readability.py', 'init', '--formal-dir', formal, '--process-dir', process,
             '--topic-id', report['topic_id'], '--note', art['note']['path'], '--r-script', binding['r_script'],
             '--analysis-db', art['analysis_db']['path'], '--analysis-codebook', art['analysis_codebook']['path'],
             '--overwrite', *preserve, log=attempt_folder / 'delivery-init.log')
        if reader_required and not preserve:
            report = read(process / er.REPORT_NAME)
            report['copy_update'].update(status='awaiting_reader',
                delivery_artifacts=current_artifacts(formal, binding),
                recovery_artifacts=current_artifacts(formal, binding))
            report['copy_update']['attempts'][-1]['status'] = 'awaiting_reader'
            er.save(*er.paths(process), report)
            call('execution_report.py', 'stage-finish', '--process-dir', process, '--stage-id', stage,
                 '--status', 'completed', '--summary', '已生成当前成果；原读者结论过期，须按第7步复核受影响内容。')
            return {'ok': True, 'status': 'READER_REVIEW_REQUIRED', 'website_submitted': False,
                    'next': '按第7步完成受影响内容的普通读者复核，再运行本入口 finish；不重做研究和生成。'}
        call('check_definition_readability.py', 'check', '--formal-dir', formal, '--process-dir', process,
             '--topic-id', report['topic_id'], log=attempt_folder / 'delivery-check.log')
        call('execution_report.py', 'stage-finish', '--process-dir', process, '--stage-id', stage,
             '--status', 'completed', '--summary',
             '仅重建并核对指定文案栏目；数据与计算检查沿用有效完整基线，未重跑正式R或重读数据表；交付检查仍读取分析字典。'
             if incremental else '完整生成与成果检查通过；内容未变的数据附件沿用原文件。')
        return complete_update(process)
    except (Exception, SystemExit) as exc:
        # Full checker output stays in the attempt logs; do not exceed Windows argv limits.
        error_summary = str(exc)[:2000]
        current = read(process / er.REPORT_NAME)
        if er.latest_stage(current, stage)['status'] == 'running':
            call('execution_report.py', 'stage-finish', '--process-dir', process, '--stage-id', stage,
                 '--status', 'failed', '--summary', error_summary)
        issue = call('execution_report.py', 'issue', '--process-dir', process, '--stage-id', stage,
                     '--kind', 'abnormal', '--description', error_summary, '--status', 'open')
        report = read(process / er.REPORT_NAME)
        report['copy_update']['status'] = 'failed'
        report['copy_update'].setdefault('issue_numbers', []).append(json.loads(issue.stdout)['issue_count'])
        report['copy_update']['recovery_artifacts'] = current_artifacts(formal, binding)
        report['copy_update']['attempts'][-1].update(status='failed', stage=stage, error=str(exc))
        er.save(*er.paths(process), report)
        raise


def current_artifacts(formal, binding):
    return {name: digest(formal / name) if (formal / name).is_file() else None
            for name in binding['result']['artifacts']}


def retry(args):
    formal, process = args.formal_dir.resolve(), args.process_dir.resolve()
    report = read(process / er.REPORT_NAME)
    binding = report.get('copy_update', {})
    if report['status'] != 'running' or binding.get('status') not in ('failed', 'awaiting_reader') or binding.get('formal_dir') != str(formal):
        raise ValueError('retry 仅恢复本任务的失败或读者要求返修的局部文案更新')
    if not binding.get('recovery_artifacts'):
        raise ValueError('旧失败记录没有现场文件指纹，不能自动恢复；先核实原基线和失败后的文件')
    check_unchanged(formal, process, binding)
    binding['status'] = 'prepared'
    binding['attempts'][-1]['retry_reason'] = args.reason
    er.save(*er.paths(process), report)
    call('execution_report.py', 'stage-start', '--process-dir', process, '--stage-id', 'copy',
         '--name', '修正文案后重新执行', '--role', '主执行', '--mode', 'rework')
    return run(args)


def complete_update(process):
    report = read(process / er.REPORT_NAME)
    for number in report['copy_update'].get('issue_numbers', []):
        if report['issues'][number - 1]['status'] == 'open':
            call('execution_report.py', 'issue-amend', '--process-dir', process, '--issue-number', number,
                 '--status', 'resolved', '--resolution', '同一基线重试后，当前完整成果和发布条件检查通过；失败日志和尝试记录保留。',
                 '--note', '固定局部更新入口在重新验证成功后关闭本入口登记的问题。')
    report = read(process / er.REPORT_NAME)
    report['copy_update']['status'] = 'completed'
    report['copy_update']['attempts'][-1]['status'] = 'completed'
    er.save(*er.paths(process), report)
    status = 'completed_with_issues' if report.get('issues') else 'completed'
    call('execution_report.py', 'finish', '--process-dir', process, '--status', status,
         '--summary', '局部文案已生成并验证；尚未同步网站。')
    return {'ok': True, 'status': 'LOCAL_UPDATE_COMPLETE', 'website_submitted': False}


def finish(args):
    formal, process = args.formal_dir.resolve(), args.process_dir.resolve()
    report = read(process / er.REPORT_NAME)
    binding = report.get('copy_update', {})
    if report['status'] != 'running' or binding.get('status') != 'awaiting_reader' or binding.get('formal_dir') != str(formal):
        raise ValueError('finish 仅用于本入口等待读者复核的当前成果')
    if current_artifacts(formal, binding) != binding['delivery_artifacts']:
        raise ValueError('待复核成果已变化；须重新生成和绑定，不能沿用旧发布条件')
    if research_record(read(Path(binding['folder']) / 'definition_search_record.json')) != research_record(read(process / 'definition_search_record.json')):
        raise ValueError('研究内容已变化，不能沿用纯文案更新')
    call('check_definition_readability.py', 'check', '--formal-dir', formal, '--process-dir', process,
         '--topic-id', report['topic_id'])
    return complete_update(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'run', 'retry', 'finish'])
    parser.add_argument('--formal-dir', type=Path, required=True)
    parser.add_argument('--process-dir', type=Path, required=True)
    parser.add_argument('--legacy-report', type=Path, help='旧主题仅缺双路探索登记时，指定经核对的已完成历史 R 复核报告；仍核对当前 R、来源及成果')
    parser.add_argument('--path-map', type=Path, help='prepare时显式声明旧主题根目录到当前副本的映射；保留原审核及内容校验')
    parser.add_argument('--reason', help='本次纯表达或展示修改；至少20字')
    parser.add_argument('--omit-questionnaire', help='已删除整节问卷时，给出明确的省略原因（至少20字）')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--pwsh')
    args = parser.parse_args()
    if args.path_map and args.command != 'prepare':
        parser.error('--path-map仅用于修改前prepare；后续沿用已保存的新目录绑定')
    if args.command in ('prepare', 'retry') and len(args.reason or '') < 20:
        parser.error('prepare/retry须说明具体修改或修复内容（至少20字）')
    if args.omit_questionnaire and len(args.omit_questionnaire) < 20:
        parser.error('请说明完整的问卷省略原因（至少20字）')
    try:
        command = {'prepare': prepare, 'run': run, 'retry': retry, 'finish': finish}[args.command]
        print(json.dumps(command(args), ensure_ascii=False))
    except (Exception, SystemExit) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

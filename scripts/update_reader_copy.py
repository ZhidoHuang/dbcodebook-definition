#!/usr/bin/env python3
"""Prepare before editing; rebuild a copy-only change without new research/review.

No browser access, downloads, or publishing. Existing runner/checkers remain the
production path. A changed research input or calculation fails before generation.

Commands: prepare saves the real pre-edit baseline; run generates/verifies the
declared change; retry retains that baseline; finish closes a requested review;
periods expands empty display periods without recalculating data.

Existing bounded APIs (not steps for a new topic):
  --metadata-only --metadata-kind tree_identity verifies explicit identities
    inserted into existing result nodes and the sole generated summary delta.
  --metadata-only --metadata-kind label_metadata verifies literal result labels
    and evidenced source identities against raw_codebook; no computed labels,
    data changes, new grouping or whole-page regeneration are permitted.
The former --component-only scratch-generation entry is retired. It must not
start new preparation or generation, nor silently fall back to full generation.
Historical receipts remain readable by the delivery checker.
These APIs preserve current source/calculation evidence, do not publish, and
require the same scope in delivery and website verification. Failed or missing
baselines cannot be replaced by candidates; tool changes require revalidation.

--legacy-report only supplies verified historical R review where the old topic
lacks the later dual-exploration registration. It never overrides a failed
current review or source check. --path-map supplies actual relocated roots;
see references/new-device.md. --r-script and --note select unambiguous formal
basenames. --omit-questionnaire records a justified whole-section omission;
per-question display fields remain part of the questionnaire evidence.
"""
import argparse
import csv
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


def formal_table(name):
    return name.endswith('.xlsx') or (name.endswith('.csv') and name.startswith(('db_','analysis_db_')))


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


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
        if formal_table(name) or name in ('文案.md', audit['artifacts'].get('note', {}).get('path')):
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
         '--task', args.reason, '--workflow', 'general', '--archive-previous')
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
        if (formal_table(name) or name == '文案.md') and digest(folder / name) != sha:
            raise ValueError('修改前成果副本已变化：' + name)
    review = binding['review']
    if er.input_hashes(review['inputs'], review.get('r_scope', 'full'), SOURCE_SCOPE) != review['inputs']:
        raise ValueError('研究或计算复核输入已变化')


def workbook_content(path):
    if Path(path).suffix.lower() == '.csv':
        hasher=hashlib.sha256()
        with Path(path).open(encoding='utf-8-sig',newline='') as stream:
            for row in csv.reader(stream):
                hasher.update((json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8'))
        return {'csv_content':hasher.hexdigest()}
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
    while record.get('copy_sections') or record.get('period_display'):
        receipt = record.get('copy_sections') or record['period_display']
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
    # Question wording/placement can change during a copy update; retain its current scope.
    impact_path = process / 'definition_change_impact.json'
    impact = read(impact_path if impact_path.is_file() else folder / 'definition_change_impact.json')
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
                if not formal_table(name):
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


def period_tool_hashes():
    return {name: digest(ROOT / name) for name in (
        'scripts/definition_display.py', 'scripts/update_reader_copy.py',
        'scripts/render_definition_bundle.R', 'references/display-periods.json')}


def validate_period_result(record, formal, process):
    from definition_display import expand_period_tables
    receipt = record['period_display']
    baseline_path = (process / receipt['baseline']).resolve()
    baseline_path.relative_to(process.resolve())
    if digest(baseline_path) != receipt['baseline_sha256']:
        raise ValueError('周期展示基线已变化')
    # Reproduce the transformation with the current code below. The recorded
    # tool hashes identify generation provenance, not a substitute for this check.
    baseline = read(baseline_path)
    if not (baseline.get('ok') and baseline.get('scope') == 'complete'
            and baseline.get('status') == 'MACHINE_CHECK_PASS'
            and all(c.get('ok') is True for c in baseline.get('checks', []))):
        raise ValueError('周期展示缺少原完整验收依据')
    if set(baseline['artifacts']) != set(record['artifacts']):
        raise ValueError('周期更新改变了交付物清单')
    if record['source_sha256'] != baseline['source_sha256'] or digest(process/'definition_search_record.json') != record['source_sha256']:
        raise ValueError('周期更新改变了来源方案')
    for name, sha in baseline['artifacts'].items():
        old = baseline_path.parent / name
        current = formal / name
        if Path(name).name != name:
            raise ValueError('无效成果名称')
        if name in receipt['changed_files']:
            if digest(old) != sha:
                raise ValueError('旧周期表基线已变化：' + name)
            expected, tables = expand_period_tables(old.read_text(encoding='utf-8-sig'), receipt['periods'])
            if not tables or expected != current.read_text(encoding='utf-8-sig'):
                raise ValueError('周期表以外内容发生变化：' + name)
        elif digest(current) != sha or record['artifacts'][name] != sha:
            raise ValueError('周期更新改变了数据、R或其他成果：' + name)


def periods(args):
    """Display-only operation: reuse accepted cells, never execute definition R."""
    from definition_display import display_periods, expand_period_tables
    formal, process = args.formal_dir.resolve(), args.process_dir.resolve()
    previous = read(process / er.REPORT_NAME)
    if previous['status'] == 'running':
        raise ValueError('已有任务执行中，不能覆盖')
    baseline = read(process/'result_check.json')
    if not (baseline.get('ok') and baseline.get('scope') == 'complete'
            and baseline.get('status') == 'MACHINE_CHECK_PASS'
            and baseline.get('checks') and all(c.get('ok') is True for c in baseline['checks'])):
        raise ValueError('先提供已有完整成果验收；局部检查不能代替')
    for name, sha in baseline['artifacts'].items():
        if Path(name).name != name or digest(formal/name) != sha:
            raise ValueError('原验收成果已变化，不能补造基线：' + name)
    if digest(process/'definition_search_record.json') != baseline['source_sha256']:
        raise ValueError('来源方案已变化')
    source = read(process/'definition_search_record.json')
    audit = read(process/'readability_audit.json')
    if any(i.get('status') == 'open' for i in previous.get('issues', [])):
        raise ValueError('存在阻断交付的问题')
    note = audit['artifacts']['note']['path']
    candidates = [n for n in baseline['artifacts'] if n.endswith('.html') or n == note]
    observed = []
    for name in candidates:
        text = (formal/name).read_text(encoding='utf-8-sig')
        observed += re.findall(r"class=['\"]dbcb-var-cycle-label['\"][^>]*>(.*?)</span>", text)
        for header in re.findall(r'<table\b[^>]*class="heatmap-table"[^>]*>\s*<tr>(.*?)</tr>', text, re.S):
            observed += re.findall(r'<th[^>]*>(.*?)</th>', header, re.S)[3:]
    target = display_periods(source['database'], observed, source.get('language'), source.get('dataset_id'))
    changes = {}
    for name in candidates:
        old = (formal/name).read_text(encoding='utf-8-sig')
        new, tables = expand_period_tables(old, target)
        if new != old:
            changes[name] = (new, tables)
    if not changes:
        return {'ok': True, 'status': 'PERIODS_ALREADY_COMPLETE', 'periods': target}
    folder = process/'period_updates'/str(uuid.uuid4())
    folder.mkdir(parents=True)
    write(folder/'result_check.json', baseline)
    for name in changes:
        shutil.copy2(formal/name, folder/name)
    for name in ('readability_audit.json', 'definition_change_impact.json'):
        shutil.copy2(process/name, folder/name)
    call('execution_report.py', 'init', '--process-dir', process, '--database', previous['database'],
         '--topic-id', previous['topic_id'], '--topic-name', previous['topic_name'],
         '--task', args.reason, '--workflow', 'general')
    call('execution_report.py', 'stage-start', '--process-dir', process, '--stage-id', 'generate',
         '--name', '仅补齐周期显示', '--role', '固定程序')
    for name, (text, _) in changes.items():
        (formal/name).write_text(text, encoding='utf-8')
    result = deepcopy(baseline)
    result.pop('copy_sections', None)
    result.update(validation_mode='period_display',
        checker_sha256=digest(ROOT/'scripts/check_definition_output.py'),
        checks=[{'check':'period grids and unchanged inputs', 'ok':True,
                 'detail':'原有人数和单元格保留，仅插入空周期；数据、R、文案、来源字节未变。'}],
        reused_checks=baseline['checks'], period_display={
            'baseline':str((folder/'result_check.json').relative_to(process)),
            'baseline_sha256':digest(folder/'result_check.json'), 'periods':target,
            'changed_files':list(changes), 'tools':period_tool_hashes()})
    for name in changes:
        result['artifacts'][name] = digest(formal/name)
    validate_period_result(result, formal, process)
    write(process/'result_check.json', result)
    write(folder/'period-check.json', {n:t for n,(_,t) in changes.items()})
    impact = read(process/'definition_change_impact.json')
    impact.update(schema_version=3, changed_dimensions=['display'], change_summary=args.reason,
                  status='CHANGE_SCOPE_RECORDED')
    write(process/'definition_change_impact.json', impact)
    art = audit['artifacts']
    rfile = next(n for n in baseline['artifacts'] if n.lower().endswith('.r'))
    call('check_definition_readability.py', 'init', '--formal-dir', formal, '--process-dir', process,
         '--topic-id', previous['topic_id'], '--note', note, '--r-script', rfile,
         '--analysis-db', art['analysis_db']['path'], '--analysis-codebook', art['analysis_codebook']['path'],
         '--overwrite', log=folder/'delivery-init.log')
    call('check_definition_readability.py', 'check', '--formal-dir', formal, '--process-dir', process,
         '--topic-id', previous['topic_id'], log=folder/'delivery-check.log')
    call('execution_report.py', 'stage-finish', '--process-dir', process, '--stage-id', 'generate',
         '--status', 'completed', '--summary', '周期格局部核对通过；数据与计算验收沿用原完整证据，未重跑R，四工作簿字节不变。')
    return {'ok':True, 'status':'LOCAL_UPDATE_COMPLETE', 'periods':target,
            'changed_files':list(changes), 'website_submitted':False}



METADATA_RECEIPT = 'definition_metadata_update.json'


def metadata_tools():
    return {name: digest(ROOT/'scripts'/name) for name in (
        'update_reader_copy.py', 'check_definition_readability.py', 'check_reader_copy.py',
        'check_definition_output.py', 'render_definition_bundle.R', 'summary_fact_helpers.R',
        'reference_format.py', 'definition_order.py')}



def metadata_static_names(r_script, config_path, folder):
    """Read literal named summary metadata with R's parser; never run topic code."""
    from skill_config import load_config, configured_executable
    from r_runtime import runtime_plan
    script, output = folder/'static-names.R', folder/'static-names.json'
    script.write_text(r"""args <- commandArgs(TRUE)
z <- parse(args[1],encoding='UTF-8')
known <- list(); answer <- NULL
value <- function(e) {
 if(is.character(e)) return(e)
 if(is.symbol(e)) return(known[[as.character(e)]])
 if(!is.call(e)) return(NULL)
 if(identical(e[[1]],as.name('c'))) {
  parts <- as.list(e)[-1]; vals <- lapply(parts,value)
  if(any(vapply(vals,is.null,logical(1)))) return(NULL)
  return(unlist(vals,use.names=TRUE))
 }
 if(identical(e[[1]],as.name('setNames'))&&length(e)==3) {
  vals<-value(e[[2]]); keys<-value(e[[3]])
  if(!is.null(vals)&&!is.null(keys)&&length(vals)==length(keys)) return(setNames(vals,keys))
 }
 NULL
}
for(e in z) {
 if(is.call(e)&&identical(e[[1]],as.name('<-'))&&is.symbol(e[[2]])) {
  key<-as.character(e[[2]]);v<-value(e[[3]])
  if(!is.null(v)) known[[key]]<-v else known[[key]]<-NULL
 }
 if(is.call(e)&&identical(e[[1]],as.name('render_definition_bundle'))) {
  parts<-as.list(e)
  if('summary_meanings'%in%names(parts)) answer<-value(parts[['summary_meanings']])
 }
}
if(is.null(answer)) answer<-known[['summary_meanings']]
if(is.null(answer)||is.null(names(answer))||any(!nzchar(names(answer)))||anyDuplicated(names(answer))) answer<-list()
jsonlite::write_json(as.list(answer),args[2],auto_unbox=TRUE)
""",encoding='utf-8')
    config=load_config(config_path); rscript=configured_executable(config,'rscript') or shutil.which('Rscript')
    if not rscript: raise ValueError('Rscript unavailable for static named metadata')
    env=dict(os.environ)
    for k,v in runtime_plan(config)['environment'].items():
        if v is None: env.pop(k,None)
        else: env[k]=v
    result=subprocess.run([rscript,'--vanilla','--encoding=UTF-8',str(script),str(r_script),str(output)],
                          cwd=folder,env=env,capture_output=True,text=True,encoding='utf-8')
    (folder/'static-names.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode: raise ValueError('Cannot parse original named metadata: '+str(folder/'static-names.log'))
    values=read(output)
    return values if isinstance(values,dict) else {}


def metadata_prepare(args):
    """Freeze the actual pre-edit state; historical reports are evidence, not new PASSes."""
    formal, process = args.formal_dir.resolve(), args.process_dir.resolve()
    marker = process / METADATA_RECEIPT
    previous_receipt = None
    if marker.exists():
        previous_receipt = read(marker)
        if previous_receipt.get('status') != 'verified':
            raise ValueError('Metadata baseline already exists; retry it rather than replacing it')
        previous_baseline = read(previous_receipt['baseline'])
        verify_metadata_update(formal, process, previous_baseline['topic_id'])
    source = process/'definition_search_record.json'
    record = read(source)
    from check_definition_output import read_xlsx_rows
    def unique(pattern):
        files = list(formal.glob(pattern))
        if len(files) != 1: raise ValueError('Expected unique artifact: ' + pattern)
        return files[0].name
    artifacts = {'copy': '文案.md', 'note': getattr(args, 'note', None) or (unique('*笔记.md') if list(formal.glob('*笔记.md')) else ''), 'public_r': getattr(args, 'r_script', None) or unique('*.R'),
                 'analysis_db': unique('analysis_db_*.xlsx') if list(formal.glob('analysis_db_*.xlsx')) else unique('analysis_db_*.csv'), 'analysis_codebook': unique('analysis_codebook_*.xlsx'),
                 'full_db': unique('db_*.xlsx') if list(formal.glob('db_*.xlsx')) else unique('db_*.csv'), 'full_codebook': unique('codebook_*.xlsx')}
    if not getattr(args, 'note', None) and not list(formal.glob('*笔记.md')):
        notes = [p.name for p in formal.glob('*.md') if p.name != '文案.md']
        if len(notes) != 1: raise ValueError('Ambiguous note; use --note')
        artifacts['note'] = notes[0]
    for name in artifacts.values():
        if Path(name).name != name or not (formal/name).is_file(): raise ValueError('Invalid explicit metadata artifact')
    rows = read_xlsx_rows(formal/artifacts['analysis_codebook'])
    vi = rows[0].index('Variable')
    variables = [r[vi] for r in rows[1:]]
    if not variables or len(variables) != len(set(variables)) or variables != record['approved_analysis_vars']:
        raise ValueError('Analysis dictionary and source variable order differ')
    if not (formal/'raw_codebook.csv').is_file(): raise ValueError('Missing raw identity dictionary')
    historical = [process/n for n in ('execution_report.json', 'result_check.json')]
    if not all(p.is_file() for p in historical): raise ValueError('Retain real historical execution and result reports')
    folder = process/'copy_updates'/str(uuid.uuid4())
    folder.mkdir(parents=True)
    hashes = {p.name: digest(p) for p in formal.iterdir() if p.is_file()}
    for role in ('copy', 'note', 'public_r', 'analysis_codebook', 'full_codebook'):
        shutil.copy2(formal/artifacts[role], folder/artifacts[role])
    shutil.copy2(source, folder/source.name)
    history = []
    for original in historical:
        target = folder/('historical_' + original.name)
        shutil.copy2(original, target)
        history.append({'path': str(target), 'sha256': digest(target), 'original_path': str(original)})
    baseline = {'schema_version': 1, 'scope': 'metadata_only', 'subscope': getattr(args, 'metadata_kind', 'tree_identity'),
        'formal_dir': str(formal), 'topic_id': str(record['topic_id']).zfill(3),
        'database': record['database'], 'folder': str(folder), 'reason': args.reason,
        'artifacts': artifacts, 'before_hashes': hashes, 'source_sha256': digest(source),
        'analysis_vars': variables, 'historical_evidence': history,
        'historical_validation': 'PRESERVED_NOT_REVALIDATED', 'tools': metadata_tools()}
    baseline['static_display_names'] = metadata_static_names(folder/artifacts['public_r'], args.config, folder)
    write(folder/'metadata-baseline.json', baseline)
    receipt = {'scope': 'metadata_only', 'status': 'prepared',
        'baseline': str(folder/'metadata-baseline.json'), 'baseline_sha256': digest(folder/'metadata-baseline.json')}
    if previous_receipt is not None:
        shutil.copy2(marker, folder/'previous-metadata-receipt.json')
        receipt['previous_receipt'] = {'path': str(folder/'previous-metadata-receipt.json'),
                                       'sha256': digest(folder/'previous-metadata-receipt.json')}
    write(marker, receipt)
    return {'ok': True, 'status': 'METADATA_PREPARED', 'scope': 'metadata_only',
            'subscope': baseline['subscope'], 'receipt': str(marker), 'historical_validation': 'PRESERVED_NOT_REVALIDATED'}


def metadata_inputs(formal, process, receipt, revalidate=False):
    from check_definition_output import read_xlsx_rows
    from check_reader_copy import sections, check_tree_result_order
    baseline_path = Path(receipt['baseline']).resolve()
    baseline_path.relative_to(process.resolve()/'copy_updates')
    if digest(baseline_path) != receipt['baseline_sha256']: raise ValueError('Metadata baseline changed')
    baseline = read(baseline_path)
    folder = baseline_path.parent
    if (baseline['scope'] != 'metadata_only' or baseline['subscope'] not in ('tree_identity', 'label_metadata')
            or Path(baseline['formal_dir']).resolve() != formal.resolve()):
        raise ValueError('Metadata baseline scope or target mismatch')
    if not revalidate and receipt.get('tools') != metadata_tools():
        raise ValueError('Metadata tools changed; run/retry against the retained baseline')
    for evidence in baseline['historical_evidence']:
        if digest(evidence['path']) != evidence['sha256']: raise ValueError('Historical evidence changed')
    source = process/'definition_search_record.json'
    if digest(source) != baseline['source_sha256'] or digest(folder/source.name) != baseline['source_sha256']:
        raise ValueError('Metadata source plan changed')
    artifacts = baseline['artifacts']
    names = {p.name for p in formal.iterdir() if p.is_file()}
    if names != set(baseline['before_hashes']): raise ValueError('Metadata artifact set changed')
    changed = {artifacts['copy'], artifacts['note']}
    if baseline['subscope'] == 'label_metadata':
        changed.update(artifacts[k] for k in ('public_r', 'analysis_codebook', 'full_codebook'))
    for name, signature in baseline['before_hashes'].items():
        if Path(name).name != name: raise ValueError('Invalid baseline artifact name')
        original = folder/name if name in changed else formal/name
        if digest(original) != signature: raise ValueError('Change outside tree metadata: ' + name)
    for role in ('public_r', 'analysis_codebook', 'full_codebook'):
        if digest(folder/artifacts[role]) != baseline['before_hashes'][artifacts[role]]:
            raise ValueError('Retained baseline artifact changed: ' + role)
    rows = read_xlsx_rows(formal/artifacts['analysis_codebook'])
    vi, li = rows[0].index('Variable'), rows[0].index('Label')
    variables = [r[vi] for r in rows[1:]]
    record = read(source)
    if variables != baseline['analysis_vars'] or variables != record['approved_analysis_vars']:
        raise ValueError('Analysis variable set or order changed')
    old_copy = (folder/artifacts['copy']).read_text(encoding='utf-8-sig')
    new_copy = (formal/artifacts['copy']).read_text(encoding='utf-8-sig')
    if baseline['subscope'] == 'label_metadata' and '[[result:' not in old_copy:
        if old_copy != new_copy: raise ValueError('Label scope changed source copy')
        checked = {'scope': 'no_tree_unchanged'}
    else:
        checked = metadata_tree_identity(old_copy, new_copy,
            read_xlsx_rows(folder/artifacts['analysis_codebook']), record, baseline.get('static_display_names'))
    return baseline, folder, checked


def metadata_tree_identity(before, after, rows, record, extra_names=None):
    from check_reader_copy import sections, check_tree_result_order
    vi, li = rows[0].index('Variable'), rows[0].index('Label')
    variables = [r[vi] for r in rows[1:]]
    token = r'\[\[result:(?:([A-Za-z][A-Za-z0-9_.]*)\|)?([^]\r\n]+)\]\]'
    old, new = list(re.finditer(token, before)), list(re.finditer(token, after))
    strip = lambda text: re.sub(token, lambda m: '[[result:' + m[2] + ']]', text)
    if not new or len(old) != len(new) or strip(before) != strip(after):
        raise ValueError('Copy changed beyond result identity insertion')
    oldrows = rows
    labels = {r[vi]: {str(r[li])} for r in oldrows[1:]}
    for v, label in (extra_names or {}).items():
        if v in labels: labels[v].add(label)
    for match in old:
        if match[1] in labels: labels[match[1]].add(match[2])
    for plan in record.get('definition_plan', []):
        v = plan.get('analysis_var')
        if v in labels:
            labels[v].update(plan[k] for k in ('display_name', 'chinese_name', 'meaning')
                             if isinstance(plan.get(k), str))
    normalize = lambda value: re.sub(r'\s+', '', value).translate(str.maketrans({'（':'(', '）':')', 'μ':'µ'}))
    for a, b in zip(old, new):
        if not b[1] or (a[1] and a[1] != b[1]): raise ValueError('Existing result identity changed or new identity missing')
        # Identity is proved from explicit prior binding or exact existing named metadata, never position.
        if not a[1]:
            adjacent = re.match(r'[ \t]*\[\[meta:([^]\r\n]+)\]\]', after[b.end():])
            full = normalize(b[2])
            with_meta = normalize(b[2] + adjacent[1]) if adjacent else full
            stem = re.sub(r'\([ -~]+\)$', '', full)
            possible = {v for v, values in labels.items()
                        if (full in {normalize(x) for x in values} or with_meta in {normalize(x) for x in values})
                        or (stem != full and re.search('[\u4e00-\u9fff]', stem)
                            and stem in {normalize(x) for x in values})}
            if possible != {b[1]}:
                raise ValueError('Tree display name has no unique exact identity evidence: ' + str((b[1], b[2])))
    checked = check_tree_result_order(sections(after, 2).get('摘要导读', ''), variables, {})
    if checked.get('scope') != 'explicit_results': raise ValueError('Expected explicit result tree')
    return checked


def metadata_render(formal, folder, baseline, config_path, attempt):
    """Run only the existing public fragment renderer, never source computations."""
    from skill_config import load_config, configured_executable
    from r_runtime import runtime_plan
    text = (folder/baseline['artifacts']['note']).read_text(encoding='utf-8-sig')
    title = re.search(r'<div\b[^>]*data-summary-insight-title="true"[^>]*>', text)
    color = re.search(r'(?:[;"\s])color:([^;" ]+)', title[0]) if title else None
    if not color: raise ValueError('No uniquely identified original summary theme')
    config = load_config(config_path)
    rscript = configured_executable(config, 'rscript') or shutil.which('Rscript')
    if not rscript: raise ValueError('Rscript unavailable for source-driven fragment generation')
    request, output = attempt/'metadata-render-input.json', attempt/'metadata-fragments.json'
    write(request, {'root': str(ROOT), 'before': str(folder/'文案.md'), 'after': str(formal/'文案.md'),
                    'variables': baseline['analysis_vars'], 'color': color[1], 'output': str(output)})
    script = attempt/'metadata-render.R'
    script.write_text('x <- jsonlite::read_json(commandArgs(TRUE)[1])\n'
        'source(file.path(x$root,"scripts","summary_fact_helpers.R"),encoding="UTF-8")\n'
        'source(file.path(x$root,"scripts","render_definition_bundle.R"),encoding="UTF-8")\n'
        'v <- unlist(x$variables,use.names=FALSE)\n'
        'out <- list(before=render_copy_fragments(x$before,v,x$color),after=render_copy_fragments(x$after,v,x$color))\n'
        'jsonlite::write_json(out,x$output,auto_unbox=TRUE)\n', encoding='utf-8')
    env = dict(os.environ, DBCODEBOOK_DEFINITION_SKILL_ROOT=str(ROOT), DBCODEBOOK_DEFINITION_PYTHON=sys.executable)
    for k, v in runtime_plan(config)['environment'].items():
        if v is None: env.pop(k, None)
        else: env[k] = v
    command = [rscript, '--vanilla', '--encoding=UTF-8', str(script), str(request)]
    with (attempt/'metadata-render.log').open('w', encoding='utf-8') as log:
        outcome = subprocess.run(command, cwd=attempt, env=env, stdout=log, stderr=subprocess.STDOUT)
    if outcome.returncode: raise ValueError('Metadata fragment rendering failed: ' + str(attempt))
    return {'command': command, 'exit_code': 0, 'files':
            {str(p): digest(p) for p in (script, request, output, attempt/'metadata-render.log')},
            'fragments': str(output)}


def verify_metadata_update(formal, process, topic):
    formal, process = Path(formal).resolve(), Path(process).resolve()
    path = process/METADATA_RECEIPT
    receipt = read(path)
    if receipt.get('status') != 'verified' or receipt.get('scope') != 'metadata_only':
        raise ValueError('Metadata receipt is not verified')
    baseline, folder, tree = metadata_inputs(formal, process, receipt)
    if str(topic).zfill(3) != baseline['topic_id']: raise ValueError('Metadata topic mismatch')
    if baseline['subscope'] == 'label_metadata':
        return verify_label_metadata(formal, process, topic, receipt, baseline, folder, tree)
    generation = receipt['generation']
    if generation['exit_code'] != 0: raise ValueError('Metadata generation did not pass')
    for name, signature in generation['files'].items():
        if digest(name) != signature: raise ValueError('Metadata generation evidence changed')
    fragments = read(generation['fragments'])
    patch = {'field': 'summary', 'before': fragments['before']['summary'], 'after': fragments['after']['summary']}
    expected = apply_fragment_patches((folder/baseline['artifacts']['note']).read_text(encoding='utf-8-sig'), [patch])
    note = formal/baseline['artifacts']['note']
    if expected != note.read_text(encoding='utf-8-sig'): raise ValueError('Note differs from exact generated tree fragment update')
    copy = (formal/'文案.md').read_text(encoding='utf-8-sig')
    expected_ids = re.findall(r'\[\[result:([A-Za-z][A-Za-z0-9_.]*)\|', copy)
    if re.findall(r'data-tree-variable="([^"]+)"', patch['after']) != expected_ids:
        raise ValueError('Generated tree identities differ from source')
    hashes = {p.name: digest(p) for p in formal.iterdir() if p.is_file()}
    if hashes != receipt['candidate_hashes']: raise ValueError('Metadata candidate changed after validation')
    return {'ok': True, 'status': 'METADATA_UPDATE_READY', 'scope': 'metadata_only',
        'subscope': 'tree_identity', 'topic_id': baseline['topic_id'], 'audit': str(path), 'audit_sha256': digest(path),
        'change_impact': {'path': METADATA_RECEIPT, 'sha256': digest(path), 'changed_dimensions': ['tree_identity']},
        'result_check': {'scope': 'metadata_only', 'status': 'EXACT_TREE_METADATA_PASS', 'tree': tree,
                         'historical_validation': 'PRESERVED_NOT_REVALIDATED'},
        'reader_review': {'status': 'UNCHANGED_TEXT_AND_EXPLICIT_IDENTITIES'},
        'questionnaire_rendering': {'status': 'PRESERVED_BY_EXACT_TRANSFORMATION'},
        'artifacts': {role: {'path': name, 'sha256': digest(formal/name)}
                      for role, name in baseline['artifacts'].items() if role != 'copy'},
        'validation_basis': 'Current tree identity delta verified; R, source and all tables byte-identical; historical research and calculations not revalidated'}


def metadata_run(args):
    formal, process = args.formal_dir.resolve(), args.process_dir.resolve()
    path = process/METADATA_RECEIPT
    receipt = read(path)
    baseline, folder, tree = metadata_inputs(formal, process, receipt, revalidate=True)
    attempt = folder/('metadata-attempt-' + str(uuid.uuid4()))
    attempt.mkdir()
    generation = (metadata_label_source(formal, folder, baseline, args.config, attempt)
                  if baseline['subscope'] == 'label_metadata'
                  else metadata_render(formal, folder, baseline, args.config, attempt))
    proposal = dict(receipt, status='verified', tools=metadata_tools(), generation=generation,
                    candidate_hashes={p.name: digest(p) for p in formal.iterdir() if p.is_file()})
    # Preserve every failed attempt; never fall back to running the full definition R.
    write(attempt/'proposed-receipt.json', proposal)
    write(path, proposal)
    try:
        result = verify_metadata_update(formal, process, baseline['topic_id'])
    except Exception as exc:
        write(path, dict(receipt, last_failure={'attempt': str(attempt), 'error': str(exc)}))
        raise
    write(attempt/'metadata-check.json', result)
    return result




def metadata_label_source(formal, folder, baseline, config_path, attempt):
    """Parse R, compare exact ASTs and materialize only verified literal metadata."""
    from skill_config import load_config, configured_executable
    from r_runtime import runtime_plan
    request, output = attempt/'label-source-input.json', attempt/'label-source-output.json'
    rname = baseline['artifacts']['public_r']
    from check_definition_output import read_xlsx_rows
    if 'analysis_codebook' in baseline['artifacts']:
        oldrows=read_xlsx_rows(folder/baseline['artifacts']['analysis_codebook'])
        old_labels={r[oldrows[0].index('Variable')]:r[oldrows[0].index('Label')] for r in oldrows[1:]}
    else: old_labels={}
    write(request, {'before': str(folder/rname), 'after': str(formal/rname),
                    'variables': baseline['analysis_vars'], 'old_labels': old_labels, 'output': str(output)})
    script = attempt/'label-source.R'
    script.write_text(r"""x <- jsonlite::read_json(commandArgs(TRUE)[1])
vars <- unlist(x$variables, use.names=FALSE)
refs <- attr(parse(x$before, keep.source=TRUE, encoding='UTF-8'),'srcref')
a <- parse(x$before, keep.source=FALSE, encoding='UTF-8')
b <- parse(x$after, keep.source=FALSE, encoding='UTF-8')
clean <- function(e) e
dp <- function(e) paste(deparse(e,width.cutoff=500),collapse=' ')
lines <- readLines(x$before,encoding='UTF-8',warn=FALSE)
start <- grep('^#{1,2} ([-]+|[0-9]+[.][0-9]+).*变量字典',lines); end <- grep('^# 输出$',lines)
if(length(start)!=1 || length(end)!=1 || start>=end) stop('No unique existing dictionary/backend boundary')
changes <- list(); groups <- list(); identities <- list()
literal <- function(e) {
 if(is.character(e) && length(e)==1) return(e)
 if(!is.call(e) || !identical(e[[1]],as.name('c'))) stop('Metadata value is not a literal vector')
 z <- as.list(e)[-1]; if(!length(z) || is.null(names(z)) || any(!nzchar(names(z))) || anyDuplicated(names(z))) stop('Invalid named metadata vector')
 vapply(z,label_value,character(1))
}
# Only these exact source-identity restorations inside the unchanged codebook builder are supported.
pairs <- list(
 c('original_vars_str','paste(name_z$Variable[match(original_vars_list, name_z$newname)], collapse = ", ")'),
 c('col','name_z$Variable[match(col, name_z$newname)]'))
restore <- function(u,v) {
 if(identical(clean(u),clean(v))) return(u)
 if(is.call(u)&&is.call(v)&&length(u)==3&&length(v)==3&&identical(u[[1]],as.name('<-'))&&identical(u[[2]],as.name('original_vars'))&&identical(u[[2]],v[[2]])) {
  for(pair in pairs) if(identical(clean(u[[3]]),parse(text=pair[1])[[1]])&&identical(clean(v[[3]]),parse(text=pair[2])[[1]])) {identities[[length(identities)+1]] <<- list(before=dp(u),after=dp(v));return(u)}
 }
 if(!is.call(u)||!is.call(v)||length(u)!=length(v)||!identical(names(u),names(v))) stop('R change outside approved dictionary identity restoration')
 for(j in seq_along(u)) { if(identical(u[[j]],quote(expr=))&&identical(v[[j]],quote(expr=))) next; v[j]<-list(restore(u[[j]],v[[j]])) };v
}

key_of <- function(e) {
 if(!is.call(e)||length(e)!=3||!identical(e[[1]],as.name('<-'))) return(NULL)
 lhs<-dp(e[[2]])
 if(!grepl('^codebook\\$Label\\[codebook\\$Variable == "[A-Za-z][A-Za-z0-9_.]*"\\]$',lhs)) return(NULL)
 sub('.*== "([^"]+)".*','\\1',lhs)
}
matched <- list(); ia<-1
for(j in seq_along(b)) {
 v<-b[[j]]
 same_target <- ia<=length(a) && is.call(a[[ia]]) && is.call(v) &&
   identical(a[[ia]][[1]],v[[1]]) &&
   (identical(a[[ia]][[1]],as.name('render_definition_bundle')) ||
    (identical(v[[1]],as.name('<-'))&&identical(a[[ia]][[2]],v[[2]])))
 if(ia<=length(a)&&(identical(a[[ia]],v)||same_target)) {
  matched[[length(matched)+1]]<-v;ia<-ia+1;next
 }
 k<-key_of(v)
 line<-if(ia<=length(a)) as.integer(refs[[ia]])[1] else Inf
 if(is.null(k)||!(k%in%vars)||is.null(x$old_labels[[k]])||!is.character(v[[3]])||length(v[[3]])!=1||!(line>start&&line<end)) stop('R expression insertion/removal outside literal dictionary override')
 changes[[length(changes)+1]]<-list(variable=k,before=x$old_labels[[k]],after=v[[3]],expression=paste0('insert-before-',ia))
}
if(ia!=length(a)+1) stop('R expressions removed')
b<-as.expression(matched)
unparen <- function(e) {
 if(is.call(e)&&identical(e[[1]],as.name('('))&&length(e)==2) return(unparen(e[[2]]))
 if(is.call(e)) { z<-as.list(e); for(j in seq_along(z)) if(!identical(z[[j]],quote(expr=))) z[j]<-list(unparen(z[[j]]));return(as.call(z)) };e
}
label_value <- function(e) {
 if(is.character(e)&&length(e)==1) return(e)
 if(is.call(e)&&identical(e[[1]],as.name('paste'))) {
  args<-as.list(e)[-1]
  if(length(args)&&all(vapply(args,function(z)is.character(z)&&length(z)==1,logical(1)))) return(do.call(paste,args))
 }
 stop('Label is not a literal string or existing literal paste')
}

for(i in seq_along(a)) {
 u<-clean(a[[i]]);v<-clean(b[[i]])
 if(identical(u,v)) next
 line<-as.integer(refs[[i]])[1]
 if(is.call(u)&&is.call(v)&&identical(u[[1]],as.name('render_definition_bundle'))&&identical(v[[1]],u[[1]])) {
  ul<-as.list(u);vl<-as.list(v)
  if('component_groups'%in%names(ul)||!('component_groups'%in%names(vl))||!('summary_groups'%in%names(ul))) stop('Only missing component_groups compatibility is allowed')
  g<-unparen(vl[['component_groups']]); sg<-unparen(ul[['summary_groups']])
  static_group <- identical(g, quote(setNames(rep("Defined variables", length(analysis_vars)), analysis_vars)))
  if(!identical(g,sg)&&!identical(g,substitute(z[analysis_vars],list(z=sg)))&&!static_group) stop('component_groups must equal existing groups or the verified static Defined variables group')
  vl[['component_groups']]<-NULL
  if(!identical(as.call(vl),u)) stop('Renderer arguments changed beyond component_groups')
  groups[[length(groups)+1]]<-list(expression=i,existing=dp(sg),added=dp(g),static_defined=static_group);next
 }
 if(!(line>start&&line<end)) stop(paste('R change outside existing dictionary region at expression',i))
 if(!is.call(u)||!is.call(v)||length(u)!=3||length(v)!=3||!identical(u[[1]],as.name('<-'))||!identical(u[[1]],v[[1]])||!identical(u[[2]],v[[2]])) stop('R metadata assignment target changed')
 lhs<-dp(u[[2]])
 if(lhs %in% c('labels','result_labels','item_labels','analysis_labels','label_map')) {
  old<-literal(u[[3]]);new<-literal(v[[3]])
  for(j in seq_along(as.list(u[[3]])[-1])) {
   ov<-u[[3]][[j+1]];nv<-v[[3]][[j+1]]
   if(!identical(ov,nv)&&is.call(nv)&&(!is.call(ov)||!identical(ov[[1]],nv[[1]])||length(ov)!=length(nv)||!identical(names(ov),names(nv)))) stop('New executable Label vector expression')
  }
  if(is.null(names(old))||!identical(names(old),names(new))||!all(names(old)[old!=new]%in%vars)) stop('Label vector identities changed')
  for(k in names(old)[old!=new]) changes[[length(changes)+1]]<-list(variable=k,before=unname(old[k]),after=unname(new[k]),expression=i)
 } else if(grepl('^codebook\\$Label\\[codebook\\$Variable == "[A-Za-z][A-Za-z0-9_.]*"\\]$',lhs)) {
  k<-sub('.*== "([^"]+)".*','\\1',lhs)
  if(!(k%in%vars)) stop('Label target is not an approved result')
  if(is.call(v[[3]]) && (!is.call(u[[3]]) || !identical(u[[3]][[1]],v[[3]][[1]]) || length(u[[3]])!=length(v[[3]]) || !identical(names(u[[3]]),names(v[[3]])))) stop('New executable Label expression')
  changes[[length(changes)+1]]<-list(variable=k,before=label_value(u[[3]]),after=label_value(v[[3]]),expression=i)
 } else if(lhs=='codebook' && grepl('lapply\\(names\\((data|db_data)\\), function\\(col\\)',dp(u[[3]]))) {
  matched<-restore(u[[3]],v[[3]])
  if(!identical(clean(matched),clean(u[[3]]))) stop('Dictionary identity restoration mismatch')
 } else stop(paste('Unapproved R change:',lhs))
}
if(!length(changes)) stop('No literal Label changes found')
if(anyDuplicated(vapply(changes,function(v)v$variable,character(1)))) stop('Ambiguous multiple changed Label assignments')
jsonlite::write_json(list(ok=TRUE,labels=changes,component_groups=groups,source_identity=identities),x$output,auto_unbox=TRUE,pretty=TRUE)
""", encoding='utf-8')
    config = load_config(config_path)
    rscript = configured_executable(config, 'rscript') or shutil.which('Rscript')
    if not rscript: raise ValueError('Rscript unavailable for AST comparison')
    env = dict(os.environ)
    for k,v in runtime_plan(config)['environment'].items():
        if v is None: env.pop(k,None)
        else: env[k]=v
    command = [rscript, '--vanilla', '--encoding=UTF-8', str(script), str(request)]
    with (attempt/'label-source.log').open('w',encoding='utf-8') as log:
        outcome = subprocess.run(command,cwd=attempt,env=env,stdout=log,stderr=subprocess.STDOUT)
    if outcome.returncode: raise ValueError('R metadata AST comparison failed: ' + str(attempt/'label-source.log'))
    return {'command':command,'exit_code':0,'metadata':str(output),
            'files':{str(q):digest(q) for q in (script,request,output,attempt/'label-source.log')}}


def metadata_verify_static_group(formal, baseline):
    from definition_order import Spans
    from check_definition_output import extract_category_pairs
    details = list(formal.glob('*_detail.html'))
    if len(details) != 1: raise ValueError('Static compatibility group requires unique original detail HTML')
    path = details[0]
    if baseline['before_hashes'].get(path.name) != digest(path): raise ValueError('Original grouping evidence changed')
    text = path.read_text(encoding='utf-8-sig')
    if extract_category_pairs(text) != [('', 'source'), ('', 'defined'), ('', 'source'), ('', 'defined')]:
        raise ValueError('Original detail is not the exact source/defined group layout')
    doc = Spans(text)
    nodes = list(doc.root.find(lambda n: n.tag == 'span' and 'var-name' in n.attrs.get('class','').split()))
    actual = []
    for node in nodes:
        parent = node.ancestor(lambda n: n.tag == 'details')
        v = node.attrs.get('id', '').removeprefix('var-')
        if parent and parent.attrs.get('id') == 'cat-Defined-variables': actual.append(v)
        elif v in baseline['analysis_vars']: raise ValueError('Result exists outside original Defined variables group')
    if actual != baseline['analysis_vars']: raise ValueError('Static group identities/order differ from original detail')


def verify_label_metadata(formal, process, topic, receipt, baseline, folder, tree):
    from check_definition_output import read_xlsx_rows, source_result_label_roles, extract_public_r_code
    from definition_order import replace_public_code
    generation = receipt['generation']
    if generation['exit_code'] != 0: raise ValueError('R metadata generation failed')
    for path, signature in generation['files'].items():
        if digest(path) != signature: raise ValueError('R metadata evidence changed')
    metadata = read(generation['metadata'])
    if metadata.get('ok') is not True: raise ValueError('R AST comparison did not pass')
    changes = {x['variable']:x for x in metadata['labels']}
    if any(g.get('static_defined') for g in metadata['component_groups']):
        metadata_verify_static_group(formal, baseline)
    art = baseline['artifacts']
    before_copy = (folder/art['copy']).read_text(encoding='utf-8-sig')
    if (formal/art['copy']).read_text(encoding='utf-8-sig') != before_copy:
        raise ValueError('Label metadata scope preserves source copy; use separate tree update')
    record = read(process/'definition_search_record.json')
    names = {v:set() for v in baseline['analysis_vars']}
    for v,label in baseline.get('static_display_names',{}).items():
        if v in names: names[v].add(label)
    for v,label in re.findall(r'\[\[result:([A-Za-z][A-Za-z0-9_.]*)\|([^]\r\n]+)\]\]',before_copy):
        if v in names: names[v].add(label)
    for row in record.get('definition_plan',[]):
        v = row.get('analysis_var')
        if v in names:
            names[v].update(row[k] for k in ('display_name','chinese_name','meaning') if isinstance(row.get(k),str))
    if len(baseline['analysis_vars']) == 1:
        from check_reader_copy import sections
        copy_sections = sections(before_copy, 2)
        summary = copy_sections.get('摘要导读', '')
        titles = re.findall(r'①[“\"]\*\*([^*\r\n]+)\*\*[”\"]', summary)
        criteria = sections(copy_sections.get('Criteria', ''), 3)
        v = baseline['analysis_vars'][0]
        if len(titles) == 1 and list(criteria) == [v] and re.search(r'定义\s*\*\*1\*\*\s*个变量', summary):
            names[v].add(titles[0])
    for v, change in changes.items():
        if change['after'] not in names.get(v,set()) or not re.search('[\u4e00-\u9fff]',change['after']):
            raise ValueError('New Label lacks confirmed Chinese identity evidence: '+v)
    with (formal/'raw_codebook.csv').open(encoding='utf-8-sig',newline='') as handle: raw=list(csv.DictReader(handle))
    raw_lookup={}
    for row in raw:
        alias=row.get('newname');identity=row.get('rawVariable') or row.get('Variable')
        if alias and identity:
            if alias in raw_lookup and raw_lookup[alias]!=identity: raise ValueError('Ambiguous raw identity: '+alias)
            raw_lookup[alias]=identity
    books={}
    observed_labels=set();observed_identity=[]
    for role in ('analysis_codebook','full_codebook'):
        old=read_xlsx_rows(folder/art[role]);new=read_xlsx_rows(formal/art[role]);books[role]=new
        if len(old)!=len(new) or old[0]!=new[0]: raise ValueError('Dictionary shape changed: '+role)
        header=old[0];vi=header.index('Variable');li=header.index('Label')
        for a,b in zip(old[1:],new[1:]):
            if len(a)!=len(b) or a[vi]!=b[vi]: raise ValueError('Dictionary variable/order changed')
            v=a[vi]
            for j,(av,bv) in enumerate(zip(a,b)):
                if av==bv: continue
                if header[j]=='Label' and v in changes and av==changes[v]['before'] and bv==changes[v]['after']:
                    # A same-name selected raw column retains its full source Label.
                    if role=='full_codebook' and v in raw_lookup: raise ValueError('Raw-source Label changed: '+v)
                    observed_labels.add((role,v));continue
                if header[j]=='original_vars' and metadata['source_identity']:
                    processed=b[header.index('processed_vars')]
                    aliases=str(processed).split(', ')
                    if not aliases or any(k not in raw_lookup for k in aliases): raise ValueError('Unknown raw mapping identity: '+v)
                    if str(bv)!=', '.join(raw_lookup[k] for k in aliases): raise ValueError('Source identity not restored from exact raw alias mapping: '+v)
                    if str(av)!=str(processed): raise ValueError('Source identity change was not an alias restoration: '+v)
                    observed_identity.append([role,v]);continue
                raise ValueError('Unexpected dictionary cell change: '+str((role,v,header[j],av,bv)))
    if {v for role,v in observed_labels if role=='analysis_codebook'} != set(changes):
        raise ValueError('Analysis dictionary changes differ from literal R metadata')
    roles=source_result_label_roles(formal,books['full_codebook'],books['analysis_codebook'],
                                   list(raw_lookup),baseline['analysis_vars'],record.get('definition_plan',[]))
    if bool(metadata['source_identity']) != bool(observed_identity): raise ValueError('R/source identity restoration is not reflected in dictionaries')
    old_r=folder/art['public_r'];new_r=formal/art['public_r']
    old_note=(folder/art['note']).read_text(encoding='utf-8-sig')
    a=old_r.read_text(encoding='utf-8-sig');b=new_r.read_text(encoding='utf-8-sig')
    pairs=[(a,b),(a.split('# 输出',1)[0].rstrip(),b.split('# 输出',1)[0].rstrip())]
    matches=[(u,v) for u,v in pairs if u in old_note]
    if not matches or any(old_note.count(u)!=1 for u,v in matches): raise ValueError('Public R fragment is not uniquely located')
    expected=replace_public_code(old_note,old_r,new_r)
    actual=(formal/art['note']).read_text(encoding='utf-8-sig')
    if actual!=expected: raise ValueError('Note changed outside the existing public R fragment')
    if extract_public_r_code(actual).strip() not in {b.strip(), b.split('# 输出',1)[0].strip()}:
        raise ValueError('Embedded public R differs from source')
    if {p.name:digest(p) for p in formal.iterdir() if p.is_file()} != receipt['candidate_hashes']:
        raise ValueError('Metadata candidate changed after validation')
    path=process/METADATA_RECEIPT
    return {'ok':True,'status':'METADATA_UPDATE_READY','scope':'metadata_only','subscope':'label_metadata',
        'topic_id':baseline['topic_id'],'audit':str(path),'audit_sha256':digest(path),
        'change_impact':{'path':METADATA_RECEIPT,'sha256':digest(path),'changed_dimensions':['result_label','public_r_metadata']},
        'result_check':{'scope':'metadata_only','status':'EXACT_LABEL_METADATA_PASS','labels':len(changes),
                        'source_identity_restorations':observed_identity,'source_result_label_roles':roles,
                        'historical_validation':'PRESERVED_NOT_REVALIDATED'},
        'reader_review':{'status':'UNCHANGED_PROSE_AND_CONFIRMED_LABELS'},
        'questionnaire_rendering':{'status':'PRESERVED_BY_EXACT_TRANSFORMATION'},
        'artifacts':{role:{'path':name,'sha256':digest(formal/name)} for role,name in art.items() if role!='copy'},
        'validation_basis':'Only verified R literal dictionary metadata, exact raw identity restoration and embedded public R changed; data and all other display content preserved; historical calculations not revalidated'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'run', 'retry', 'finish', 'periods'])
    parser.add_argument('--component-only', action='store_true', help='Retired generation entry; rejected without writing files')
    parser.add_argument('--retain-baseline', action='store_true',
                        help='Explicit exception: retain the comparison files required by this bounded update')
    parser.add_argument('--metadata-kind', choices=['tree_identity', 'label_metadata'], default='tree_identity')
    parser.add_argument('--r-script', help='Explicit formal R basename when helper R files coexist')
    parser.add_argument('--note', help='Explicit formal note basename when Markdown files are ambiguous')
    parser.add_argument('--metadata-only', action='store_true', help='Verify a bounded tree-identity or literal dictionary-metadata delta against the retained baseline')
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
    if args.command in ('prepare', 'retry', 'periods') and len(args.reason or '') < 20:
        parser.error('prepare/retry须说明具体修改或修复内容（至少20字）')
    if args.omit_questionnaire and len(args.omit_questionnaire) < 20:
        parser.error('请说明完整的问卷省略原因（至少20字）')
    try:
        if args.component_only:
            raise ValueError('component-only 整套隔离生成已退役；未写入文件，也未启动替代生成。请按本次实际改动使用公共生成接口；历史凭据仅按原范围核对。')
        if args.command in ('prepare', 'periods') and not args.retain_baseline:
            raise ValueError('常规修改直接更新源文件并生成当前成果；确需局部对照副本时才传 --retain-baseline。未写入文件。')
        if args.metadata_only:
            if args.command not in ('prepare', 'run', 'retry'):
                raise ValueError('metadata-only supports prepare/run/retry; publication uses scoped readability check')
            if args.path_map or args.legacy_report or args.omit_questionnaire:
                raise ValueError('metadata-only retains original historical evidence without rewriting it')
            command = metadata_prepare if args.command == 'prepare' else metadata_run
        else:
            command = {'prepare': prepare, 'run': run, 'retry': retry, 'finish': finish, 'periods': periods}[args.command]
        print(json.dumps(command(args), ensure_ascii=False))
    except (Exception, SystemExit) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

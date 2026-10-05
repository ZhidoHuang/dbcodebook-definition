#!/usr/bin/env python3
"""Prepare before editing; rebuild a copy-only change without new research/review.

No browser access, downloads, or publishing. Existing runner/checkers remain the
production path. A changed research input or calculation fails before generation.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import zipfile

import execution_report as er
from exploration_handoff import validate_exploration
from source_record_binding import research_record, SOURCE_SCOPE

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


def find_review(process, required):
    for path in reports(process):
        report = read(path)
        if er.COMBINED_REVIEW_ROLE in report.get("stage_reviews", {}):
            # A newer pending/failed/stale review must never fall back to an old pass.
            review = deepcopy(er.validate_stage_review(report, er.COMBINED_REVIEW_ROLE, required))
            agent = review.get("prior_agent_record") or next(
                a for a in report.get("reviews", []) if a["agent_id"] == review["agent_id"])
            review.update(prior_agent_record=agent, reused_from=str(path))
            return review
    raise ValueError("没有可沿用的独立 R 复核")


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
    for path in reports(process):
        prior = read(path)
        if prior.get("exploration_policy"):
            validate_exploration(prior, source)
            break
    else:
        raise ValueError("没有可沿用的探索方案")
    rfiles = [n for n in result["artifacts"] if n.lower().endswith('.r')]
    if len(rfiles) != 1:
        raise ValueError("须有唯一正式 R")
    review = find_review(process, [formal / rfiles[0], source, formal / 'raw_codebook.csv'])
    audit = read(process / 'readability_audit.json')
    if audit.get('unresolved_issues') or any(i.get('status') == 'open' for i in current.get('issues', [])):
        raise ValueError("现有问题尚未解决，不能作为纯文案更新")
    folder = process / 'copy_updates' / str(uuid.uuid4())
    folder.mkdir(parents=True)
    for name in result['artifacts']:
        if name.endswith('.xlsx') or name == '文案.md':
            shutil.copy2(formal / name, folder / name)
    shutil.copy2(source, folder / source.name)
    shutil.copy2(process / 'definition_change_impact.json', folder / 'definition_change_impact.json')
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
               'review': review, 'status': 'prepared'}
    report['copy_update'] = binding
    report['stage_reviews'] = {er.COMBINED_REVIEW_ROLE: review}
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
        if name != '文案.md' and digest(formal / name) != sha:
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
    impact.update(schema_version=3, change_summary=binding['reason'], changed_dimensions=['copy'])
    if args.omit_questionnaire:
        if '## 原始问卷' in (formal / '文案.md').read_text(encoding='utf-8-sig'):
            raise ValueError('正文仍有原始问卷，不能登记为全部省略')
        for question in source.get('questionnaire_evidence', []):
            question.update(display_required=False, display_omission_reason=args.omit_questionnaire,
                            rendered_in_copy=False, copy_locator='不展示：' + args.omit_questionnaire)
        write(source_path, source)
        impact.update(question_groups=[], question_groups_not_applicable_reason=args.omit_questionnaire)
    write(process / 'definition_change_impact.json', impact)
    stage = 'copy'
    try:
        call('check_reader_copy.py', '--copy', formal / '文案.md', '--record', source_path,
             '--process-dir', process, log=folder / 'copy-check.log')
        call('execution_report.py', 'stage-finish', '--process-dir', process, '--stage-id', stage,
             '--status', 'completed', '--copy', formal / '文案.md', '--summary', binding['reason'])
        stage = 'generate'
        call('execution_report.py', 'stage-start', '--process-dir', process, '--stage-id', stage,
             '--name', '重新生成并核对成果', '--role', '固定程序')
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
        with (folder / 'generate.log').open('w', encoding='utf-8') as log:
            outcome = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if outcome.returncode:
            raise ValueError('正式生成失败，见 ' + str(folder / 'generate.log'))
        for name in binding['result']['artifacts']:
            if not name.endswith('.xlsx'):
                continue
            same = workbook_content(formal / name) == workbook_content(folder / name)
            if (name.startswith('db_') or name.startswith('analysis_db_')) and not same:
                raise ValueError('纯文案修改产生数据变化：' + name)
            if same:
                shutil.copy2(folder / name, formal / name)
        old = binding['result']
        columns = next(c['detail'] for c in old['checks'] if c['check'] == 'analysis_db columns')
        art = binding['audit_artifacts']
        raw = list(dict.fromkeys(v for group in source['source_groups'] for v in group['raw_variables']))
        params = ['--complete', '--db', source['database'].lower(), '--formal-dir', formal,
                  '--process-dir', process, '--expected-files', ','.join(n for n in old['artifacts'] if not n.endswith('.log')),
                  '--raw-vars', ','.join(raw), '--analysis-db', art['analysis_db']['path'],
                  '--analysis-codebook', art['analysis_codebook']['path'], '--analysis-columns', ','.join(columns),
                  '--analysis-vars', ','.join(old['analysis_vars']), '--check-summary-facts',
                  '--require-log-exit-code', '--log-prefix', prefix, '--report', process / 'result_check.json']
        if source.get('language'):
            params += ['--language', source['language']]
        call('check_definition_output.py', *params, log=folder / 'result-check.log')
        preserve = ['--preserve-reader'] if (process / 'reader_comprehension_review.json').exists() else []
        call('check_definition_readability.py', 'init', '--formal-dir', formal, '--process-dir', process,
             '--topic-id', report['topic_id'], '--note', art['note']['path'], '--r-script', binding['r_script'],
             '--analysis-db', art['analysis_db']['path'], '--analysis-codebook', art['analysis_codebook']['path'],
             '--overwrite', *preserve, log=folder / 'delivery-init.log')
        call('check_definition_readability.py', 'check', '--formal-dir', formal, '--process-dir', process,
             '--topic-id', report['topic_id'], log=folder / 'delivery-check.log')
        call('execution_report.py', 'stage-finish', '--process-dir', process, '--stage-id', stage,
             '--status', 'completed', '--summary', '当前成果检查通过；未变的数据及附件沿用原文件。')
        report = read(process / er.REPORT_NAME)
        report['copy_update']['status'] = 'completed'
        er.save(*er.paths(process), report)
        call('execution_report.py', 'finish', '--process-dir', process, '--status', 'completed',
             '--summary', '局部文案已生成并验证；尚未同步网站。')
        return {'ok': True, 'status': 'LOCAL_UPDATE_COMPLETE', 'website_submitted': False}
    except (Exception, SystemExit) as exc:
        call('execution_report.py', 'stage-finish', '--process-dir', process, '--stage-id', stage,
             '--status', 'failed', '--summary', str(exc))
        call('execution_report.py', 'issue', '--process-dir', process, '--stage-id', stage,
             '--kind', 'abnormal', '--description', str(exc), '--status', 'open')
        report = read(process / er.REPORT_NAME)
        report['copy_update']['status'] = 'failed'
        er.save(*er.paths(process), report)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'run'])
    parser.add_argument('--formal-dir', type=Path, required=True)
    parser.add_argument('--process-dir', type=Path, required=True)
    parser.add_argument('--reason', help='本次纯表达或展示修改；至少20字')
    parser.add_argument('--omit-questionnaire', help='已删除整节问卷时，给出明确的省略原因（至少20字）')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--pwsh')
    args = parser.parse_args()
    if args.command == 'prepare' and len(args.reason or '') < 20:
        parser.error('prepare须说明具体修改范围（至少20字）')
    if args.omit_questionnaire and len(args.omit_questionnaire) < 20:
        parser.error('请说明完整的问卷省略原因（至少20字）')
    try:
        print(json.dumps(prepare(args) if args.command == 'prepare' else run(args), ensure_ascii=False))
    except (Exception, SystemExit) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

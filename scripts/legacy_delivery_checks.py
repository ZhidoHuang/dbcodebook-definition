"""Read-only verification of retained delivery receipts. No generation or repair commands.

Recorded tool versions identify the historical run. Current validators check
the retained artifacts, source, scope and evidence without recreating its runtime.
Historical acceptance is not a new calculation or research review.
"""
import csv
import hashlib
import json
import re
from pathlib import Path
TEXT_SECTIONS = ('摘要导读', '小book提示', '参考资料说明')
TEXT_FIELDS = ('summary', 'summary_blocks', 'insight', 'references')
METADATA_RECEIPT = 'definition_metadata_update.json'


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


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
    """Recognize a retained full-check result, not a current checker execution."""
    return (record.get('ok') is True and record.get('scope') == 'complete'
            and record.get('status') == 'MACHINE_CHECK_PASS' and record.get('checks')
            and all(item.get('ok') is True for item in record['checks'])
            and re.fullmatch(r'[0-9A-Fa-f]{64}', record.get('checker_sha256', '')) is not None)


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


def metadata_inputs(formal, process, receipt):
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

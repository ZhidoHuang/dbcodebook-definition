"""NHIS regular-dataset identity and unique-person export contract."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlsplit

DATASETS = {
    'nhis_pre1997': [*(f'{y}FY' for y in range(1963, 1968)), '1968FY', '1968CY', *(str(y) for y in range(1969, 1997))],
    'nhis_1997_2018': [str(y) for y in range(1997, 2019)],
    'nhis_2019_plus': [str(y) for y in range(2019, 2026)],
}
DEFAULTS = ('ID', 'Wave_id', 'Survey_year')
OPTIONAL_DEFAULTS = ('Record_id', 'Baseline_year', 'Imputation_number')
KIND = 'nhis_identity_selection_v1'
PUBLICATION_CATEGORIES = {
    'nhis_pre1997': 'NHIS 1996年及以前',
    'nhis_1997_2018': 'NHIS 1997—2018',
    'nhis_2019_plus': 'NHIS 2019年及以后',
}


def publication_category(dataset_id):
    return PUBLICATION_CATEGORIES[require_dataset(dataset_id)]


def require_dataset(value):
    if value not in DATASETS:
        raise ValueError('NHIS requires one explicit supported dataset_id')
    return value


def page_url(base, dataset_id):
    require_dataset(dataset_id)
    root = str(base).rstrip('/')
    parsed = urlsplit(root)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.path not in {'', '/'}:
        raise ValueError('NHIS base URL must be an http(s) origin')
    return root + '/home/nhis/' + dataset_id + '/'


def require_context(record, dataset_id=None):
    chosen = require_dataset(record.get('dataset_id'))
    if str(record.get('database', '')).lower() != 'nhis' or (dataset_id is not None and dataset_id != chosen):
        raise ValueError('NHIS record and requested dataset differ')
    return chosen


def validate_selection(action):
    ds = require_dataset(action.get('dataset_id'))
    parsed = urlsplit(action.get('url', ''))
    if parsed.path != '/home/nhis/' + ds + '/' or parsed.scheme not in {'http', 'https'}:
        raise ValueError('NHIS action URL and dataset_id differ')
    if action.get('kind') != KIND or action.get('database') != 'nhis':
        raise ValueError('Invalid NHIS selection kind')
    if not re.fullmatch(r'[a-f0-9]{64}', str(action.get('dictionary_sha256', ''))):
        raise ValueError('NHIS selection needs the current dictionary SHA256')
    rows = action.get('selected')
    if not isinstance(rows, list) or not rows:
        raise ValueError('NHIS selection is empty')
    ids, aliases = set(), set()
    for row in rows:
        for name in ('variable_id', 'variable', 'file', 'alias'):
            if not isinstance(row.get(name), str) or not row[name].strip():
                raise ValueError('NHIS selection needs ' + name)
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', row['alias']) or row['alias'] in (*DEFAULTS, *OPTIONAL_DEFAULTS):
            raise ValueError('Invalid or reserved NHIS source alias')
        if row['variable_id'] in ids or row['alias'] in aliases:
            raise ValueError('Duplicate NHIS identity or alias')
        periods = row.get('periods')
        if not isinstance(periods, list) or not periods or any(not isinstance(p, str) or not p for p in periods) or len(periods) != len(set(periods)):
            raise ValueError('NHIS source needs explicit distinct dictionary periods')
        mappings = row.get('source_mappings')
        if not isinstance(mappings, list) or not mappings:
            raise ValueError('NHIS selection needs exact source mappings')
        for mapping in mappings:
            required = ('调查期间', '来源文件标识', '原变量名', '合并文件', '合并变量名', 'Variable_id', '编码版本')
            if any(k not in mapping or mapping[k] is None for k in required) or mapping['Variable_id'] != row['variable_id']:
                raise ValueError('NHIS source mapping is incomplete or belongs to another identity')
            if mapping.get('hrs_style_id_type') != '唯一个人ID':
                raise ValueError('This NHIS adapter supports only verified unique-person sources')
        export_periods = {str(m['调查期间']) for m in mappings}
        dictionary_periods = {p[:-2] if ds == 'nhis_pre1997' and re.fullmatch(r'196[3-7]FY', p) else p for p in export_periods}
        if not set(periods).issubset(dictionary_periods):
            raise ValueError('NHIS dictionary periods are not supported by exact source mappings')
        ids.add(row['variable_id']); aliases.add(row['alias'])
    if action.get('aliases') != [row['alias'] for row in rows]:
        raise ValueError('NHIS aliases and selected identities differ')
    if action.get('input_text') != selection_text(rows):
        raise ValueError('NHIS bulk input differs from the exact identity selection')
    return action


def selection_text(rows):
    return '\n'.join(f"{r['variable']} ({r['file']}) [{r['variable_id']}]={r['alias']}" for r in rows)


def build_selection(record, url):
    ds = require_context(record)
    if record.get('status') != 'READY':
        raise ValueError('NHIS selection requires the primary READY record')
    spec = record.get('nhis_selection') or {}
    action = {'kind': KIND, 'database': 'nhis', 'dataset_id': ds, 'url': url,
              'dictionary_sha256': spec.get('dictionary_sha256'), 'selected': spec.get('inputs', []),
              'aliases': [r.get('alias') for r in spec.get('inputs', [])],
              'input_text': selection_text(spec.get('inputs', []))}
    validate_selection(action)
    by_alias = {r['alias']: r for r in action['selected']}
    used = set()
    for group in record.get('source_groups', []):
        names, aliases = group.get('source_identities', []), group.get('raw_variables', [])
        if not names or len(names) != len(aliases):
            raise ValueError('NHIS groups need positional full identities and aliases')
        covered = set()
        for name, alias in zip(names, aliases):
            item = by_alias.get(alias)
            if not item or name != f"{item['variable']} ({item['file']})":
                raise ValueError('NHIS source group differs from exact selection')
            used.add(alias)
            covered.update(item['periods'])
        if not set(group.get('periods') or []).issubset(covered):
            raise ValueError('NHIS source group periods differ from exact selection')
    if used != set(by_alias):
        raise ValueError('NHIS exact selection and source groups differ')
    return action


def validate_package(directory, members, expected, dataset_id, selection=None):
    require_dataset(dataset_id)
    directory = Path(directory)
    raws = {n for n in members if n.startswith('raw_data') and n.endswith('.csv')}
    if raws != {'raw_data.csv'}:
        raise ValueError('NHIS unique-person adapter requires the original raw_data.csv only')
    if not expected or len(expected) != len(set(expected)) or set(expected).intersection((*DEFAULTS, *OPTIONAL_DEFAULTS)):
        raise ValueError('NHIS business aliases must be unique and exclude default keys')
    with (directory/'raw_codebook.csv').open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['Variable', 'Label', 'newname']:
            raise ValueError('NHIS raw_codebook header differs from the website contract')
        dictionary = list(reader)
    if len(dictionary) != len(expected) or {r['newname'] for r in dictionary} != set(expected):
        raise ValueError('NHIS dictionary does not match selected aliases')
    by_alias = {r['newname']: r for r in dictionary}
    allowed_periods = set(DATASETS[dataset_id])
    if selection is not None:
        validate_selection(selection)
        if selection['dataset_id'] != dataset_id or selection['aliases'] != list(expected):
            raise ValueError('NHIS package and selection context differ')
        allowed_periods = set()
        for item in selection['selected']:
            if by_alias[item['alias']]['Variable'] != f"{item['variable']} ({item['file']})":
                raise ValueError('NHIS exported source identity differs from selected Variable_id evidence')
            allowed_periods.update(m['调查期间'] for m in item['source_mappings'])
    with (directory/'raw_data.csv').open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        if len(set(header)) != len(header) or not set(DEFAULTS).issubset(header) or set(header) != set(expected) | (set(header) & set((*DEFAULTS, *OPTIONAL_DEFAULTS))):
            raise ValueError('NHIS raw header differs from business aliases plus default columns')
        seen, periods, count = set(), set(), 0
        for number, row in enumerate(reader, 2):
            if None in row or any(v is None for v in row.values()) or any(not row[k].strip() for k in DEFAULTS):
                raise ValueError(f'Malformed NHIS identity/CSV at row {number}')
            if row['ID'] in seen:
                raise ValueError(f'Duplicate NHIS person identity at row {number}')
            if row['Wave_id'] not in allowed_periods:
                raise ValueError(f'NHIS period outside selected dataset/source mappings: {row["Wave_id"]}')
            if not re.fullmatch(r'\d{4}', row['Survey_year']) or row['Survey_year'] != row['Wave_id'][:4]:
                raise ValueError(f'NHIS Survey_year and source period disagree at row {number}')
            seen.add(row['ID']); periods.add(row['Wave_id']); count += 1
    if not count:
        raise ValueError('NHIS raw contains no personal records')
    return {'files': {'raw_data.csv': {'header': header, 'rows': count, 'data_vars': list(expected),
             'identity_columns': [k for k in (*DEFAULTS, *OPTIONAL_DEFAULTS) if k in header],
             'observed_periods': sorted(periods)}}, 'dictionary_rows': len(dictionary),
            'dataset_id': dataset_id, 'source_identity_check': 'selected_manifest' if selection else 'aliases_only'}

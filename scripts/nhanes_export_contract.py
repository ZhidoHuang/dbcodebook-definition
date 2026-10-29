"""Validate ordinary NHANES records and explicit person-level repeated files."""
import csv
import io
import json
import re
import zipfile
from collections import OrderedDict
from pathlib import Path

IDENTIFIERS = ('SEQN', 'YEAR')
SOURCE_TYPE = '常规(唯一SEQN)'
REPEATED_SOURCES = frozenset(('PAQIAF', 'RXQ_RX'))
SUPPORTED_SOURCES = REPEATED_SOURCES | {SOURCE_TYPE}
MEDICINE_LISTS = {'multum': ('inVariables', 'nVariables', 'iVariables'),
                  'icd': ('icdVariables',), 'drugnames': ('dnVariables',)}
DOCUMENT_PERIODS = {
    'PAQIAF': {'PAQIAF':'1999-2000', 'PAQIAF_B':'2001-2002', 'PAQIAF_C':'2003-2004', 'PAQIAF_D':'2005-2006'},
    'RXQ_RX': {**{('RXQ_RX' if index == 0 else 'RXQ_RX_' + chr(65 + index)):f'{1999+2*index}-{2000+2*index}' for index in range(10)}, 'P_RXQ_RX':'2017-2020'},
}


def document_period(source, document):
    """Use verified release filenames; never infer cycles from participant IDs."""
    stem = re.sub(r'(?i)\.xpt$', '', document.strip()).upper()
    period = DOCUMENT_PERIODS.get(source, {}).get(stem)
    if period is None:
        raise ValueError('No verified NHANES cycle mapping for ' + document)
    return period


def require_source_types(rows):
    for row in rows:
        match = re.fullmatch(r'([^()\s]+)\s+\((.+)\)', row['identity'])
        if not match or match[2] not in SUPPORTED_SOURCES:
            raise ValueError('Unsupported NHANES source: ' + row['identity'])


def _source(row):
    variable = row['Variable'].strip()
    match = re.fullmatch(r'([^()\s]+)\s+\((.+)\)', variable)
    if match:
        variable, source = match.groups()
    else:
        source = SOURCE_TYPE
    if not variable or source not in SUPPORTED_SOURCES:
        raise ValueError('NHANES source identity is unsupported: ' + row['Variable'])
    expected_type = 'uniqID' if source == SOURCE_TYPE else 'reID'
    if row['File type'] != expected_type:
        raise ValueError('NHANES dictionary File type differs from its source identity')
    return source


def _identity(row, number, period=None):
    person, period = row['SEQN'], period or row['YEAR']
    if not re.fullmatch(r'[0-9]+(?:\.0+)?', person or '') or not re.fullmatch(r'[0-9]{4}-[0-9]{4}', period or ''):
        raise ValueError(f'Invalid NHANES identity at CSV row {number}')
    start, end = map(int, period.split('-'))
    if start >= end:
        raise ValueError(f'Invalid NHANES period at CSV row {number}')
    return (re.sub(r'\.0+$', '', person).lstrip('0') or '0', period)


def validate_package(root, members, aliases):
    root = Path(root)
    defaults = {'SEQN', 'YEAR', 'DOC_FILE', 'RowIndex'}
    if len(set(aliases)) != len(aliases) or set(aliases) & defaults:
        raise ValueError('NHANES aliases must be unique and exclude default identities')
    with (root / 'raw_codebook.csv').open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not {'Variable', 'File type', 'newname'}.issubset(reader.fieldnames or []):
            raise ValueError('NHANES dictionary fields missing')
        rows = list(reader)
    if len(rows) != len(aliases) or {r['newname'] for r in rows} != set(aliases):
        raise ValueError('NHANES dictionary aliases differ from selected sources')
    groups = OrderedDict()
    for row in rows:
        groups.setdefault(_source(row), []).append(row['newname'])
    expected = {('raw_data.csv' if source == SOURCE_TYPE else f'raw_data_{source}.csv'):source for source in groups}
    if len(members) != len(expected) or set(members) != set(expected):
        raise ValueError('NHANES data files differ from selected source types')
    facts = {}
    for filename, source in expected.items():
        repeated = source != SOURCE_TYPE
        prefix = ['RowIndex', 'DOC_FILE', 'SEQN'] if repeated else list(IDENTIFIERS)
        keys, periods, documents, total = set(), set(), set(), 0
        with (root / filename).open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            has_year = 'YEAR' in header
            if repeated and has_year:
                prefix.append('YEAR')
            if header != prefix + groups[source]:
                raise ValueError('NHANES identity or selected columns differ in ' + filename)
            for number, row in enumerate(reader, 2):
                if repeated:
                    if row['RowIndex'] != str(number-1) or not row['DOC_FILE'].strip():
                        raise ValueError(f'Invalid repeated-file provenance at {filename}:{number}')
                    documents.add(row['DOC_FILE'])
                    mapped = document_period(source, row['DOC_FILE'])
                    if has_year and row['YEAR'] != mapped:
                        raise ValueError(f'Conflicting YEAR and DOC_FILE at {filename}:{number}')
                    period = row['YEAR'] if has_year else mapped
                else:
                    period = row['YEAR']
                key = _identity(row, number, period)
                if not repeated and key in keys:
                    raise ValueError(f'Duplicate NHANES person-period at CSV row {number}')
                keys.add(key)
                periods.add(period)
                total += 1
        if not total:
            raise ValueError('NHANES export contains no rows in ' + filename)
        facts[filename] = {'rows':total, 'keys':list(IDENTIFIERS) if has_year else ['SEQN','DOC_FILE'], 'periods':sorted(periods), 'header':header}
        if repeated:
            facts[filename].update(source_type=source, record_unit='repeated_person_records',
                person_periods=len(keys), repeated_rows=total-len(keys), provenance_columns=['RowIndex','DOC_FILE'],
                source_documents=sorted(documents))
            if not has_year:
                facts[filename].update(aggregation_keys=list(IDENTIFIERS),
                    period_derivation='DOC_FILE verified release mapping; raw CSV unchanged',
                    document_periods={d:document_period(source,d) for d in sorted(documents)})
    if list(facts) == ['raw_data.csv']:
        return facts['raw_data.csv']
    return {'files':facts}


def build_medicine_download_action(base_url, attempt_id, attempt_file, variables):
    """Use the existing bound-tab download receiver for the separate medicine UI."""
    from urllib.parse import urlsplit
    origin = base_url.rstrip('/')
    if urlsplit(origin).scheme not in {'http', 'https'} or not urlsplit(origin).netloc:
        raise ValueError('Medicine export requires an absolute website URL')
    if not variables or len({v['variable'] for v in variables}) != len(variables):
        raise ValueError('Medicine variables must be nonempty and unique')
    for item in variables:
        if item.get('list_id') not in sum(MEDICINE_LISTS.values(), ()) or not item.get('selected_values'):
            raise ValueError('Medicine source needs its observed list and selected values')
    url = origin + '/home/medicine/'
    script = '''
if (page.url().split('?')[0] !== EXPECTED_URL) throw new Error('Not the medicine export page');
const specs = EXPECTED_SPECS;
const actual = await page.locator('.stored-variable-item').evaluateAll(es => es.map(e => ({
  variable:e.getAttribute('data-variable-name'), list_id:e.parentElement.id,
  selected_values:JSON.parse(e.getAttribute('data-match-values'))
})));
const normalize = rows => JSON.stringify(rows.map(r=>({...r,selected_values:[...r.selected_values].sort()})).sort((a,b)=>a.variable.localeCompare(b.variable)));
if (normalize(actual) !== normalize(specs)) throw new Error('Medicine selection differs from confirmed specification');
const receiver = downloadCapture(page, downloadAttemptId, downloadTarget);
const responsePromise = page.waitForResponse(r => r.url().split('?')[0] === EXPECTED_URL + 'download_all/' && r.request().method() === 'POST', {timeout:20000});
dbCodeBookMarkDownloadClickRequested();
await page.getByRole('button', {name:'下载变量',exact:true}).click();
try {
  const response = await responsePromise;
  if (!response.ok() || (response.headers()['content-type'] || '').includes('application/json')) {
    receiver.reject(await response.text());
  }
} catch (error) { /* Unknown response: observe the same download, never reclick. */ }
actionResult = await observeDownload(page, downloadAttemptId);
'''.replace('EXPECTED_URL', json.dumps(url)).replace('EXPECTED_SPECS', json.dumps(variables, ensure_ascii=False))
    return {'database':'nhanes', 'source_kind':'medicine', 'url':url,
            'attempt_id':attempt_id, 'attempt_file':str(Path(attempt_file).resolve()),
            'variables':variables, 'run_script':script, 'timeout_ms':45000}


def validate_medicine_package(archive, variables):
    """Check the original special export, including its SEQN-only join contract."""
    names = [v['variable'] for v in variables]
    if not names or len(set(names)) != len(names):
        raise ValueError('Medicine specification must contain unique variables')
    with zipfile.ZipFile(archive) as package:
        if set(package.namelist()) != {'raw_drug.csv','raw_drug_detail.txt'}:
            raise ValueError('Unexpected medicine export members')
        detail = package.read('raw_drug_detail.txt').decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(package.read('raw_drug.csv').decode('utf-8-sig')))
        if reader.fieldnames != ['SEQN', *names]:
            raise ValueError('Medicine export columns differ from selected variables')
        persons, total = set(), 0
        for number, row in enumerate(reader, 2):
            person = row['SEQN']
            if not re.fullmatch(r'[0-9]+(?:\.0+)?', person or ''):
                raise ValueError(f'Invalid medicine SEQN at row {number}')
            key = re.sub(r'\.0+$', '', person).lstrip('0') or '0'
            if key in persons:
                raise ValueError(f'Duplicate medicine SEQN at row {number}')
            if any(row[name] not in {'0','1','0.0','1.0'} for name in names):
                raise ValueError(f'Nonbinary medicine flag at row {number}')
            persons.add(key)
            total += 1
    if not total:
        raise ValueError('Medicine export is empty')
    blocks = re.split(r'(?m)^变量名[:：]\s*', detail)[1:]
    records = {block.splitlines()[0].strip():block for block in blocks}
    if set(records) != set(names):
        raise ValueError('Medicine detail names differ from CSV')
    for item in variables:
        block = records[item['variable']]
        if any(value not in block for value in item['selected_values']):
            raise ValueError('Medicine detail omits the selected source category')
    return {'rows':total, 'keys':['SEQN'], 'header':['SEQN',*names],
            'source_kind':'medicine', 'detail_file':'raw_drug_detail.txt'}


def medicine_source_columns(formal, record):
    """Verify the separate original package before admitting its used output columns."""
    export = record.get('medicine_export')
    if not export:
        return []
    formal = Path(formal)
    archive = formal / 'bookapp_medicine_download.zip'
    facts = validate_medicine_package(archive, export['variables'])
    with zipfile.ZipFile(archive) as package:
        for filename in ('raw_drug.csv','raw_drug_detail.txt'):
            if (formal / filename).read_bytes() != package.read(filename):
                raise ValueError('Medicine file differs from original archive: ' + filename)
    used = export.get('used_fields', [])
    if (not used or len(set(used)) != len(used) or
            not set(used) <= set(facts['header']) - {'SEQN'}):
        raise ValueError('Invalid medicine used_fields')
    return used

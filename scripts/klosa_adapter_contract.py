"""KLoSA raw export contract, verified against website source; no raw acquisition."""
import csv
import re
from pathlib import Path
from urllib.parse import urlsplit

LANGUAGES = {'en': 9, 'ko': 10}
IDENTIFIERS = ['ID', 'Harmonized_id', 'Wave_id']
REPEAT_MEMBER = 'raw_data_KLoSA_Imputation.csv'
REPEAT_IDENTIFIERS = ['RowIndex', *IDENTIFIERS, 'v_imputation_']
FILES = {'KLoSA_Core', 'KLoSA_Exit', 'KLoSA_str', 'KLoSA_Lt', 'KLoSA_Imputation'}
DICT_HEADER = ['Easy label', 'Base_Variable', 'Wave', 'Variable', 'File type', 'newname']

def language(value):
    if value not in LANGUAGES:
        raise ValueError('KLoSA requires explicit language=en or ko')
    return value

def page_url(base_url, value):
    language(value)
    base = base_url.strip().rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
        raise ValueError('KLoSA base_url must be an absolute origin')
    return f'{base}/home/klosa/{value}/'

def require_context(document, value, url=None):
    language(value)
    if str(document.get('database', '')).lower() != 'klosa' or document.get('language') != value:
        raise ValueError('KLoSA database/language changed or missing')
    if url is not None and document.get('url', document.get('existing_tab_path')) != url:
        raise ValueError('KLoSA route changed or missing')

def require_wave_source_identities(action, value):
    """Require actual period fields, avoiding UI Base_Variable alias expansion."""
    require_context(action, value, action['url'])
    for line in action['input_text'].splitlines():
        match = re.fullmatch(r'(w(\d{2})[^\s()]*)\s+\(([^()]+)\)=([^\r\n=]+)', line)
        if not match or match[3] not in FILES or not 1 <= int(match[2]) <= LANGUAGES[value]:
            raise ValueError('KLoSA selection requires evidence-resolved wave Variable (File)=alias; never infer it from Base_Variable')

def _rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        if not header or len(header) != len(set(header)):
            raise ValueError('empty or duplicate CSV header')
        rows = list(reader)
        if any(None in r or any(v is None for v in r.values()) for r in rows):
            raise ValueError('ragged CSV row')
        return header, rows

def _wave(value, lang):
    # Actual source tests use integer Wave_id; textual equivalent remains strict.
    match = re.fullmatch(r'(?:Wave )?([1-9]|10)', value)
    if not match or int(match[1]) > LANGUAGES[lang]:
        raise ValueError('Wave_id outside declared language coverage')
    return int(match[1])

def validate_package(staging, members, expected, lang):
    language(lang)
    staging = Path(staging)
    expected = list(expected)
    if not expected or len(set(expected)) != len(expected):
        raise ValueError('expected aliases must be nonempty and unique')
    if not members or len(set(members)) != len(members) or set(members) - {'raw_data.csv', REPEAT_MEMBER}:
        raise ValueError('unexpected or duplicate KLoSA raw members')
    header, dictionary = _rows(staging/'raw_codebook.csv')
    if header != DICT_HEADER:
        raise ValueError('KLoSA dictionary header differs from website contract')
    aliases, owners = [], {}
    for row in dictionary:
        alias = row['newname']; source = re.fullmatch(r'(.+) \(([^()]+)\)', row['Variable'])
        if not source or source[2] not in FILES or not row['Base_Variable'] or not alias:
            raise ValueError('dictionary source identity or alias missing')
        waves = row['Wave'].split(', ')
        if any(not re.fullmatch(r'Wave ([1-9]|10)', x) for x in waves):
            raise ValueError('dictionary Wave must use website Wave N labels')
        for wave in waves:_wave(wave, lang)
        repeated = source[2] == 'KLoSA_Imputation'
        if row['File type'] != ('reID' if repeated else 'uniqID'):
            raise ValueError('dictionary file classification mismatch')
        aliases.append(alias); owners[alias] = REPEAT_MEMBER if repeated else 'raw_data.csv'
    if len(aliases) != len(set(aliases)) or set(aliases) != set(expected):
        raise ValueError('dictionary aliases differ from approved selection')
    seen, reports, id_metadata = set(), {}, {}
    for member in members:
        repeated = member == REPEAT_MEMBER
        identities = REPEAT_IDENTIFIERS if repeated else IDENTIFIERS
        header, rows = _rows(staging/member)
        if header[:len(identities)] != identities:
            raise ValueError('KLoSA identity prefix differs from website contract')
        variables = header[len(identities):]
        if not variables or any(v not in owners or owners[v] != member for v in variables):
            raise ValueError('raw alias absent from dictionary or assigned to wrong member')
        seen.update(variables)
        row_keys, ids, person_waves = set(), set(), set()
        for row in rows:
            if any(not row[x] or row[x].strip() != row[x] for x in identities):
                raise ValueError('blank or whitespace identity')
            wave = _wave(row['Wave_id'], lang)
            meta = (row['Harmonized_id'], wave)
            if row['ID'] in id_metadata and id_metadata[row['ID']] != meta:
                raise ValueError('same ID has conflicting person/wave metadata')
            id_metadata[row['ID']] = meta
            key = (row['ID'], row['v_imputation_']) if repeated else row['ID']
            if key in row_keys or (not repeated and (row['ID'] in ids or meta in person_waves)):
                raise ValueError('ordinary ID/person-wave or imputation draw key duplicated')
            row_keys.add(key); ids.add(row['ID']); person_waves.add(meta)
        if repeated and (len({r['RowIndex'] for r in rows}) != len(rows) or any(not r['RowIndex'].isdigit() or int(r['RowIndex']) < 1 for r in rows)):
            raise ValueError('RowIndex must remain unique positive values')
        reports[member] = {'header':header, 'rows':len(rows), 'cols':len(header), 'identity_columns':identities, 'data_vars':variables}
    if seen != set(expected):
        raise ValueError('raw members do not cover dictionary aliases exactly')
    return {'codebook':{'rows':len(dictionary),'aliases':aliases}, 'data':reports, 'database':'klosa', 'language':lang}

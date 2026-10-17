"""MHAS Core respondent exports; other products need their own reviewed contract."""
import csv
import re
from itertools import product
from pathlib import Path

CORE = 'MHAS_SURVEY_CORE_RESPONDENT'
RAW_NAME = 'raw_data_' + CORE + '.csv'
PERIODS = ('2001', '2003', '2012', '2015', '2018', '2021', '2024')
IDENTIFIERS = {'ID', 'Wave_id', 'UNHHIDNP', 'CUNICAH', 'NP', 'cunicah', 'np',
               'unhhid', 'ps3', 'acthog', 'ent2', 'codent01', 'codent03',
               'source_file', 'source_row'}
PERSON_SHAPES = [('unhhidnp',), ('cunicah', 'np'), ('unhhid', 'np'),
                 ('cunicah', 'acthog', 'ent2'), ('cunicah', 'ent2'), ('unhhid', 'ps3'),
                 ('cunicah', 'acthog', 'codent03'), ('cunicah', 'codent01')]


def identity_matches(row):
    def value(name):
        text = str(row.get(name) or '').strip()
        return re.sub(r'(?<=\d)\.0$', '', text)
    for shape in PERSON_SHAPES:
        choices = [[k for k in row if k.casefold() == part] for part in shape]
        for columns in product(*choices):
            parts = [value(k) for k in columns]
            if all(parts) and row['ID'] == '|'.join([row['Wave_id'], *parts]):
                return True
    return False


def primary_raw(directory):
    return Path(directory) / RAW_NAME


def validate_package(directory, members, expected):
    if set(members) != {RAW_NAME}:
        raise ValueError('MHAS currently accepts the Core respondent module only; do not flatten other products')
    directory = Path(directory)
    with (directory / 'raw_codebook.csv').open(encoding='utf-8-sig', newline='') as f:
        book = list(csv.DictReader(f))
    aliases = [r.get('newname', '') for r in book]
    if len(set(aliases)) != len(aliases) or set(aliases) != set(expected):
        raise ValueError('MHAS dictionary must match the selected aliases exactly')
    if any(not r.get('Variable', '').endswith(' (' + CORE + ')') for r in book):
        raise ValueError('MHAS dictionary contains a different source product')
    with primary_raw(directory).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        if len(set(header)) != len(header) or not {'ID', 'Wave_id'} <= set(header):
            raise ValueError('MHAS requires distinct ID and Wave_id columns')
        if set(header) - IDENTIFIERS != set(expected) - IDENTIFIERS or not set(expected) <= set(header):
            raise ValueError('MHAS raw columns differ from the selected sources and default identifiers')
        seen_id, seen_person, periods = set(), set(), set()
        for row in reader:
            key = (row['ID'], row['Wave_id'])
            if not row['ID'].strip() or key[1] not in PERIODS or not identity_matches(row):
                raise ValueError('MHAS missing person identity or unsupported period')
            if row['ID'] in seen_id or key in seen_person:
                raise ValueError('MHAS duplicated ID or person-period row')
            seen_id.add(row['ID']); seen_person.add(key); periods.add(key[1])
    return {'rows': len(seen_id), 'header': header,
            'periods': sorted(periods), 'key': ['ID', 'Wave_id'],
            'scope': CORE, 'identity_columns': [x for x in header if x in IDENTIFIERS]}

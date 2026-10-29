"""Validate the existing NHANES III unique-person website export, without rewriting raw."""
from __future__ import annotations
import csv
import re
from pathlib import Path

RAW_NAME = 'raw_data_NHANES_III.csv'
DEFAULTS = ('SEQN', '_survey_period', '_period')
PERIODS = {'1988-1994', '1988-1991', '1991-1994'}


def person_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+(?:\.0+)?', value):
        raise ValueError('NHANES III SEQN must be a nonempty integer identifier')
    key = re.sub(r'\.0+$', '', value).lstrip('0') or '0'
    if key == '0':
        raise ValueError('NHANES III SEQN must be positive')
    return key


def validate_package(directory, members, expected):
    directory = Path(directory)
    raw_members = {name for name in members if name.startswith('raw_data') and name.endswith('.csv')}
    if raw_members != {RAW_NAME}:
        raise ValueError('NHANES III adapter supports only the original unique-person file: '+RAW_NAME)
    if len(set(expected)) != len(expected) or set(expected).intersection(DEFAULTS):
        raise ValueError('NHANES III source aliases must be unique and exclude default identifiers')
    with (directory/'raw_codebook.csv').open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['Survey', 'Variable', 'Label', 'File type', 'newname']:
            raise ValueError('NHANES III dictionary header differs from the verified website export')
        dictionary = list(reader)
    if ({r['newname'] for r in dictionary} != set(expected) or len(dictionary) != len(expected)
            or any(r['Survey'] != 'NHANES III' or r['File type'] != 'uniqPersonID'
                   or not re.fullmatch(r'[^()\s]+ \(.+\)', r['Variable']) for r in dictionary)
            or len({r['Variable'] for r in dictionary}) != len(dictionary)):
        raise ValueError('NHANES III dictionary contains unexpected aliases, survey, source identities or file types')
    with (directory/RAW_NAME).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        if (len(set(header)) != len(header) or 'SEQN' not in header
                or set(header) != set(expected) | (set(header) & set(DEFAULTS))):
            raise ValueError('NHANES III raw header differs from selected sources plus verified defaults')
        seen, periods = set(), set()
        for number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Malformed NHANES III CSV row {number}')
            key = person_key(row['SEQN'])
            if key in seen:
                raise ValueError(f'Duplicate NHANES III person at CSV row {number}')
            seen.add(key)
            for name in ('_survey_period', '_period'):
                value = row.get(name, '')
                if value and value not in PERIODS:
                    raise ValueError(f'Unverified NHANES III period {value!r} at CSV row {number}')
                if value:
                    periods.add(value)
    if not seen:
        raise ValueError('NHANES III export has no person records')
    return {'files': {RAW_NAME: {'header': header, 'rows': len(seen), 'data_vars': list(expected),
                                'identity_columns': [x for x in DEFAULTS if x in header],
                                'observed_periods': sorted(periods)}}, 'dictionary_rows': len(dictionary)}

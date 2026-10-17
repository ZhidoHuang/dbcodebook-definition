"""Validate NHANES ordinary unique-SEQN exports; repeated sources are out of scope."""
import csv
import re
from pathlib import Path

IDENTIFIERS = ('SEQN', 'YEAR')
SOURCE_TYPE = '常规(唯一SEQN)'


def validate_package(root, members, aliases):
    root = Path(root)
    if list(members) != ['raw_data.csv']:
        raise ValueError('NHANES ordinary export requires only raw_data.csv')
    if len(set(aliases)) != len(aliases) or set(aliases) & set(IDENTIFIERS):
        raise ValueError('NHANES aliases must be unique and exclude default identities')
    with (root / 'raw_codebook.csv').open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not {'Variable', 'File type', 'newname'}.issubset(reader.fieldnames or []):
            raise ValueError('NHANES dictionary fields missing')
        rows = list(reader)
    if len(rows) != len(aliases) or {r['newname'] for r in rows} != set(aliases):
        raise ValueError('NHANES dictionary aliases differ from selected sources')
    if any(r['File type'] != 'uniqID' or not r['Variable'].strip() for r in rows):
        raise ValueError('NHANES only supports ordinary uniqID sources')
    keys, periods = set(), set()
    with (root / 'raw_data.csv').open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        if header[:2] != list(IDENTIFIERS) or len(header) != len(aliases) + 2 or set(header[2:]) != set(aliases):
            raise ValueError('NHANES requires SEQN,YEAR followed by selected aliases')
        for number, row in enumerate(reader, 2):
            person, period = row['SEQN'], row['YEAR']
            if not re.fullmatch(r'[0-9]+(?:\.0+)?', person or '') or not re.fullmatch(r'[0-9]{4}-[0-9]{4}', period or ''):
                raise ValueError(f'Invalid NHANES identity at CSV row {number}')
            start, end = map(int, period.split('-'))
            if start >= end:
                raise ValueError(f'Invalid NHANES period at CSV row {number}')
            key = (re.sub(r'\.0+$', '', person).lstrip('0') or '0', period)
            if key in keys:
                raise ValueError(f'Duplicate NHANES person-period at CSV row {number}')
            keys.add(key)
            periods.add(period)
    if not keys:
        raise ValueError('NHANES export contains no rows')
    return {'rows': len(keys), 'keys': list(IDENTIFIERS), 'periods': sorted(periods), 'header': header}

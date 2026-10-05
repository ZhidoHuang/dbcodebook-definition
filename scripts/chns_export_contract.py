"""CHNS personal-period and static-person files; other record levels are separate."""
import csv
import re
from pathlib import Path

YEARS = {'1989', '1991', '1993', '1997', '2000', '2004', '2006', '2009', '2011', '2015'}
MAIN_IDS = {'ID', 'IDind', 'WAVE', 'hhid', 'COMMID', 'Household_ID', 'Community_ID'}


def normalize_year(value):
    """Compare integer-equivalent exported WAVE text without rewriting source cells."""
    text = str(value)
    if not re.fullmatch(r'\d{4}(?:\.0+)?', text):
        raise ValueError('CHNS invalid year: expected an integer survey year')
    year = text.split('.', 1)[0]
    if year not in YEARS:
        raise ValueError('CHNS invalid year outside supported survey periods')
    return year


def rows_at(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        if not header or len(header) != len(set(header)):
            raise ValueError('CHNS CSV has missing or duplicate column names')
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('CHNS CSV has malformed rows')
    return header, rows


def validate_person_package(directory, members, expected):
    directory = Path(directory)
    header, dictionary = rows_at(directory / 'raw_codebook.csv')
    if not {'Variable', 'newname', 'File type'}.issubset(header):
        raise ValueError('CHNS dictionary requires full source identity, alias and file type')
    files, aliases, identities = {}, set(), set()
    has_person_period = any(row.get("File type") == "uniqID" for row in dictionary)
    for row in dictionary:
        match = re.fullmatch(r'([^()\s]+) \(([^/\\]+)\)', row['Variable'])
        alias, kind = row['newname'], row['File type']
        if not match or not alias or alias in aliases or row['Variable'] in identities:
            raise ValueError('CHNS dictionary has invalid or duplicate source/alias')
        source = match[2]
        if kind not in {'uniqID', 'personID'}:
            raise ValueError('CHNS personal adapter does not support this record level')
        member = 'raw_data.csv' if kind == 'uniqID' else f'raw_data_{source}.csv'
        merged_static = kind == 'personID' and member not in members and has_person_period
        if merged_static:
            member = 'raw_data.csv'
        output_kind = 'uniqID' if member == 'raw_data.csv' else kind
        item = files.setdefault(member, {'kind': output_kind, 'sources': set(), 'aliases': set(), 'static_aliases': set()})
        if item['kind'] != output_kind:
            raise ValueError('CHNS source file types conflict')
        if merged_static:
            item['static_aliases'].add(alias)
        item['sources'].add(source)
        item['aliases'].add(alias)
        aliases.add(alias)
        identities.add(row['Variable'])
    if not aliases or len(expected) != len(set(expected)) or aliases != set(expected):
        raise ValueError('CHNS dictionary aliases differ from selection')
    if len(members) != len(set(members)) or set(members) != set(files):
        raise ValueError('CHNS package files differ from dictionary record levels')
    reports = {}
    for member, spec in files.items():
        columns, rows = rows_at(directory / member)
        static = spec['kind'] == 'personID'
        keys = ['IDind'] if static else ['ID', 'IDind', 'WAVE']
        allowed = {'IDind'} if static else MAIN_IDS | {
            f'{key} ({source})' for key in MAIN_IDS - {'ID'} for source in spec['sources']}
        if not set(keys).issubset(columns):
            raise ValueError('CHNS personal keys missing or ambiguous across sources')
        if spec['aliases'] & allowed or set(columns) - allowed != spec['aliases']:
            raise ValueError('CHNS business columns differ from their dictionary file')
        seen, person_period = set(), set()
        static_values = {}
        for row in rows:
            if any(not row[key].strip() for key in keys):
                raise ValueError('CHNS personal identity is empty')
            identity = row['IDind'] if static else row['ID']
            if identity in seen:
                raise ValueError('CHNS duplicate personal identity')
            seen.add(identity)
            if not static:
                pair = (row['IDind'], normalize_year(row['WAVE']))
                if pair in person_period:
                    raise ValueError('CHNS invalid year or duplicate person-period')
                person_period.add(pair)
                if spec['static_aliases']:
                    values = tuple(row[name] for name in sorted(spec['static_aliases']))
                    previous = static_values.setdefault(row['IDind'], values)
                    if previous != values:
                        raise ValueError('CHNS merged static values vary across personal periods')
        reports[member] = {'rows': len(rows), 'header': columns,
                           'identity_columns': [c for c in columns if c in allowed],
                           'data_vars': sorted(spec['aliases']), 'record_level': spec['kind'],
                           'merged_static_vars': sorted(spec['static_aliases'])}
    return reports

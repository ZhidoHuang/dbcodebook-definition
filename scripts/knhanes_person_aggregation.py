"""Bounded offline person aggregation contract; not clinical acceptance.

Only the four person-level diet questions repeated on day-two food rows are
supported. Raw files and RowIndex are never rewritten. The transport validator
must still validate the original website package before this layer is used.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

KEYS = ('ID', 'id', 'year')
MEMBER = 'raw_data_Dietary_recall_second_day.csv'
FILE = 'Dietary recall second day'
FIELDS = {'n_diet': 'numeric_code', 'n_diet_why': 'numeric_code',
          'n_dt_ds': 'text', 'n_dt_etc': 'text'}


def _rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def validate_plan(codebook, source_record):
    plan = source_record.get('knhanes_person_aggregation')
    if not isinstance(plan, dict):
        raise ValueError('A source-bound person aggregation plan is required')
    fixed = {'schema_version': 1, 'primary_file': 'raw_data.csv',
             'repeat_file': MEMBER, 'source_file': FILE,
             'group_keys': list(KEYS), 'visit_periods': ['2009', '2019'],
             'method': 'constant_within_person_visit',
             'missing_rule': 'single_known_or_all_missing',
             'conflict_rule': 'group_na_and_report',
             'join': 'left_to_primary', 'orphan_rule': 'stop'}
    if any(plan.get(k) != value for k, value in fixed.items()):
        raise ValueError('Unsupported or incomplete day-two aggregation policy')
    repeat = [row for row in codebook if row['File type'] == 'reID']
    if len(repeat) != 4:
        raise ValueError('Exactly the four day-two diet fields must be declared')
    by_original = {}
    for row in repeat:
        identity = row['Variable']
        suffix = f' ({FILE})'
        if not identity.endswith(suffix):
            raise ValueError('Other repeat families are not supported')
        variable = identity[:-len(suffix)]
        if variable not in FIELDS or variable in by_original:
            raise ValueError('Unsupported or duplicate day-two question')
        by_original[variable] = row['newname']
    specs = plan.get('source_summaries')
    if not isinstance(specs, list) or len(specs) != 4:
        raise ValueError('Four explicit summary lineages are required')
    summaries = {}
    raw_names = {row['newname'] for row in codebook}
    final_names = set(source_record.get('approved_analysis_vars', []))
    for spec in specs:
        original = spec.get('original_variable')
        name = spec.get('variable')
        if (original not in FIELDS or not isinstance(name, str) or not name.isascii()
                or not name.replace('_', '').isalnum() or not name[0].isalpha()
                or name in raw_names | final_names | set(KEYS) | set(summaries)
                or spec.get('source_variables') != [by_original[original]]
                or spec.get('value_type') != FIELDS[original]):
            raise ValueError('Summary identity, type or lineage differs from source')
        summaries[name] = dict(spec)
    if {x['original_variable'] for x in summaries.values()} != set(FIELDS):
        raise ValueError('Every selected question needs one summary')
    return plan, summaries


def expected_person_summaries(directory, source_record, transport_contract):
    directory = Path(directory)
    if set(transport_contract['data']) != {'raw_data.csv', MEMBER}:
        raise ValueError('Only regular personal data plus day-two diet is supported')
    if transport_contract['data'][MEMBER]['identity_columns'] != ['RowIndex', *KEYS]:
        raise ValueError('Original repeated-row identity must remain present')
    _, codebook = _rows(directory / 'raw_codebook.csv')
    plan, summaries = validate_plan(codebook, source_record)
    _, core = _rows(directory / 'raw_data.csv')
    _, repeated = _rows(directory / MEMBER)
    core_keys = [tuple(row[k] for k in KEYS) for row in core]
    if len(set(core_keys)) != len(core_keys):
        raise ValueError('Primary person-year keys are not unique')
    core_set = set(core_keys)
    grouped = defaultdict(list)
    for row in repeated:
        key = tuple(row[k] for k in KEYS)
        if row['year'] not in plan['visit_periods']:
            raise ValueError('Unexpected visit period; no silent year exclusion')
        if key not in core_set:
            raise ValueError('Day-two respondent has no primary person-year')
        grouped[key].append(row)
    expected = {key: {name: None for name in summaries} for key in core_keys}
    conflict_groups = []
    mixed_missing_fields = 0
    for key, rows in grouped.items():
        values = {}
        conflicts = {}
        for name, spec in summaries.items():
            raw = spec['source_variables'][0]
            # Only read.csv's ordinary blank/NA are treated as missing here.
            # Labels, 8/9 and arbitrary text are retained for clinical review.
            originals = {row[raw] for row in rows if row[raw] not in ('', 'NA')}
            # Numeric code spelling may change under read.csv type inference.
            # Compare finite code values numerically; original free text stays exact.
            known = set()
            for value in originals:
                normalized = value
                if spec['value_type'] == 'numeric_code':
                    try:
                        numeric = Decimal(value)
                        if numeric.is_finite():
                            normalized = format(numeric.normalize(), 'f')
                    except InvalidOperation:
                        pass
                known.add(normalized)
            if known and any(row[raw] in ('', 'NA') for row in rows):
                mixed_missing_fields += 1
            if len(known) > 1:
                conflicts[raw] = sorted(originals)
            values[name] = next(iter(known)) if len(known) == 1 else None
        if conflicts:
            # Hold all four related question summaries for this visit only.
            # Exact conflicting raw values remain in the untouched source file.
            conflict_groups.append({'key': key, 'source_values': conflicts,
                                    'source_rows': [r['RowIndex'] for r in rows]})
        else:
            expected[key] = values
    return expected, summaries, {'primary_rows': len(core), 'repeat_rows': len(repeated),
        'repeat_person_visits': len(grouped), 'conflict_person_visits': len(conflict_groups),
        'conflicts': conflict_groups, 'mixed_missing_fields': mixed_missing_fields,
        'scope': 'deterministic source aggregation only; no clinical text classification'}


def _same(actual, expected, value_type):
    if expected is None:
        return actual is None or actual == ''
    if value_type == 'text':
        return isinstance(actual, str) and actual == expected
    try:
        return actual is not None and Decimal(str(actual)) == Decimal(expected)
    except (InvalidOperation, ValueError):
        return isinstance(actual, str) and actual == expected


def validate_summary_cells(header, workbook_rows, expected, summaries):
    if not set(KEYS) | set(summaries) <= set(header):
        raise ValueError('Workbook omits identity or declared summary columns')
    indexes = {name: header.index(name) for name in (*KEYS, *summaries)}
    keys = [tuple(str(row[indexes[k]]) for k in KEYS) for row in workbook_rows]
    if keys != list(expected):
        raise ValueError('Primary person-year rows/order changed or repeated food rows leaked')
    checked = 0
    for key, row in zip(keys, workbook_rows):
        for name, spec in summaries.items():
            if not _same(row[indexes[name]], expected[key][name], spec['value_type']):
                raise ValueError('Source summary cell differs from independent aggregation: ' + name)
            checked += 1
    return {'rows': len(keys), 'source_summary_cells': checked, 'differences': 0}

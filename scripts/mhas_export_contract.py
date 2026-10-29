"""Verified MHAS person exports, retaining each product's physical raw file."""
import csv
import re
from itertools import product
from pathlib import Path

CORE = 'MHAS_SURVEY_CORE_RESPONDENT'
NOK = 'MHAS_SURVEY_NEXT_OF_KIN'
MEXCOG_COGNITIVE = 'MHAS_MEXCOG_COGNITIVE_ASSESSMENT'
MEXCOG_INFORMANT = 'MHAS_MEXCOG_INFORMANT_INTERVIEW'
SCOPED_MODULES = {CORE, NOK, MEXCOG_COGNITIVE, MEXCOG_INFORMANT}
RAW_NAME = 'raw_data_' + CORE + '.csv'
PERIODS = ('2001', '2003', '2012', '2015', '2018', '2021', '2024')
ANTHROPOMETRICS = 'MHAS_ANCILLARY_ANTHROPOMETRICS_BIOMARKERS'
HEAVY_METALS = 'MHAS_ANCILLARY_HEAVY_METALS'
SOURCE_PERIODS = {CORE: PERIODS,
                  NOK: ('2003', '2012', '2015', '2018', '2021', '2024'),
                  ANTHROPOMETRICS: ('2001', '2003', '2012', '2016'),
                  HEAVY_METALS: ('2018',),
                  MEXCOG_COGNITIVE: ('2016', '2021'),
                  MEXCOG_INFORMANT: ('2016', '2021')}
IDENTIFIERS = {'ID', 'Wave_id', 'UNHHIDNP', 'CUNICAH', 'NP', 'cunicah', 'np',
               'unhhid', 'ps3', 'acthog', 'ent2', 'codent01', 'codent03',
               'source_file', 'source_row'}
SOURCE_IDENTIFIERS = {
    CORE: IDENTIFIERS,
    NOK: {'ID', 'Wave_id', 'cunicah', 'np', 'unhhid', 'acthog', 'ent2', 'UNHHIDNP',
          'source_file', 'source_row'},
    ANTHROPOMETRICS: {'ID', 'Wave_id', 'cunicah', 'np', 'acthog', 'ent2',
                     'unhhid', 'ps3', 'source_file', 'source_row'},
    HEAVY_METALS: {'ID', 'Wave_id', 'cunicah', 'np', 'source_file', 'source_row'},
    MEXCOG_COGNITIVE: {'ID', 'Wave_id', 'cunicah', 'np', 'CUNICAH', 'NP', 'source_file', 'source_row'},
    MEXCOG_INFORMANT: {'ID', 'Wave_id', 'cunicah', 'np', 'CUNICAH', 'NP', 'source_file', 'source_row'},
}
PERSON_SHAPES = [('unhhidnp',), ('cunicah', 'np'), ('unhhid', 'np'),
                 ('cunicah', 'acthog', 'ent2'), ('cunicah', 'ent2'), ('unhhid', 'ps3'),
                 ('cunicah', 'acthog', 'codent03'), ('cunicah', 'codent01')]
ANCILLARY_PERSON_SHAPES = {
    NOK: {'2003': [('cunicah', 'acthog', 'ent2')],
          '2012': [('cunicah', 'np')], '2015': [('cunicah', 'np')],
          '2018': [('unhhidnp',)], '2021': [('cunicah', 'np')],
          '2024': [('unhhidnp',)]},
    ANTHROPOMETRICS: {'2001': [('unhhid', 'ps3')],
                     '2003': [('cunicah', 'acthog', 'ent2')],
                     '2012': [('cunicah', 'np')], '2016': [('cunicah', 'np')]},
    HEAVY_METALS: {'2018': [('cunicah', 'np')]},
    MEXCOG_COGNITIVE: {'2016': [('cunicah', 'np')], '2021': [('CUNICAH', 'NP')]},
    MEXCOG_INFORMANT: {'2016': [('cunicah', 'np')], '2021': [('CUNICAH', 'NP')]},
}


def supported_combination(sources):
    sources = set(sources)
    return (sources <= SCOPED_MODULES or sources <= {ANTHROPOMETRICS, HEAVY_METALS})


def identity_matches(row, shapes=None, exact_case=False):
    def value(name):
        text = str(row.get(name) or '').strip()
        return re.sub(r'(?<=\d)\.0$', '', text)
    for shape in PERSON_SHAPES if shapes is None else shapes:
        choices = [[k for k in row if (k == part if exact_case else k.casefold() == part.casefold())] for part in shape]
        for columns in product(*choices):
            parts = [value(k) for k in columns]
            if all(parts) and row['ID'] == '|'.join([row['Wave_id'], *parts]):
                return True
    return False


def raw_files(directory):
    """Return separate, supported raw paths; reject flattened or mixed products."""
    paths = sorted(Path(directory).glob('raw_data*.csv'))
    sources = {p.name: p for p in paths}
    supported = {'raw_data_' + source + '.csv' for source in SOURCE_PERIODS}
    modules = {p.name[len('raw_data_'):-4] for p in paths}
    if set(sources) - supported or not supported_combination(modules):
        raise ValueError('MHAS accepts separate Core/NOK/Mex-Cog files or verified biomarker/metals files; do not flatten or mix these families')
    return paths


def primary_raw(directory):
    """Representative path for compatibility; callers must process raw_files separately."""
    paths = raw_files(directory)
    return paths[0] if paths else Path(directory) / RAW_NAME


def validate_package(directory, members, expected):
    directory = Path(directory)
    with (directory / 'raw_codebook.csv').open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or not {'Variable', 'newname'} <= set(fields):
            raise ValueError('MHAS dictionary requires Variable and newname')
        book = list(reader)
    aliases = [r.get('newname', '') for r in book]
    if not aliases or any(not a for a in aliases) or len(set(expected)) != len(expected) or len(set(aliases)) != len(aliases) or set(aliases) != set(expected):
        raise ValueError('MHAS dictionary must match the selected aliases exactly')
    groups, identities = {}, set()
    for row in book:
        identity = row.get('Variable') or ''
        match = re.fullmatch(r'([^()\s]+) \(([^()]+)\)', identity)
        if not match or match[2] not in SOURCE_PERIODS:
            raise ValueError('MHAS dictionary contains a different source product or incomplete Variable identity')
        source = match[2]
        if identity in identities:
            raise ValueError('MHAS dictionary contains a duplicated source identity')
        identities.add(identity)
        if source != CORE and row.get('File type') != 'uniqPersonID':
            raise ValueError('MHAS non-Core dictionary must use uniqPersonID')
        groups.setdefault(source, []).append(row['newname'])
    filenames = {'raw_data_' + source + '.csv': source for source in groups}
    if len(members) != len(filenames) or set(members) != set(filenames) or not supported_combination(groups):
        raise ValueError('MHAS files must match selected products; questionnaire files cannot mix with biomarkers/metals and raw files must not be flattened')
    if {p.name for p in raw_files(directory)} != set(filenames):
        raise ValueError('MHAS directory contains missing or additional raw files')
    facts = {name: _validate_file(directory / name, source, groups[source])
             for name, source in filenames.items()}
    if len(facts) == 1:
        return {**next(iter(facts.values())), 'files': facts}
    return {'rows': sum(f['rows'] for f in facts.values()),
            'header': list(dict.fromkeys(x for f in facts.values() for x in f['header'])),
            'periods': sorted({x for f in facts.values() for x in f['periods']}),
            'identity_columns': list(dict.fromkeys(x for f in facts.values() for x in f['identity_columns'])),
            'key': (['source_module', 'ID', 'Wave_id'] if set(groups) & (SCOPED_MODULES - {CORE}) else ['ID', 'Wave_id']),
            'scope': list(groups), 'files': facts}


def _validate_file(path, source, expected):
    identifiers = SOURCE_IDENTIFIERS[source]
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        if len(set(header)) != len(header) or not {'ID', 'Wave_id'} <= set(header):
            raise ValueError('MHAS requires distinct ID and Wave_id columns')
        if set(header) - identifiers != set(expected) - identifiers or not set(expected) <= set(header):
            raise ValueError('MHAS raw columns differ from the selected sources and default identifiers')
        seen_id, seen_person, periods = set(), set(), set()
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('MHAS malformed raw row')
            key = (row['ID'], row['Wave_id'])
            shapes = ANCILLARY_PERSON_SHAPES.get(source, {}).get(key[1])
            if not row['ID'].strip() or key[1] not in SOURCE_PERIODS[source] or not identity_matches(row, shapes, source in {MEXCOG_COGNITIVE, MEXCOG_INFORMANT}):
                raise ValueError('MHAS missing person identity or unsupported period')
            if row['ID'] in seen_id or key in seen_person:
                raise ValueError('MHAS duplicated ID or person-period row')
            seen_id.add(row['ID']); seen_person.add(key); periods.add(key[1])
    return {'rows': len(seen_id), 'header': header,
            'periods': sorted(periods), 'key': ['ID', 'Wave_id'],
            'scope': source, 'identity_columns': [x for x in header if x in identifiers]}


def validate_analysis_scope(scopes, approved=None):
    if not isinstance(scopes, dict) or not scopes or not set(scopes) <= SCOPED_MODULES:
        raise ValueError('Invalid MHAS analysis module scope')
    owners = set()
    for module, scope in scopes.items():
        if not isinstance(scope, dict): raise ValueError('Invalid module scope')
        periods, variables = scope.get('analysis_periods'), scope.get('result_variables')
        if not isinstance(periods, list) or not periods or any(not isinstance(p, str) for p in periods) or len(set(periods)) != len(periods) or not set(periods) <= set(SOURCE_PERIODS[module]):
            raise ValueError('Invalid module analysis_periods: ' + module)
        if not isinstance(variables, list) or not variables or any(not isinstance(v, str) or not v.strip() or v in IDENTIFIERS or v == 'source_module' for v in variables) or len(set(variables)) != len(variables) or owners.intersection(variables):
            raise ValueError('Invalid/overlapping module result_variables: ' + module)
        owners.update(variables)
    if approved is not None and (not isinstance(approved, list) or set(approved) != owners or len(approved) != len(owners)):
        raise ValueError('MHAS scope must own every approved result exactly once')
    return scopes


def validate_scoped_analysis(paths, rows, header, record):
    """Questionnaire analysis is file-scoped; raw periods do not define applicability."""
    scopes = validate_analysis_scope((record or {}).get('mhas_analysis_scope'), (record or {}).get('approved_analysis_vars'))
    modules = {p.stem.removeprefix('raw_data_'): p for p in paths}
    if not isinstance(scopes, dict) or set(scopes) != set(modules):
        raise ValueError('MHAS requires exact mhas_analysis_scope for every source file')
    required = {'source_module', 'ID', 'Wave_id'}
    if not required.issubset(header):
        raise ValueError('MHAS scoped analysis requires source_module, ID, Wave_id')
    availability = {}
    selection = (record or {}).get('mhas_selection', {})
    if selection.get('mode') == 'raw_columns':
        from mhas_scoped_selection import build_raw
        prepared = build_raw(record, record.get('dbcodebook_url', 'http://localhost/'))
        for item in prepared['selected']:
            availability[(item['file'], item['alias'])] = set(item['periods'])
    owners = {}
    expected = {}
    columns = {}
    for module, path in modules.items():
        scope = scopes[module]
        periods = scope.get('analysis_periods', [])
        variables = scope.get('result_variables', [])
        if not periods or len(set(periods)) != len(periods) or not set(periods) <= set(SOURCE_PERIODS[module]):
            raise ValueError('Invalid module analysis_periods: ' + module)
        if not variables or len(set(variables)) != len(variables) or not set(variables) <= set(header):
            raise ValueError('Missing/invalid result_variables: ' + module)
        for variable in variables:
            if variable in owners: raise ValueError('Result belongs to multiple source modules: ' + variable)
            owners[variable] = module
        with path.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            columns[module] = [n for n in reader.fieldnames if n in SOURCE_IDENTIFIERS[module]]
            if not set(columns[module]) <= set(header):
                raise ValueError('Default identities not preserved for ' + module)
            raw_rows = list(reader)
            for raw_row in raw_rows:
                for (owner, alias), available in availability.items():
                    if owner == module and raw_row['Wave_id'] not in available and raw_row.get(alias) not in (None, ''):
                        raise ValueError('Raw source populated outside verified available periods: ' + alias)
            expected[module] = {(r['ID'], r['Wave_id']): r for r in raw_rows if r['Wave_id'] in periods}
    actual = set()
    for values in rows[1:]:
        row = dict(zip(header, values))
        module = row.get('source_module')
        if module not in modules: raise ValueError('Unknown source_module')
        if any(not isinstance(row.get(n), str) for n in required):
            raise ValueError('MHAS scoped keys must remain strings')
        key = (row['ID'], row['Wave_id'])
        original = expected[module].get(key)
        if original is None: raise ValueError('Analysis identity outside declared module/period or absent from raw')
        scoped_key = (module, *key)
        if scoped_key in actual: raise ValueError('Duplicate scoped identity')
        actual.add(scoped_key)
        for column in columns[module]:
            value = row.get(column)
            if ('' if value is None else str(value)) != original.get(column, ''):
                raise ValueError('Changed default identity: ' + module + ':' + column)
        for variable, owner in owners.items():
            if owner != module and row.get(variable) not in (None, ''):
                raise ValueError('Result populated in wrong source module: ' + variable)
    required_rows = {(module, *key) for module, entries in expected.items() for key in entries}
    if actual != required_rows:
        raise ValueError('Missing declared module-period rows')
    return {'rows': len(actual), 'key': ['source_module', 'ID', 'Wave_id'], 'modules': list(modules)}

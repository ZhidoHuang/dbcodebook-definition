"""Preserve MHAS identity/period scope and explicit download names."""
import re


def build(record, url):
    if record['mhas_selection'].get('mode') == 'raw_columns':
        return build_raw(record, url)
    scope = record['mhas_selection']
    digest = scope.get('dictionary_sha256', '')
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('MHAS scoped selection requires a dictionary SHA256')
    inputs, selected, initial, aliases, cells = [], [], [], set(), set()
    def needs_cells(item):
        periods = item['period_bindings']
        available = item.get('available_bindings', periods)
        groups = {}
        for period, variable in periods.items():
            alias = item.get('period_aliases', {}).get(period, item.get('aliases', {}).get(variable))
            groups.setdefault((variable, alias), set()).add(period)
        return any(ps != {p for p, v in available.items() if v == variable}
                   for (variable, alias), ps in groups.items())

    # Put period-cell work first so its verified rows are visible in the batch table.
    for item in sorted(scope['inputs'], key=lambda item: not needs_cells(item)):

        identity, file = item['variable_id'], item['file']
        periods = item['period_bindings']
        names = item.get('aliases')
        if not names:
            raise ValueError('MHAS requires explicit aliases by original column; old automatic suffixes are obsolete')
        available = item.get('available_bindings', periods)
        if (not periods or set(available) != set(item['available_periods'])
                or any(available.get(p) != v for p, v in periods.items())):
            raise ValueError('MHAS selection must retain verified available and selected period scopes')
        if set(names) != set(periods.values()):
            raise ValueError('MHAS aliases must cover the exact original columns')
        if not file or any(not isinstance(x, str) or not x or re.search(r'[\s()=,]', x)
                           for x in [identity, *names.values()]):
            raise ValueError('Invalid MHAS selector or alias')
        # A series input with several original columns cannot assign several names.
        # Select it once, then use the existing tag editor for those explicit names.
        period_names = item.get('period_aliases', {})
        if any(p not in periods for p in period_names):
            raise ValueError('MHAS period alias outside selected scope')
        grouped = {}
        for period, variable in periods.items():
            alias = period_names.get(period, names[variable])
            if not isinstance(alias, str) or not alias or re.search(r'[\s()=,]', alias):
                raise ValueError('Invalid MHAS period alias')
            grouped.setdefault((variable, alias), []).append(period)
        single = len(grouped) == 1 and periods == available
        input_alias = next(iter(grouped))[1] if single else None
        inputs.append(f'{identity} ({file})' + ('=' + input_alias if single else ''))
        for variable in dict.fromkeys(available.values()):
            initial.append(dict(variable=variable, file=file, variable_id=identity,
                                periods=sorted(p for p, v in available.items() if v == variable),
                                alias=input_alias if single else variable,
                                dictionary_sha256=digest))
        for (variable, alias), ps in grouped.items():
            ps = sorted(ps)
            if alias in aliases or any((identity, p) in cells for p in ps):
                raise ValueError('Duplicate MHAS period selector or alias')
            aliases.add(alias)
            cells.update((identity, p) for p in ps)
            full_periods = sorted(p for p, v in available.items() if v == variable)
            scopes = [ps] if ps == full_periods else [[p] for p in ps]
            for selected_periods in scopes:
                selected.append(dict(variable=variable, file=file, alias=alias,
                                     variable_id=identity, periods=selected_periods,
                                     initial_alias=input_alias if single else variable,
                                     dictionary_sha256=digest))
    expected = {(a, i) for g in record['source_groups']
                for a, i in zip(g['raw_variables'], g['source_identities'])}
    actual = {(r['alias'], f"{r['variable']} ({r['file']})") for r in selected}
    if not selected or actual != expected:
        raise ValueError('MHAS selectors differ from settled source groups')
    shape = lambda row: (row['variable_id'], row['variable'], tuple(row['periods']))
    desired = {shape(row): row for row in selected}
    retained = [desired[shape(row)] for row in initial if shape(row) in desired]
    retained_keys = {shape(row) for row in retained}
    export_order = retained + [row for row in selected if shape(row) not in retained_keys]
    snapshot = {'database': 'MHAS', 'status': 'READY', 'mhas_selection': scope,
                'source_groups': [{'raw_variables': g['raw_variables'], 'source_identities': g['source_identities']}
                                  for g in record['source_groups']]}
    return dict(kind='mhas_scoped_selection_v2', database='mhas', url=url,
                input_text='\n'.join(inputs), aliases=list(dict.fromkeys(r['alias'] for r in export_order)),
                selected=selected, dictionary_sha256=digest, source_record=snapshot,
                source_cell_count=sum(len(r['periods']) for r in initial), initial=initial)


def validate_action(action):
    if action.get('kind') == 'mhas_raw_column_selection_v1':
        if action != build_raw(action['source_record'], action['url']):
            raise ValueError('MHAS raw-column action changed; rebuild from settled record')
        return
    core = {k: v for k, v in action.items() if k not in ('rename_offset', 'selection_resume')}
    if core != build(action['source_record'], action['url']):
        raise ValueError('MHAS scoped action changed; rebuild from settled record')
    if 'selection_resume' in action and action['selection_resume'] is not True:
        raise ValueError('Invalid MHAS selection continuation')
    offset = action.get('rename_offset')
    if offset is not None and (not isinstance(offset, int) or offset < 0 or offset >= len(action['selected'])):
        raise ValueError('Invalid MHAS rename offset')


def build_raw(record, url):
    """Select physical columns; keep adopted business periods as separate evidence."""
    scope = record['mhas_selection']
    digest = scope.get('dictionary_sha256', '')
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('MHAS raw-column selection requires a dictionary SHA256')
    expected, alias_owners = {}, {}
    for group in record['source_groups']:
        if len(group['source_identities']) != len(group['raw_variables']):
            raise ValueError('MHAS source identities and aliases differ in length')
        for identity, alias in zip(group['source_identities'], group['raw_variables']):
            match = re.fullmatch(r'([^()\s]+)\s+\((.+)\)', identity)
            if not match or not alias or re.search(r'[\s()=,]', alias):
                raise ValueError('Invalid MHAS raw-column identity or alias')
            key = (match[1], match[2].strip())
            if key in expected and expected[key] != alias:
                raise ValueError('MHAS physical column needs one shared alias: ' + identity)
            if alias in alias_owners and alias_owners[alias] != key:
                raise ValueError('Duplicate MHAS raw-column alias: ' + alias)
            expected[key], alias_owners[alias] = alias, key
    evidence = {}
    for item in scope['inputs']:
        available = item.get('available_bindings', item['period_bindings'])
        if (set(available) != set(item['available_periods']) or
                any(available.get(p) != v for p,v in item['period_bindings'].items())):
            raise ValueError('MHAS available and business bindings conflict')
        for period, variable in available.items():
            key = (variable, item['file'])
            evidence.setdefault(key, {'periods':set(), 'business_periods':set(), 'owners':set()})
            evidence[key]['periods'].add(period)
            evidence[key]['owners'].add(item['variable_id'])
        for period, variable in item['period_bindings'].items():
            key = (variable, item['file'])
            alias = item.get('period_aliases', {}).get(period, item['aliases'].get(variable))
            if expected.get(key) != alias:
                raise ValueError('MHAS physical-column alias differs from business mapping')
            evidence[key]['business_periods'].add(period)
    rows=[]
    for (variable,file), alias in expected.items():
        info=evidence.get((variable,file))
        if not info or not info['business_periods']:
            raise ValueError('MHAS raw column lacks verified business periods')
        rows.append(dict(variable=variable,file=file,alias=alias,periods=sorted(info['periods']),
                         business_periods=sorted(info['business_periods']),
                         evidence_variable_ids=sorted(info['owners'])))
    if not rows:
        raise ValueError('MHAS raw-column selection is empty')
    snapshot={'database':'MHAS','status':'READY','mhas_selection':scope,
              'source_groups':[{'source_identities':g['source_identities'],'raw_variables':g['raw_variables']}
                               for g in record['source_groups']]}
    return dict(kind='mhas_raw_column_selection_v1',database='mhas',url=url,
                dictionary_sha256=digest,selected=rows,aliases=[r['alias'] for r in rows],
                input_text='\n'.join(f"{r['variable']} ({r['file']})={r['alias']}" for r in rows),
                source_record=snapshot)

"""Prepare bulk UI input and download aliases from one settled source list, offline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from skill_config import load_config, database_url


def parse_selection(text):
    rows, identities, aliases = [], set(), set()
    for item in re.split(r'[\n,]', text):
        item = item.strip()
        if not item:
            continue
        if item.count('=') != 1:
            raise ValueError('Each source must be full Variable (File)=alias')
        identity, alias = (part.strip() for part in item.split('='))
        match = re.fullmatch(r'([^()\s]+)\s+\((.+)\)', identity)
        if not match or not match[2].strip():
            raise ValueError('Missing full source identity: ' + identity)
        if not alias or any(ord(char) < 32 for char in alias):
            raise ValueError('Invalid download alias: ' + alias)
        key = (match[1], match[2].strip())
        if key in identities or alias in aliases:
            raise ValueError('Duplicate source or alias: ' + item)
        identities.add(key)
        aliases.add(alias)
        rows.append({'identity': identity, 'alias': alias})
    if not rows:
        raise ValueError('Source selection is empty')
    return rows


def build_action(text, url):
    rows = parse_selection(text)
    return {'kind': 'source_selection_v1', 'url': url,
            'input_text': '\n'.join(row['identity'] + '=' + row['alias'] for row in rows),
            'aliases': [row['alias'] for row in rows]}


def build_record_action(record, url):
    """Retain concept links in the record; deduplicate only identical sources."""
    if record.get('status') != 'READY':
        raise ValueError('Use the primary merged READY record, not an independent proposal')
    groups = record.get('source_groups')
    if not isinstance(groups, list) or not groups:
        raise ValueError('source_groups must contain the settled sources')
    sources, aliases = {}, {}
    for group in groups:
        identities, names = group.get('source_identities'), group.get('raw_variables')
        if (not isinstance(identities, list) or not isinstance(names, list)
                or not identities or len(identities) != len(names)):
            raise ValueError('Each source identity must have one positional download alias')
        for identity, alias in zip(identities, names):
            if not isinstance(identity, str) or not isinstance(alias, str):
                raise ValueError('Source identity and alias must be strings')
            rows = parse_selection(identity + '=' + alias)
            if len(rows) != 1:
                raise ValueError('Each source entry must contain exactly one identity and alias')
            row = rows[0]
            match = re.fullmatch(r'([^()\s]+)\s+\((.+)\)', row['identity'])
            key = (match[1], match[2].strip())
            name = row['alias']
            if key in sources and sources[key] != name:
                raise ValueError('One source has conflicting aliases: ' + identity)
            if name in aliases and aliases[name] != key:
                raise ValueError('Different sources share an alias: ' + name)
            sources[key], aliases[name] = name, key
    return build_action('\n'.join(f'{var} ({file})={alias}'
                                  for (var, file), alias in sources.items()), url)


def browser_code(action, mode):
    if mode == 'select':
        rebuilt = build_action(action['input_text'], action['url'])
        if action != rebuilt:
            raise ValueError('Selection action is inconsistent; regenerate from the source list')
    source = Path(__file__).with_name('source_selection.js').read_text(encoding='utf-8')
    return 'async page => (' + source + ')(page, ' + json.dumps(action) + ', ' + json.dumps(mode) + ')'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--input', type=Path, help='Legacy explicit full-identity list')
    source.add_argument('--record', type=Path, help='Primary merged READY source record')
    parser.add_argument('--database', required=True, choices=['charls', 'elsa', 'hrs'])
    parser.add_argument('--config', type=Path)
    parser.add_argument('--action-file', required=True, type=Path)
    parser.add_argument('--expect-vars-file', required=True, type=Path)
    args = parser.parse_args()
    paths = [p.resolve() for p in (args.record or args.input, args.action_file, args.expect_vars_file)]
    if len(set(paths)) != 3:
        parser.error('Input, action and alias output must be distinct files')
    url = database_url(load_config(args.config), args.database)
    if args.record:
        record = json.loads(args.record.read_text(encoding='utf-8-sig'))
        if str(record.get('database', '')).lower() != args.database:
            raise ValueError('Source record database differs from requested database')
        action = build_record_action(record, url)
    else:
        action = build_action(args.input.read_text(encoding='utf-8-sig'), url)
    for path in (args.action_file, args.expect_vars_file):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.action_file.write_text(json.dumps(action, ensure_ascii=False, indent=2), encoding='utf-8')
    args.expect_vars_file.write_text('\n'.join(action['aliases']) + '\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'count': len(action['aliases']), 'offline': True}))


if __name__ == '__main__':
    main()

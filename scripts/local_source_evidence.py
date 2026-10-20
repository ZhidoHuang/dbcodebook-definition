"""Validate optional local dictionary receipts; no local database or private config access."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

LOCAL_DICTIONARY_API = 1


def read_reference(ref, base):
    if not isinstance(ref, dict) or not ref.get('path') or not ref.get('sha256'):
        raise ValueError('Local evidence requires path and sha256')
    path = Path(ref['path'])
    if not path.is_absolute():
        path = base / path
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != ref['sha256']:
        raise ValueError('Local evidence changed: ' + str(path))
    return json.loads(content.decode('utf-8-sig'))


def validate_local_evidence(record, record_path):
    access = record.get('source_access')
    if access is None:
        return None
    if not isinstance(access, dict) or access.get('mode') != 'local_dictionary':
        raise ValueError('Unsupported explicit source_access mode')
    base = Path(record_path).parent
    binding = read_reference(access.get('binding'), base)
    if binding.get('schema') != 'dbcodebook.local-binding.v1' or binding.get('ok') is not True:
        raise ValueError('Local dictionary binding is not valid')
    database = str(record['database']).lower()
    if binding.get('database') != database:
        raise ValueError('Local dictionary database differs from topic')
    if binding.get('website_url', '').rstrip('/') != record.get('dbcodebook_url', '').rstrip('/'):
        raise ValueError('Local dictionary binding targets a different website')
    if database == 'klosa' and binding.get('language') != record.get('language'):
        raise ValueError('Local dictionary language differs from topic')
    if binding.get('mapping', {}).get('kind') != 'runtime_settings_same_file':
        raise ValueError('Local dictionary needs verified runtime/settings/file mapping')
    if not re.fullmatch(r'[0-9a-f]{64}', str(binding.get('dictionary_sha256', ''))):
        raise ValueError('Local binding needs a dictionary SHA256')
    receipts = access.get('receipts')
    if not isinstance(receipts, list) or not receipts:
        raise ValueError('No local dictionary receipts')
    directories, sources, keywords = set(), {}, set()
    scoped_sources = {}
    for ref in receipts:
        data = read_reference(ref, base)
        if (data.get('schema') != 'dbcodebook.local-source.v1' or data.get('ok') is not True
                or data.get('database') != database
                or data.get('language') != binding.get('language')
                or data.get('binding_sha256') != access['binding']['sha256']
                or data.get('dictionary_sha256') != binding.get('dictionary_sha256')):
            raise ValueError('Local receipt is failed, mismatched or from another binding')
        request = data.get('request', {})
        if request.get('kind') not in ('search', 'directory', 'detail'):
            raise ValueError('Unsupported local query kind')
        if request.get('kind') == 'search':
            keywords.add(request.get('query'))
        for row in data.get('sources', []):
            for path in row.get('directory_paths', []):
                if path:
                    directories.add(' > '.join(path))
            if request.get('kind') != 'detail':
                continue
            if database == 'mhas' and record.get('mhas_selection'):
                raw = row.get('raw_row', {})
                available = {p for p in binding['periods'] if raw.get(p) not in (None, '')}
                owner = scoped_sources.setdefault(row.get('variable_id'),
                    {'file': row.get('file'), 'available': available, 'periods': {}})
                if owner['file'] != row.get('file') or owner['available'] != available:
                    raise ValueError('Conflicting MHAS identity receipts')
                for cell in row.get('periods', []):
                    if cell.get('available'):
                        previous = owner['periods'].setdefault(cell['period'], cell['actual_variable'])
                        if previous != cell['actual_variable']:
                            raise ValueError('Conflicting MHAS period mapping')
            for period in row.get('periods', []):
                if not period.get('available'):
                    continue
                name = period.get('source_identity')
                if name != f"{period.get('actual_variable')} ({row.get('file')})":
                    raise ValueError('Local detail source identity is inconsistent')
                if name:
                    sources.setdefault(name, set()).add(period['period'])
        for path in data.get('directory_paths', []):
            if path:
                directories.add(' > '.join(path))
    for group in record.get('source_groups', []):
        if group.get('discovery', {}).get('mode') != 'local_dictionary':
            raise ValueError('Local-source groups must identify local_dictionary discovery')
        names = group.get('source_identities') or []
        periods = set(group.get('periods') or [])
        covered = set()
        for name in names:
            if name not in sources:
                raise ValueError('Missing local detail for source: ' + name)
            if not sources[name] & periods:
                raise ValueError('Local source does not cover any declared period: ' + name)
            covered.update(sources[name])
        if not names or not periods.issubset(covered):
            raise ValueError('Local detail does not cover declared source-group periods')
    if record.get('mhas_selection'):
        if database != 'mhas' or record['mhas_selection']['dictionary_sha256'] != binding['dictionary_sha256']:
            raise ValueError('MHAS selection dictionary differs from source binding')
        from mhas_scoped_selection import build
        action = build(record, record['dbcodebook_url'])
        for item in record['mhas_selection']['inputs']:
            owner = scoped_sources.get(item['variable_id'])
            if (not owner or owner['file'] != item['file']
                    or owner['available'] != set(item['available_periods'])
                    or any(owner['periods'].get(p) != v for p, v in item.get('available_bindings', item['period_bindings']).items())):
                raise ValueError('MHAS selector is not supported by exact identity/period receipts')
        by_alias = {}
        for row in action['selected']:
            by_alias.setdefault(row['alias'], set()).update(row.get('business_periods', row['periods']))
        for group in record['source_groups']:
            covered = {p for a in group['raw_variables'] for p in by_alias[a]}
            if not set(group['periods']).issubset(covered):
                raise ValueError('MHAS source-group periods differ from scoped aliases')
    return {'directories': directories, 'sources': sources, 'keywords': keywords}

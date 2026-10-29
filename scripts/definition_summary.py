"""Verify an approved introduction replacement, without rechecking unchanged calculations."""
from pathlib import Path
import hashlib
import html
import json
import re
from definition_order import Spans

RECEIPT = 'definition_summary_update.json'


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest().upper()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def visible(text):
    return re.sub(r'\s+', '', html.unescape(re.sub(r'<[^>]+>', '', text)).replace('**', '').replace('`', ''))


def bounds(text, rendered=False):
    heading = re.search(r'(?m)^##\s+摘要导读\s*$', text)
    if not heading:
        raise ValueError('Missing summary heading')
    start = heading.end()
    rest = text[start:]
    stops = [m.start() for m in re.finditer(r'(?m)^#{2,3}\s|^```|^<!-- summary-insight-card:start -->|^<div\b[^\n>]*data-raw-source-structure="true"', rest)]
    stop = start + min(stops) if stops else len(text)
    if rendered:
        doc = Spans(text[start:stop])
        paragraphs = [n for n in doc.root.find(lambda n: n.attrs.get('data-summary-entry-paragraph') == 'true')
                      if n.start < stop - start]
        if paragraphs:
            if any(n.end is None for n in paragraphs):
                raise ValueError('Unclosed summary paragraph')
            return start + paragraphs[0].start, start + paragraphs[-1].end
        trees = [start + n.start for n in doc.root.find(lambda n: n.tag == 'pre' or n.attrs.get('data-summary-tree') == 'true')]
        if trees:
            stop = min(trees)
    while start < stop and text[start].isspace():
        start += 1
    while stop > start and text[stop - 1].isspace():
        stop -= 1
    return start, stop


def replacement(text, proposed, rendered=False):
    a, b = bounds(text, rendered)
    return text[:a] + proposed + text[b:]


def verify(formal, process, topic):
    formal, process = Path(formal).resolve(), Path(process).resolve()
    receipt_path = process / RECEIPT
    record = load(receipt_path)
    if str(topic).zfill(3) != record['topic'].split('_', 1)[0].zfill(3):
        raise ValueError('Summary receipt topic ID differs')
    approval = record['approval']
    for key in ('review', 'drafts'):
        if digest(approval[key]) != approval[key + '_sha256']:
            raise ValueError('Approved summary input changed: ' + key)
    drafts = load(approval['drafts'])
    matches = [r for r in drafts if r['database'] == record['database'] and r['topic'] == record['topic']]
    if len(matches) != 1 or matches[0].get('historical_split'):
        raise ValueError('No unique active approved introduction')
    draft = matches[0]
    proposed = draft['proposed']
    backup = Path(record['before'])
    if set(record['changed_files']) != {record['artifacts'][k] for k in ('copy', 'note')}:
        raise ValueError('Only the copy and main note may change')
    if str(formal) != str(Path(draft['path']).resolve()):
        raise ValueError('Approved topic identity differs')
    if set(p.name for p in formal.iterdir() if p.is_file()) != set(record['before_hashes']):
        raise ValueError('Formal artifact set changed')
    for filename, signature in record['before_hashes'].items():
        baseline = backup / filename if filename in record['changed_files'] else formal / filename
        if digest(baseline) != signature:
            raise ValueError('Summary baseline changed: ' + filename)
    for role, rendered in (('copy', False), ('note', True)):
        filename = record['artifacts'][role]
        old = (backup / filename).read_text(encoding='utf-8-sig')
        current = (formal / filename).read_text(encoding='utf-8-sig')
        value = record['rendered_summary'] if rendered else proposed
        if visible(value) != visible(proposed):
            raise ValueError('Rendered introduction differs from approved text')
        if replacement(old, value, rendered) != current:
            raise ValueError('Change outside approved introduction: ' + filename)
        if digest(backup / filename).lower() != draft['formal_bindings'][str(formal / filename)].lower():
            raise ValueError('Baseline differs from reviewed version')
    source = process / 'definition_search_record.json'
    if not record.get('source_sha256') and source.exists():
        raise ValueError('Source plan was added after the summary baseline')
    if record.get('source_sha256') and digest(source) != record['source_sha256']:
        raise ValueError('Source plan changed')
    if len(draft['numbered_results']) != draft['count'] or {r['variable'] for r in draft['numbered_results']} != set(draft['variables']):
        raise ValueError('Approved result identities are incomplete')
    return {'ok': True, 'status': 'SUMMARY_UPDATE_READY', 'topic_id': str(topic).zfill(3),
            'scope': 'summary_only', 'audit': str(receipt_path), 'audit_sha256': digest(receipt_path),
            'change_impact': {'path': RECEIPT, 'sha256': digest(receipt_path), 'changed_dimensions': ['summary']},
            'result_check': {'scope': 'summary_only', 'status': 'EXACT_REPLACEMENT_PASS'},
            'reader_review': {'status': 'USER_APPROVED_SUMMARY', 'review_sha256': approval['review_sha256']},
            'questionnaire_rendering': {'status': 'PRESERVED_BY_EXACT_TRANSFORMATION'},
            'artifacts': {role: {'path': name, 'sha256': digest(formal / name)}
                          for role, name in record['artifacts'].items() if role != 'copy'},
            'validation_basis': 'Approved introduction and exact preservation of all other content and artifacts; no fresh calculation review'}

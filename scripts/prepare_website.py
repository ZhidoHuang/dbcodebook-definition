"""Build a bound-tab, non-submitting website preparation action."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


def browser_code(action):
    base = action.get('base_url', '')
    url = urlsplit(base)
    if (url.scheme not in ('http', 'https') or not url.netloc or url.username
            or url.password or url.path not in ('', '/') or url.query or url.fragment):
        raise ValueError('base_url must be the website origin')
    create = action.get('create', False)
    post = str(action.get('post_id', ''))
    edit = action.get('edit_id')
    if not isinstance(create, bool) or (create and (post or edit is not None)):
        raise ValueError('create cannot be combined with post_id/edit_id')
    if not create and not re.fullmatch(r'(?:local-)?[1-9][0-9]*', post):
        raise ValueError('existing article requires a valid post_id')
    if edit is not None and (isinstance(edit, bool) or not re.fullmatch(r'[1-9][0-9]*', str(edit))):
        raise ValueError('edit_id must be an observed positive editor id')
    parts = action.get('identity_title_parts')
    if not create and (not isinstance(parts, list) or not parts
                       or any(not isinstance(x, str) or not x.strip() for x in parts)):
        raise ValueError('existing article requires identity_title_parts')
    action = {**action, 'base_url': base.rstrip('/'), 'post_id': post,
              'create': create, 'edit_id': str(edit) if edit is not None else None}
    root = Path(__file__).parent
    helper = (root / 'website_taxonomy.js').read_text(encoding='utf-8')
    prepare = (root / 'website_prepare.js').read_text(encoding='utf-8')
    return ('async page => {\n' + helper + '\n' + prepare
            + '\nreturn prepareWebsite(page, ' + json.dumps(action, ensure_ascii=False) + ');\n}')

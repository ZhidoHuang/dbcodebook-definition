"""Validate bound CHARLS mixed-source evidence by identity and period."""
from __future__ import annotations
import copy
from pathlib import Path
import re
from local_source_evidence import read_reference, validate_local_evidence
from source_read import saved_receipt

def validate_mixed(record, record_path):
    access = record['source_access']
    if record.get('database','').upper() != 'CHARLS' or access.get('mode') != 'mixed_charls_v1':
        raise ValueError('Unsupported mixed scope')
    base = Path(record_path).parent
    local = copy.deepcopy(record)
    local['source_access'] = {k:v for k,v in access['local'].items()}
    if local['source_access'].get('mode') != 'local_dictionary':
        raise ValueError('Invalid local mode')
    local_binding=read_reference(local['source_access']['binding'],base)
    # Use unchanged binding/receipt verification with synthetic claims derived
    # only from verified local detail requests; never write those claims out.
    claims=[]; local_cells={}
    for ref in local['source_access']['receipts']:
        data=read_reference(ref, base)
        if data.get('request',{}).get('kind') != 'detail':
            continue
        for row in data.get('sources',[]):
            by_identity={}
            for cell in row.get('periods',[]):
                if cell.get('available') is True:
                    requested=data['request'].get('periods')
                    if (cell.get('period') not in (requested if requested is not None else local_binding.get('periods',[])) or row.get('variable') != data['request'].get('variable') or row.get('file') != data['request'].get('file')):
                        raise ValueError('Local detail differs from request')
                    key=(cell['source_identity'],cell['period'])
                    if key in local_cells and local_cells[key] != cell:
                        raise ValueError('Conflicting local details')
                    local_cells[key]=cell
                    by_identity.setdefault(cell['source_identity'], []).append(cell['period'])
            for name, periods in by_identity.items():
                claims.append({'discovery':{'mode':'local_dictionary'},'source_identities':[name], 'periods':periods})
    local['source_groups']=claims
    local_info=validate_local_evidence(local, record_path)
    website=record['dbcodebook_url'].rstrip('/')
    web={}; web_directories=set(); web_keywords=set()
    for ref in access.get('web_receipts', []):
        state=read_reference(ref, base)
        binding=state.get('binding',{}); action=binding.get('action',{})
        if binding.get('database')!='charls' or binding.get('url','').rstrip('/')!=website or action.get('kind') not in ('detail','directory','search'):
            raise ValueError('Wrong web binding or type')
        if not re.fullmatch(r'[0-9a-f]{64}', str(binding.get('helper_sha256',''))):
            raise ValueError('Missing browser helper binding')
        completed=state.get('completed',[])
        if [x.get('index') for x in completed] != list(range(len(completed))):
            raise ValueError('Completed periods not sequential')
        if action['kind'] in ('directory','search'):
            if state.get('ok') is not True or len(completed)!=1 or state.get('pending') or state.get('failed'):
                raise ValueError('Web discovery is incomplete')
            receipt=saved_receipt(completed[0],state)
            if receipt.get('ok') is not True or receipt.get('operation_completed') is not True or receipt.get('action') != action:
                raise ValueError('Web discovery binding mismatch')
            if action['kind']=='directory':
                if receipt.get('status')!='DIRECTORY_READ' or receipt.get('path')!=action.get('path'):
                    raise ValueError('Web directory mismatch')
                web_directories.add(' > '.join(action['path']))
            else:
                if receipt.get('status')!='SEARCH_READ': raise ValueError('Web search mismatch')
                web_keywords.add(action.get('query'))
            continue
        periods=action.get('periods',[])
        for item in completed:
            index=item['index']
            if index >= len(periods): raise ValueError('Invalid completed index')
            receipt=saved_receipt(item,state); part=receipt.get('action',{})
            expected={**action,'periods':[periods[index]]}
            if receipt.get('ok') is not True or receipt.get('operation_completed') is not True or receipt.get('status')!='SOURCE_READ' or part != expected:
                raise ValueError('Invalid completed web receipt')
            name=f"{action['variable']} ({action['file']})"
            details=receipt.get('details',[])
            if len(details)!=1 or details[0].get('identity')!=name or details[0].get('period')!=periods[index] or details[0].get('status')!='DETAIL_READ':
                raise ValueError('Web detail mismatch')
            key=(name,periods[index]); detail=details[0]
            if key in web and web[key] != detail: raise ValueError('Conflicting web details')
            web[key]=detail
    if set(web) & set(local_cells):
        raise ValueError('Overlapping web/local detail needs explicit conflict review')
    plan=access.get('required_identity_periods')
    if not isinstance(plan,list) or not plan: raise ValueError('Explicit required plan missing')
    required=set()
    for row in plan:
        name=row.get('identity'); period=row.get('period'); channel=row.get('channel')
        key=(name,period)
        if not isinstance(name,str) or not isinstance(period,str) or key in required:
            raise ValueError('Invalid or duplicate required identity-period')
        required.add(key)
        if channel=='web': found=key in web
        elif channel=='local': found=period in local_info['sources'].get(name,set())
        else: raise ValueError('Unknown channel')
        if not found: raise ValueError('Missing required source identity-period')
    # Check source groups against explicit plan. Completeness of individual
    # source/period declarations still requires separately verified planning.
    grouped=set()
    for group in record.get('source_groups',[]):
        names=group.get('source_identities',[]); periods=set(group.get('periods',[]))
        if len(names)!=1: raise ValueError('Mixed mode requires one exact identity per source group')
        for name in names:
            represented={p for n,p in required if n==name and p in periods}
            if not represented: raise ValueError('Group identity not represented')
            grouped.update((name,p) for p in represented)
        if not periods.issubset({p for n,p in grouped if n in names}):
            raise ValueError('Group period not represented')
    if grouped != required: raise ValueError('Plan differs from source group scope')
    return {'sources':required,'directories':local_info['directories'],'keywords':local_info['keywords'],
            'mixed':True,'web_directories':web_directories,'web_keywords':web_keywords}

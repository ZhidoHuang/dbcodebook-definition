import copy,hashlib,json
from pathlib import Path
from source_read import receipt_hash

def exercise(checker, original, folder, selection_path):
    root=Path(folder); data=copy.deepcopy(original)
    def save(name,obj):
        p=root/name;p.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8')
        return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    binding={'schema':'dbcodebook.local-binding.v1','ok':True,'database':'charls','language':None,
        'website_url':'http://localhost:8000/home/charls/','dictionary_sha256':'a'*64,
        'mapping':{'kind':'runtime_settings_same_file'}}
    bref=save('fixture_binding.json',binding)
    local={'schema':'dbcodebook.local-source.v1','ok':True,'database':'charls','language':None,
        'binding_sha256':bref['sha256'],'dictionary_sha256':'a'*64,
        'request':{'kind':'detail','variable':'FA002','file':'F','periods':['2013']},
        'sources':[{'variable':'FA002','file':'F','periods':[{'period':'2013','available':True,'actual_variable':'FA002','source_identity':'FA002 (F)'}]}]}
    lref=save('fixture_local.json',local)
    def web(action,payload):
        receipt={'action':action,**payload};state={'ok':True,'status':receipt['status'],
            'binding':{'action':action,'database':'charls','url':'http://localhost:8000/home/charls/','helper_sha256':'a'*64},
            'completed':[{'index':0,'sha256':receipt_hash(receipt),'result':dict(receipt)}],'pending':None,'failed':None}
        if action['kind']=='detail':
            state['details']=state['completed'][0]['result'].pop('details');state['completed'][0]['details_slice']=[0,1]
        else:
            keys=[k for k in receipt if k not in ('action','ok','status')];state['completed'][0]['fields']=keys
            for key in keys:state[key]=state['completed'][0]['result'].pop(key)
        return state
    action={'kind':'detail','variable':'FA002','file':'F','periods':['2011']}
    wref=save('fixture_web.json',web(action,{'ok':True,'status':'SOURCE_READ','operation_completed':True,'details':[{'identity':'FA002 (F)','period':'2011','status':'DETAIL_READ'}]}))
    directory={'kind':'directory','path':['Core data','Work']}
    dref=save('fixture_directory.json',web(directory,{'ok':True,'status':'DIRECTORY_READ','path':directory['path'],'children':[],'results':{},'operation_completed':True}))
    data['source_groups'][0]['source_identities']=['FA002 (F)']
    data['source_groups'][0]['discovery']={'mode':'directory','value':'Core data > Work'}
    data['source_access']={'mode':'mixed_charls_v1','local':{'mode':'local_dictionary','binding':bref,'receipts':[lref]},
        'web_receipts':[wref,dref],'required_identity_periods':[{'identity':'FA002 (F)','period':'2011','channel':'web'},{'identity':'FA002 (F)','period':'2013','channel':'local'}]}
    data['normal_searches']=[{'performed':False,'reason':'Synthetic fixture uses a directory'}]
    record=root/'fixture_record.json';record.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    assert checker.validate_download_selection(record,selection_path,'001')['ok']
    search_action={'kind':'search','query':'work'}
    search_ref=save('fixture_search.json',web(search_action,{'ok':True,'status':'SEARCH_READ','query':'work','results':{},'operation_completed':True}))
    search_case=copy.deepcopy(data);search_case['source_access']['web_receipts'].append(search_ref)
    search_case['source_groups'][0]['discovery']={'mode':'ordinary_search','value':'work'}
    search_case['normal_searches']=[{'performed':True,'keyword':'work','result':'synthetic source'}]
    record.write_text(json.dumps(search_case,ensure_ascii=False),encoding='utf-8')
    assert checker.validate_download_selection(record,selection_path,'001')['ok']
    search_case['source_access']['web_receipts'].pop()
    record.write_text(json.dumps(search_case,ensure_ascii=False),encoding='utf-8')
    try:checker.validate_download_selection(record,selection_path,'001')
    except ValueError as e: assert 'web search requires' in str(e)
    else:raise AssertionError('missing search evidence accepted')
    wrong=copy.deepcopy(data);wrong['source_groups'][0]['discovery']['mode']='local_dictionary'
    record.write_text(json.dumps(wrong,ensure_ascii=False),encoding='utf-8')
    try:checker.validate_download_selection(record,selection_path,'001')
    except ValueError as e: assert 'Mixed local discovery' in str(e)
    else:raise AssertionError('web directory falsely accepted as local discovery')
    data['source_access']['required_identity_periods'].pop()
    record.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    try:checker.validate_download_selection(record,selection_path,'001')
    except ValueError as e: assert 'period not represented' in str(e)
    else:raise AssertionError('full gate accepted missing identity period')
    print('SYNTHETIC_MIXED_FULL_DOWNLOAD_GATE_PASS')

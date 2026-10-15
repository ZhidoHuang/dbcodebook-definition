"""Synthetic SHARE contract cases. No real respondents or website downloads."""
import copy,csv,io,json,os,subprocess,sys,tempfile,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
from share_export_contract import validate_unique_package, validate_unique_preview
from recover_dbcodebook_export import inspect_archive, install_archive
from check_definition_output import check_identity_values
from prepare_source_selection import build_record_action

def must_fail(fn, fragment):
    try: fn()
    except ValueError as e:
        assert fragment in str(e),(fragment,str(e))
    else: raise AssertionError('Invalid fixture accepted: '+fragment)

def write_csv(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f: csv.writer(f).writerows(rows)

def main():
    header=['ID','Wave_id','mergeid','hhid','country','intid (A)','intid (B)','answer']
    # Non-reconstructed IDs and a leading-zero person ID reused across waves.
    rows=[['opaque-alpha','Wave 1','000012','001','01','07','008','Yes'],
          ['opaque-beta','Wave 2','000012','002','01','09','010','Refusal']]
    cbheader=['Variable','Label','Period','File type','Match key','newname']
    cbrows=[['x (A)','Answer','Wave 1, Wave 2','uniqID','Wave_id + mergeid（ID）','answer']]
    # Only dictionaries may authorize scoped interviewer identifiers.
    header.remove('intid (B)'); [row.pop(6) for row in rows]
    with tempfile.TemporaryDirectory(prefix='share_adapter_fixture_') as tmp:
        d=Path(tmp);write_csv(d/'raw_data.csv',[header,*rows]);write_csv(d/'raw_codebook.csv',[cbheader,*cbrows])
        result=validate_unique_package(d,['raw_data.csv'],['answer']);assert result['rows']==2
        z=d/'fixture.zip'
        with zipfile.ZipFile(z,'w') as f:
            for name in ['raw_data.csv','raw_codebook.csv']: f.write(d/name,name)
        assert inspect_archive(z,['answer'],'share')['data']['raw_data.csv']['rows']==2
        must_fail(lambda:validate_unique_package(d,['raw_data.csv','raw_data_country.csv'],['answer']),'one personal')
        for altered,fragment in [([rows[0],rows[0]],'duplicate'),
                                 ([rows[0],['different','Wave 1',*rows[0][2:]]],'duplicate'),
                                 ([['x','Corona Survey 1',*rows[0][2:]]],'unsupported period'),
                                 ([['x','Wave 1','',*rows[0][3:]]],'empty identity')]:
            write_csv(d/'raw_data.csv',[header,*altered]);must_fail(lambda:validate_unique_package(d,['raw_data.csv'],['answer']),fragment)
        write_csv(d/'raw_data.csv',[header,*rows])
        write_csv(d/'raw_codebook.csv',[cbheader,[*cbrows[0][:3],'countryID',*cbrows[0][4:]]])
        must_fail(lambda:validate_unique_package(d,['raw_data.csv'],['answer']),'personal uniqID')
        write_csv(d/'raw_codebook.csv',[cbheader,*cbrows])
        out=[];check_identity_values(d/'raw_data.csv',header,[['ID','Wave_id','mergeid'],['opaque-beta','Wave 2','000012']],['ID','Wave_id','mergeid'],out,'share')
        assert all(x['ok'] for x in out),out
        out=[];check_identity_values(d/'raw_data.csv',header,[['ID','Wave_id','mergeid'],['opaque-beta','Wave 1','000012']],['ID','Wave_id','mergeid'],out,'share')
        assert any(not x['ok'] for x in out),out
        preview={'selected_variables':1,'preview_variables':1,'variables_limited':False,'total_files':2,'files':[
            {'file_type':'uniqID','columns':header,'rows':rows,'preview_rows':2,'total_rows':2,'match_key':'Wave_id + mergeid（ID）','file_list':['A'],'variables':['x']},
            {'file_type':'dictionary','columns':cbheader,'rows':cbrows,'preview_rows':1,'total_rows':1}]}
        assert validate_unique_preview(preview,{'x (A)':'answer'})['full_file_verified'] is False
        bad=copy.deepcopy(preview);bad['files'][0]['match_key']='Wave_id + country'
        must_fail(lambda:validate_unique_preview(bad,{'x (A)':'answer'}),'match key')
        bad=copy.deepcopy(preview);bad['variables_limited']=True
        must_fail(lambda:validate_unique_preview(bad,{'x (A)':'answer'}),'limited')
        # New downloads move period and connection metadata to the original HTML note.
        newheader=['Variable','Label','File type','newname']
        newrows=[['x (A)','Answer','uniqID','answer']]
        note=('SHARE 连接说明\n文件信息\n① raw_data.csv\n记录单位：受访者 × 调查时期\n'
              '变量来源\n连接键：ID = Wave_id + "_" + mergeid\n'
              '├─ sharew1_rel9-0-0_a.dta [Wave 1]\n│  └─ x → answer\n'
              '└─ sharew2_rel9-0-0_a.dta [Wave 2]\n   └─ x → answer\n')
        from html import escape
        def save_note(text):
            (d/'连接说明.html').write_text('<div>'+escape(text)+'</div>',encoding='utf-8')
        write_csv(d/'raw_codebook.csv',[newheader,*newrows])
        must_fail(lambda:validate_unique_package(d,['raw_data.csv'],['answer']),'requires 连接说明')
        save_note(note)
        assert validate_unique_package(d,['raw_data.csv'],['answer'])['rows']==2
        newpreview=copy.deepcopy(preview)
        newpreview['files'][1].update(columns=newheader,rows=newrows)
        newpreview['files'].append({'file_type':'connection_note','text':note})
        newpreview['total_files']=3
        assert validate_unique_preview(newpreview,{'x (A)':'answer'})['full_file_verified'] is False
        for altered,fragment in [(note.replace('mergeid','country'),'match key/unit'),
                                 (note.replace('Wave 2','Wave 10'),'ordinary Wave'),
                                 (note.replace('─ x','─ other'),'provenance'),
                                 (note.replace('→ answer','→ wrong_alias'),'provenance')]:
            save_note(altered)
            must_fail(lambda:validate_unique_package(d,['raw_data.csv'],['answer']),fragment)
        save_note(note.split('└─ sharew2')[0])
        must_fail(lambda:validate_unique_package(d,['raw_data.csv'],['answer']),'raw periods differ')
        save_note(note)
        write_csv(d/'raw_codebook.csv',[newheader+['Period'],newrows[0]+['Wave 1, Wave 2']])
        must_fail(lambda:validate_unique_package(d,['raw_data.csv'],['answer']),'both Period and Match key')
        write_csv(d/'raw_codebook.csv',[newheader,['x (A)','Answer','reID','answer']])
        must_fail(lambda:validate_unique_package(d,['raw_data.csv'],['answer']),'personal uniqID')
        write_csv(d/'raw_codebook.csv',[newheader,*newrows])
        with zipfile.ZipFile(z,'w') as f:
            for name in ['raw_data.csv','raw_codebook.csv','连接说明.html']: f.write(d/name,name)
        assert inspect_archive(z,['answer'],'share')['data']['raw_data.csv']['rows']==2
        installed=d/'installed';installed.mkdir()
        install_archive(z,installed)
        for name in ['raw_data.csv','raw_codebook.csv','连接说明.html']:
            assert (installed/name).read_bytes()==(d/name).read_bytes()
    action=build_record_action({'status':'READY','source_groups':[{'source_identities':['x (A)'],'raw_variables':['answer']}]},'https://example.test/home/share/')
    assert action['input_text']=='x (A)=answer'
    r=os.environ.get('RSCRIPT')
    if r:
        env=os.environ.copy()
        for key in ('LC_ALL','LANG','LC_CTYPE'): env.pop(key,None)
        subprocess.run([r,'--vanilla','--encoding=UTF-8','tests/test_share_renderer.R'],cwd=root,env=env,check=True)
    else: print('SHARE_RENDERER_SKIP: RSCRIPT not configured')
    print('SHARE synthetic export/preview/identity fixtures PASS; no real-download acceptance')
    return 0

if __name__=='__main__': raise SystemExit(main())

"""NHIS selection/export boundary tests using disposable metadata and CSV fixtures."""
import copy
import csv
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from nhis_export_contract import build_selection, validate_selection, validate_package, page_url
from prepare_source_selection import browser_code
from definition_display import display_periods
from check_definition_source_record import validate_questionnaire_evidence


def reject(fn):
    try: fn()
    except (ValueError,KeyError): return
    raise AssertionError('Invalid NHIS context accepted')


def main():
    entries=[]
    for suffix,period in [('fy','1968FY'),('cy','1968CY')]:
        ident='NHIS_'+suffix
        entries.append(dict(variable_id=ident,variable='AGE',file='Person core',alias='age_'+suffix,periods=[period],
            source_mappings=[{'调查期间':period,'来源文件标识':'Person_'+period,'原变量名':'AGE',
                '合并文件':'person.parquet','合并变量名':'AGE_'+suffix,'Variable_id':ident,
                '编码版本':suffix,'hrs_style_id_type':'唯一个人ID'}]))
    record={'database':'NHIS','dataset_id':'nhis_pre1997','status':'READY',
        'source_groups':[{'source_identities':['AGE (Person core)','AGE (Person core)'],
                          'raw_variables':['age_fy','age_cy'],'periods':['1968FY','1968CY']}],
        'nhis_selection':{'dictionary_sha256':'a'*64,'inputs':entries}}
    action=build_selection(record,page_url('https://example.test','nhis_pre1997'))
    assert len(action['selected'])==2 and 'NHIS_fy' in action['input_text']
    assert 'nhis_identity_selection_v1' in browser_code(action,'select')
    for field,value in [('dataset_id','nhis_2019_plus'),('url','https://example.test/home/nhis/'),('input_text','AGE (Person core)=age')]:
        reject(lambda field=field,value=value:validate_selection({**action,field:value}))
    for field,value in [('periods',['2099']),('alias','ID'),('variable_id','wrong')]:
        bad=copy.deepcopy(action);bad['selected'][0][field]=value
        reject(lambda:validate_selection(bad))
    assert display_periods('NHIS',dataset_id='nhis_pre1997')[5:7]==['1968FY','1968CY']
    reject(lambda:page_url('https://example.test',None))
    # Questionnaire evidence must not access an unrelated, unbound URL local.
    reject(lambda:validate_questionnaire_evidence(
        {'database':'NHIS','questionnaire_evidence':None},
        [{'step':1,'action':'official_material_review'}],{}))
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        with (root/'raw_codebook.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['Variable','Label','newname'])
            writer.writerows([['AGE (Person core)','Age','age_fy'],['AGE (Person core)','Age','age_cy']])
        header=['ID','Wave_id','Survey_year','age_fy','age_cy']
        rows=[['1968FY:person:001','1968FY','1968','40',''],['1968CY:person:001','1968CY','1968','','41']]
        def write(values):
            with (root/'raw_data.csv').open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(header);writer.writerows(values)
        write(rows)
        result=validate_package(root,['raw_data.csv','raw_codebook.csv'],action['aliases'],'nhis_pre1997',action)
        assert result['source_identity_check']=='selected_manifest'
        write([rows[0],rows[0]]);reject(lambda:validate_package(root,['raw_data.csv'],action['aliases'],'nhis_pre1997',action))
        write([[*rows[0][:2],'1969',*rows[0][3:]]]);reject(lambda:validate_package(root,['raw_data.csv'],action['aliases'],'nhis_pre1997',action))
        write(rows);reject(lambda:validate_package(root,['raw_data.csv','raw_data_events.csv'],action['aliases'],'nhis_pre1997',action))
    print('NHIS adapter boundary fixtures PASS; no real data or browser export')


if __name__=='__main__': main()

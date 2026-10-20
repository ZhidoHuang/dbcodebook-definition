"""Physical-column UI contract; business periods remain a separate decision."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_source_selection import build_record_action,browser_code

def record():
    return {'database':'MHAS','status':'READY','source_groups':[
        {'source_identities':['c54 (Core)'],'raw_variables':['c54']}],
        'mhas_selection':{'mode':'raw_columns','dictionary_sha256':'a'*64,'inputs':[{
            'variable_id':'c54_Core','file':'Core','available_periods':['2001','2003'],
            'available_bindings':{'2001':'c54','2003':'c54'},
            'period_bindings':{'2001':'c54'},'aliases':{'c54':'c54'}}]}}

class RawTests(unittest.TestCase):
    def test_business_scope_does_not_become_full_raw_scope(self):
        a=build_record_action(record(),'http://fixture/')
        self.assertEqual(a['input_text'],'c54 (Core)=c54')
        self.assertEqual(a['selected'][0]['periods'],['2001','2003'])
        self.assertEqual(a['selected'][0]['business_periods'],['2001'])

    def test_repeated_column_needs_one_alias(self):
        r=record();r['source_groups'].append({'source_identities':['c54 (Core)'],'raw_variables':['current']})
        with self.assertRaisesRegex(ValueError,'one shared alias'):build_record_action(r,'http://fixture/')
        r['source_groups'][-1]['raw_variables']=['c54']
        self.assertEqual(len(build_record_action(r,'http://fixture/')['selected']),1)

    def test_business_binding_and_action_tampering_rejected(self):
        r=record();r['mhas_selection']['inputs'][0]['period_bindings']['2001']='wrong'
        with self.assertRaises(ValueError):build_record_action(r,'http://fixture/')
        a=build_record_action(record(),'http://fixture/');a['selected'][0]['periods']=['2001']
        with self.assertRaises(ValueError):browser_code(a,'select')

    def test_actual_column_api_periods_and_ui_alias_are_checked(self):
        a=build_record_action(record(),'http://fixture/')
        fixture=r'''
const assert=require('node:assert/strict');const run=ACTION;
async function scenario(change={}) {
 let clicks=0;
 const row={variable:'c54',file:'Core',wave:'2001, 2003',raw_column:true,input:'c54 (Core)',...change.api};
 const dom={variable:'c54',file:'Core',alias:'c54',...change.dom};
 const locator=s=>({count:async()=>1,isVisible:async()=>false,waitFor:async()=>{},
   fill:async x=>assert.equal(x,'c54 (Core)=c54'),click:async()=>{clicks++;},
   evaluateAll:async(fn,arg)=>fn([{dataset:{},getAttribute:k=>dom[k.replace('data-','').replace('display','alias')],
     querySelector:()=>({textContent:dom.alias})}],arg)});
 const page={url:()=> 'http://fixture/',evaluate:async()=>true,locator,
 getByRole:()=>locator('open'),waitForResponse:async p=>{
 const response={url:()=> 'http://fixture/validate_tags/',request:()=>({method:()=> 'POST'}),
  ok:()=>true,json:async()=>({valid_tags:[row],invalid_tags:[]})};assert.equal(p(response),true);return response;}};
 const result=await run(page);assert.equal(clicks,2);return result;
}
(async()=>{
 const ok=await scenario();assert.equal(ok.status,'SELECTION_READY');assert.equal(ok.validated_sources[0].periods.length,2);
 for(const change of [{api:{wave:'2001'}},{api:{variable:'other'}},{api:{file:'Other'}},
 {api:{raw_column:false}},{api:{input:'wrong (Core)'}},{dom:{alias:'other'}}])
  assert.equal((await scenario(change)).status,'SELECTION_CONTENT_MISMATCH');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'raw.cjs';p.write_text(fixture.replace('ACTION',browser_code(a,'select')),encoding='utf-8')
            x=subprocess.run(['node',str(p)],capture_output=True,text=True)
            self.assertEqual(x.returncode,0,x.stderr)

if __name__=='__main__':unittest.main()

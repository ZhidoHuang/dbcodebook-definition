"""Exercise dropdown decisions and clicks without creating website records."""
import json
import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from skill_config import load_config, configured_executable

def main():
    node = configured_executable(load_config(None), 'node') or shutil.which('node')
    if not node:
        raise RuntimeError('Node is required for website taxonomy tests')
    code = r'''
const assert = require('node:assert/strict');
const {resolveWebsiteTaxonomy:resolve, applyWebsiteTaxonomy:apply, verifyWebsiteTaxonomy:verify} = require(HELPER);
assert.deepEqual(resolve({value:' medical ',mode:'create'},['Medical']),{value:'Medical',mode:'existing'});
assert.throws(()=>resolve({value:'mental',mode:'existing'},['medical']),/NO_MATCH/);
assert.throws(()=>resolve({value:'medical',mode:'existing'},['medical','Medical']),/AMBIGUOUS/);
assert.throws(()=>resolve({value:'new',mode:'create'},[]),/REQUIRES_REVIEW/);
assert.throws(()=>resolve({value:'new',mode:'create',options:[],reason:'checked'},['added']),/OPTIONS_CHANGED/);
assert.deepEqual(resolve({value:'孤独感',mode:'create',options:['生活质量'],reason:'量表概念不同'},['生活质量']),{value:'孤独感',mode:'create'});

// The mock exposes only normal locator clicks; hidden-value writes and Enter are unavailable.
function fixture() {
 const state={directory_tag:{current:'old',options:['Medical']},cross_database_topic:{current:'old topic',options:['生活质量']}};
 const clicks=[];let active,query,shown=[];
 const api={evaluate:async(fn,arg)=>{
   if(arg) {
     const existing=state[active].options.filter(x=>x.toLowerCase().includes(query.toLowerCase()));
     shown=arg.endsWith(':not(.is-create)')?existing:(state[active].options.includes(query)?[]:[query]);
     return shown;
   }
   return JSON.parse(JSON.stringify(state));
 },locator:selector=>({
   click:async()=>{active=selector==='#directory-tag-trigger'?'directory_tag':'cross_database_topic';clicks.push(selector);},
   fill:async value=>{query=value;},
   nth:index=>({click:async()=>{state[active].current=shown[index];clicks.push(selector);}})
 })};
 return {tab:{playwright:api},state,clicks};
}
(async()=>{
 let f=fixture();
 let decisions=await apply(f.tab,{directory_tag:{value:'medical',mode:'existing'},cross_database_topic:{value:'孤独感',mode:'create',options:['生活质量'],reason:'不同测量概念'}});
 assert.equal(f.state.directory_tag.current,'Medical');assert.equal(f.state.cross_database_topic.current,'孤独感');
 assert(f.clicks.some(x=>x.endsWith(':not(.is-create)')));assert(f.clicks.some(x=>x.endsWith('.is-create')));
 await verify(f.tab,decisions);
 f.state.cross_database_topic.current='changed';await assert.rejects(()=>verify(f.tab,decisions),/CHANGED_BEFORE_SUBMIT/);
 f=fixture();await assert.rejects(()=>apply(f.tab,{directory_tag:{value:'Medical',mode:'existing'},cross_database_topic:{value:'新建',mode:'create',options:[],reason:'旧列表'}}),/OPTIONS_CHANGED/);assert.equal(f.clicks.length,0);
 f=fixture();await apply(f.tab,{directory_tag:{value:'Medical',mode:'existing'}});assert.equal(f.state.cross_database_topic.current,'old topic');
 console.log('WEBSITE_TAXONOMY_PASS: existing, create, ambiguity, stale options, unchanged field, final mismatch');
})().catch(e=>{console.error(e);process.exit(1);});
'''.replace('HELPER', json.dumps(str(ROOT / 'scripts/website_taxonomy.js')))
    subprocess.run([node, '-e', code], check=True)

if __name__ == '__main__':
    main()

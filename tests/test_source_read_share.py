"""SHARE tooltip matching includes missing labels and does not invent count semantics."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source_read import browser_code


def main():
    url = "http://localhost:8000/home/share/"
    action = {"kind": "detail", "variable": "euro1", "file": "Generated health variables", "periods": ["Wave 1"]}
    fixture = r"""
const assert = require('node:assert/strict');
const run = RUN;
const url = SITE;
async function scenario(stale=false, noDistribution=false) {
  const calls=[], listeners=new Map(), heads=['Wave 1','Variable','File'];
  const row={Variable:'euro1',File:'Generated health variables','Wave 1':'5',
    'Wave 1_label':'Depression', 'Wave 1_summary':"Refusal ( 2 ), Don't know ( 1 ), Not selected ( 3 ), Selected ( 2 )"};
  const dist=[['Refusal',2],["Don't know",1],['Not selected',3],['Selected',stale?9:2]];
  const cells=['5','euro1','Generated health variables'].map(innerText=>({innerText}));
  const header=heads.map(innerText=>({innerText,getAttribute:()=>innerText}));
  let visible=false, query='', resolve;
  const card={innerText:'complete tooltip', getClientRects:()=>visible?[{}]:[],
    querySelector:s=>s==='.tooltip-title'?{textContent:'euro1'}:s==='.tooltip-item.label'?{textContent:'Depression'}:null,
    querySelectorAll:()=>noDistribution?[]:dist.map(([label,count])=>({querySelector:s=>({textContent:s==='.code-cell'?label:String(count)})}))};
  const tableDOM={querySelectorAll:s=>s==='thead th'?header:[{querySelectorAll:()=>cells}]};
  global.document={querySelector:()=>tableDOM,querySelectorAll:()=>[card]};
  const request={url:()=>url,method:()=> 'POST',postDataJSON:()=>({search:query,page:1})};
  const response={url:()=>url,request:()=>request,ok:()=>true,status:()=>200,
    json:async()=>({data:[row],total_pages:1,total_results:1})};
  const page={url:()=>url,evaluate:async()=>true,on:(k,v)=>listeners.set(k,v),off:k=>listeners.delete(k),
    waitForResponse:()=>new Promise(r=>resolve=r),
    waitForFunction:async(fn,arg)=>{if(!fn(arg))throw Error('mismatched DOM')},
    getByRole:()=>({click:async()=>{calls.push('search');listeners.get('request')(request);resolve(response)}}),
    locator:s=>s==='#search'?{fill:async x=>query=x,click:async()=>{visible=false}}:
      s==='#results-table'?{count:async()=>1,locator:s=>s==='thead th'?{evaluateAll:async fn=>fn(header)}:
        {nth:()=>({locator:()=>({nth:()=>({hover:async()=>{calls.push('detail');visible=true}})})})}}:
      {count:async()=>0,evaluateAll:async fn=>fn([card])}};
  const result=await run(page);
  assert.equal(listeners.size,0);
  assert.deepEqual(calls,['search','detail']);
  return result;
}
(async()=>{
  const good=await scenario();
  assert.equal(good.status,'SOURCE_READ',JSON.stringify(good));
  assert.equal(good.details[0].count,'5');
  assert.equal(good.details[0].distribution.reduce((n,x)=>n+Number(x.count),0),8);
  assert.equal(good.details[0].source_row['Wave 1_summary'],good.details[0].summary);
  assert.equal((await scenario(true)).status,'DETAIL_CONTENT_MISMATCH');
  assert.equal((await scenario(false,true)).status,'DETAIL_CONTENT_MISMATCH');
  // First read is genuinely in flight while the second reaches the same page.
  let release, authCalls=0;
  const page={url:()=>url,evaluate:()=>{authCalls++;return new Promise(r=>release=r)}};
  const first=run(page);
  assert.equal((await run(page)).status,'READ_BUSY');
  assert.equal(authCalls,1,'Second action touched the browser');
  release(false);
  assert.equal((await first).status,'LOGIN_REQUIRED');
  const third=run(page);release(false);
  assert.equal((await third).status,'LOGIN_REQUIRED');
  console.log('SHARE_SOURCE_READ_PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
""".replace("RUN", browser_code(action, url, "share"), 1).replace("SITE", json.dumps(url), 1)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "share.cjs"
        path.write_text(fixture, encoding="utf-8")
        subprocess.run(["node", str(path)], check=True)


if __name__ == "__main__":
    main()

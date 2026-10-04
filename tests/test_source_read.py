"""Offline source-reading failure cases; actual CHARLS smoke evidence is recorded separately."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from source_read import browser_code


def main():
    url = 'http://localhost:8000/home/charls/'
    action = {'kind':'detail', 'variable':'q1', 'file':'Core', 'periods':['2011','2014']}
    for invalid in [{}, {'kind':'search','query':'x'}, {'kind':'directory','path':['a[b]']},
                    {**action,'periods':['2011']*7}, {**action,'periods':[{}]},
                    {**action,'file':'Core] OR other['}]:
        try:
            browser_code(invalid, url, 'charls')
        except ValueError:
            pass
        else:
            raise AssertionError(invalid)
    try:
        browser_code(action, url, 'elsa')
    except ValueError:
        pass
    else:
        raise AssertionError('Unverified database accepted')
    fixture = r'''
const assert = require('node:assert/strict');
const run = RUN_CODE;
const searchRun = SEARCH_CODE;
async function scenario(o={}, runner=run) {
 const calls=[];
 const row={Variable:'q1',File:'Core','2011':'5','2014':null,
   '2011_label':'question','2011_summary':'1 yes ( 5 )','2011_text':'Q1 yes -> Skip to Q2'};
 const rows=o.absent ? [] : [row];
 const heads=o.noHeaders?[]:['2011','2014','Variable','File'];
 const cells=['5','','q1',o.stale?'Other':'Core'].map(innerText=>({innerText}));
 let cardVisible=!o.clickRequired;
 const card={querySelector:s=>({textContent:({'.variable':'q1 (Core)','.year':'[2011]',
   '.label-text':'question','.summary-text':o.badSummary?'old':row['2011_summary'],
   '.year-text':row['2011_text']})[s]})};
 const emptyRow={innerText:'no result',querySelector:s=>s==='td[colspan]'?{}:null};
 const tableDOM={querySelectorAll:s=>s==='thead th'?heads.map(innerText=>({innerText})):
   o.absent&&!o.staleEmpty?(o.emptyMessage?[emptyRow]:[]):[{querySelectorAll:()=>cells,querySelector:()=>null}]};
 global.document={querySelector:()=>tableDOM,querySelectorAll:()=>cardVisible?[card]:[]};
 let pending, predicate, query='';
 const timeout = message => Object.assign(new Error(message),{name:'TimeoutError'});
 const request={url:()=>SITE_URL,method:()=> 'POST',postDataJSON:()=>({search:query,page:1}),failure:()=>({errorText:'net::ERR_CONNECTION_RESET'})};
 const response={url:()=>SITE_URL,status:()=>o.httpFail?503:200,ok:()=>!o.httpFail,json:async()=>{
   if(o.badJson)throw Error('invalid body');return {status:o.rejected?'fail':'success',data:rows,total_pages:1,total_results:rows.length}},
   request:()=>request};
 const cell={click:async()=>{calls.push('detail');if(o.clickUnstable)throw timeout('element is not stable');cardVisible=!o.missingCard;}};
 const table={count:async()=>1,locator:s=>s==='thead th'?{evaluateAll:async fn=>fn(heads.map(innerText=>({innerText})))}:
   {nth:()=>({locator:()=>({nth:()=>cell})})}};
 const boxes={evaluateAll:async(fn,arg)=>fn(cardVisible?[card]:[],arg)};
 const handlers=new Map();
 const page={on:(event,fn)=>handlers.set(event,fn),off:(event,fn)=>{assert.equal(handlers.get(event),fn);handlers.delete(event)},
   url:()=>o.wrongPage?'http://localhost:8000/home/elsa/':SITE_URL,
   evaluate:async()=>o.auth===undefined?true:o.auth,
   locator:s=>s==='#results-table'?table:s==='#search'?{fill:async x=>{query=x;calls.push('fill')}}:boxes,
   waitForResponse:fn=>{calls.push('listen');predicate=fn;
     if(o.waitFailure)return Promise.reject(Object.assign(new Error('page closed'),{name:'TargetClosedError'}));
     return new Promise(resolve=>{pending=resolve})},
   getByRole:()=>({click:async()=>{assert.ok(calls.includes('listen'));calls.push('search');
     if(o.searchClickFail)throw timeout('search button not stable');
     if(!o.noRequest)handlers.get('request')?.(request);
     if(o.requestFail)handlers.get('requestfailed')?.(request);
     assert.ok(predicate(response));pending?.(o.noResponse?null:response)}}),
   waitForFunction:async(fn,arg)=>{if(!fn(arg))throw timeout('visible content not current');}
 };
 const result=await runner(page);assert.equal(handlers.size,0,'request listeners leaked');return {result,calls};
}
(async()=>{
 let x=await scenario({clickRequired:true});assert.equal(x.result.status,'SOURCE_READ',JSON.stringify(x.result));
 assert.equal(x.result.details[1].status,'NO_RECORDS');
 assert.equal(x.result.details[0].source,'Q1 yes -> Skip to Q2');
 assert.deepEqual(x.calls,['fill','listen','search','detail']);
 assert.equal((await scenario({stale:true})).result.status,'READ_INCOMPLETE');
 assert.equal((await scenario({badSummary:true})).result.status,'DETAIL_CONTENT_MISMATCH');
 assert.equal((await scenario({absent:true})).result.status,'SOURCE_AMBIGUOUS_OR_NOT_ON_PAGE');
 assert.equal((await scenario({noResponse:true})).result.status,'READ_INCOMPLETE');
 assert.equal((await scenario({rejected:true})).result.status,'READ_INCOMPLETE');
 x=await scenario({auth:false});assert.equal(x.result.status,'LOGIN_REQUIRED');assert.equal(x.calls.length,0);
 x=await scenario({wrongPage:true});assert.equal(x.result.status,'WRONG_PAGE');assert.equal(x.calls.length,0);
 assert.equal((await scenario({},searchRun)).result.status,'SEARCH_READ');
 x=await scenario({absent:true,noHeaders:true,emptyMessage:true},searchRun);
 assert.equal(x.result.status,'SEARCH_READ',JSON.stringify(x.result));
 assert.equal(x.result.total_results,0);assert.deepEqual(x.result.rows,[]);
 assert.equal((await scenario({absent:true,noHeaders:true},searchRun)).result.status,'SEARCH_READ');
 assert.equal((await scenario({absent:true,noHeaders:true,emptyMessage:true})).result.status,'SOURCE_AMBIGUOUS_OR_NOT_ON_PAGE');
 assert.equal((await scenario({absent:true,staleEmpty:true},searchRun)).result.status,'READ_INCOMPLETE');
 assert.equal((await scenario({noHeaders:true},searchRun)).result.status,'READ_INCOMPLETE');
 for(const [options,code] of [
   [{noResponse:true,noRequest:true},'SEARCH_REQUEST_NOT_OBSERVED'],
   [{noResponse:true},'SEARCH_RESPONSE_TIMEOUT'],
   [{noResponse:true,requestFail:true},'SEARCH_REQUEST_FAILED'],
   [{waitFailure:true},'SEARCH_RESPONSE_WAIT_FAILED'],
   [{httpFail:true},'SEARCH_HTTP_ERROR'],
   [{badJson:true},'SEARCH_RESPONSE_NOT_JSON'],
   [{rejected:true},'SEARCH_REJECTED'],
   [{stale:true},'SEARCH_TABLE_TIMEOUT'],
   [{searchClickFail:true},'SEARCH_CLICK_TIMEOUT'],
   [{clickRequired:true,clickUnstable:true},'DETAIL_CLICK_TIMEOUT'],
   [{clickRequired:true,missingCard:true},'DETAIL_CARD_TIMEOUT']]) {
   x=await scenario(options);assert.equal(x.result.error_code,code,JSON.stringify(x.result));
   assert.equal(x.calls.filter(c=>c==='search').length,1,'Search was replayed');
   assert.ok(x.result.diagnostics.elapsed_ms>=0);
   assert.ok(x.result.message.length>0);
 }
 x=await scenario({httpFail:true});assert.equal(x.result.diagnostics.searches[0].http_status,503);
 x=await scenario({clickRequired:true,clickUnstable:true});
 assert.equal(x.result.diagnostics.detail.period,'2011');assert.equal(x.result.diagnostics.detail.variable,'q1');
 console.log('SOURCE_READ_TESTS_PASS: stale rows, exact identity, detail mismatch, no records, timeout, login and original text');
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('RUN_CODE', browser_code(action,url,'charls')).replace('SEARCH_CODE',browser_code({'kind':'search','query':'test'},url,'charls')).replace('SITE_URL',json.dumps(url))
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'source-read.cjs'
        path.write_text(fixture,encoding='utf-8')
        subprocess.run(['node',str(path)],check=True)


if __name__ == '__main__':
    main()

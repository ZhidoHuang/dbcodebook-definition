"""Cross-database page contracts: actual names, displayed periods and full summary text."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source_read import browser_code


def main():
    cases = []
    for db, language, period, summary, label in [
        ("elsa", None, "COVID-19 Wave 1", "Top10: 40 ( 3 ), 41 ( 2 )", "Age"),
        ("hrs", None, "1992-2022", "ENGLISH ( 3 ), SPANISH ( 2 )", "Language"),
        ("klosa", "en", "Wave 9", "Range: 194435.82 (190810 ~ 196112)", "Birth date"),
        ("klosa", "ko", "Wave 10", "아니오 ( 3 ), 예 ( 2 )", "재확인"),
        ("chns", None, "Default", "Illness (3)\nOther (2)", ""),
        ("knhanes", None, "2024", "Range: 33.64 (0.0 ~ 98.0)", "만 나이"),
        ("share", None, "Corona Survey 1", "Refusal ( 3 ), Selected ( 2 )", "Test"),
    ]:
        family = db in {"hrs", "klosa"}
        action = {"kind": "detail", "base_variable" if family else "variable": "A001" if family else "age",
                  "file": "Core", "periods": [period]}
        if language:
            action.update(database=db, language=language)
        url = f"http://localhost:8000/home/{db}/" + (language + "/" if language else "")
        row = {"Base_Variable" if family else "Variable": "A001" if family else "age", "File": "Core",
               period: "5", period + "_summary": summary, period + "_label": label}
        if family:
            row[period + "_variable"] = "w09A001" if db == "klosa" else "HA001"
            row[period + "_description"] = "Complete question. If no, skip to Q3. END."
        cases.append({"db": db, "family": family, "period": period, "row": row, "url": url,
                      "code": browser_code(action, url, db)})
    # Reject missing/mismatched language and period-family ambiguity before browser work.
    for action, url in [
        ({"kind": "search", "query": "age"}, "http://localhost/home/klosa/en/"),
        ({"kind": "search", "query": "age", "database": "klosa", "language": "ko"}, "http://localhost/home/klosa/en/"),
    ]:
        try:
            browser_code(action, url, "klosa")
        except ValueError:
            pass
        else:
            raise AssertionError("KLoSA context accepted without matching language")
    fixture = r"""
const assert=require('node:assert/strict');
const cases=CASES;
async function scenario(c, corruption='') {
  const row={...c.row}, period=c.period, calls=[];
  if(corruption==='missing-variable')delete row[period+'_variable'];
  const key=c.family?'Base_Variable':'Variable';
  let fileShown=!c.family, expanded=c.db!=='knhanes', visible=false, directory=true, query='', resolve;
  const heads=()=>[...(expanded?[period]:[]),key,...(fileShown?['File']:[])];
  const header=()=>heads().map(x=>({innerText:x,getAttribute:()=>x}));
  const cells=()=>heads().map(h=>({innerText:corruption==='file'&&h==='File'?'Other':String(row[h])}));
  const summary=row[period+'_summary'];
  const distributions=/^Range:/i.test(summary)?[]:
    [...summary.matchAll(/([^\n]+?)\s*\(\s*(\d+)\s*\)/g)].map(m=>[m[1].replace(/^[ ,]+/,''),m[2]]);
  if(corruption==='count'&&distributions.length)distributions[0][1]='9';
  const fields={'.tooltip-title':c.family?row[period+'_variable']:'age',
    '.tooltip-item.label':row[period+'_label'],'.tooltip-item.description':row[period+'_description']||'',
    '.tooltip-item.code':summary};
  const card={innerText:summary,getClientRects:()=>visible?[{}]:[],querySelector:s=>({textContent:fields[s]||''}),
    querySelectorAll:()=>distributions.map(([label,count])=>({querySelector:s=>({textContent:s==='.code-cell'?label:count})}))};
  const tableDOM={querySelectorAll:s=>s==='thead th'?header():[{querySelectorAll:()=>cells()}]};
  global.document={querySelector:()=>tableDOM,querySelectorAll:()=>[card]};
  const request={url:()=>c.url,method:()=> 'POST',postDataJSON:()=>({search:query,page:1})};
  const response={url:()=>c.url,request:()=>request,ok:()=>true,status:()=>200,
    json:async()=>({data:[row],total_pages:1,total_results:1})};
  const listeners=new Map();
  const page={url:()=>c.url,evaluate:async()=>true,on:(k,v)=>listeners.set(k,v),off:k=>listeners.delete(k),
    waitForResponse:()=>new Promise(r=>resolve=r),
    waitForFunction:async(fn,arg)=>{if(!fn(arg))throw Object.assign(Error('stale DOM'),{name:'TimeoutError'})},
    getByRole:()=>({click:async()=>{calls.push('search');listeners.get('request')(request);resolve(response)}}),
    locator:s=>{
      if(s==='#search')return {fill:async x=>query=x,click:async()=>visible=false};
      if(s==='.side-nav.active .nav-toggle')return {count:async()=>directory?1:0,click:async()=>{directory=false;calls.push('close-directory')}};
      if(s==='.filter-select-header')return {click:async()=>calls.push('display-fields')};
      if(s==='.filter-option-checkbox[value="File"]')return {isChecked:async()=>fileShown,getAttribute:async()=> 'file-checkbox'};
      if(s==='label[for="file-checkbox"]')return {click:async()=>{fileShown=true;calls.push('show-file')}};
      if(s==='#year-window-expand')return {count:async()=>1,getAttribute:async()=>String(expanded),click:async()=>{expanded=true;calls.push('show-periods')}};
      if(s==='#results-table')return {count:async()=>1,locator:s=>s==='thead th'?{evaluateAll:async fn=>fn(header())}:
        s==='thead th[data-column="File"]'?{count:async()=>fileShown?1:0}:
        {nth:()=>({locator:()=>({nth:()=>({hover:async()=>{assert.equal(directory,false);visible=corruption!=='hover-empty';calls.push('hover');
          if(corruption.startsWith('hover-'))throw Object.assign(Error('hover completion timeout'),{name:'TimeoutError'})},
          click:async()=>{throw Error('Read-only tooltip must not select a variable')}})})})}};
      return {evaluateAll:async fn=>fn([card])};
    }};
  const result=await eval('('+c.code+')')(page);
  assert.equal(listeners.size,0);
  return {result,calls};
}
(async()=>{
  for(const c of cases){
    const {result,calls}=await scenario(c);
    assert.equal(result.status,'SOURCE_READ',JSON.stringify({db:c.db,result}));
    const d=result.details[0];
    assert.equal(d.summary,c.row[c.period+'_summary']);
    assert.equal(d.period,c.period);
    assert.equal(d.source_row.File,'Core');
    if(c.family){assert.equal(d.variable,c.row[c.period+'_variable']);assert.equal(d.source,c.row[c.period+'_description']);assert.ok(calls.includes('show-file'))}
    if(c.db==='elsa'){assert.equal(d.summary_kind,'top10');assert.equal(d.distribution[0].label,'40')}
    if(c.db==='knhanes'){assert.ok(calls.includes('show-periods'));assert.equal(d.summary_kind,'range')}
    assert.equal((await scenario(c,'file')).result.error_code,'SEARCH_TABLE_TIMEOUT');
    if(c.family)assert.equal((await scenario(c,'missing-variable')).result.status,'PERIOD_VARIABLE_MISSING');
    if(!/^Range:/.test(d.summary))assert.equal((await scenario(c,'count')).result.status,'DETAIL_CONTENT_MISMATCH');
    const recovered=await scenario(c,'hover-visible');
    assert.equal(recovered.result.status,'SOURCE_READ');
    assert.equal(recovered.result.details[0].hover_timeout,true);
    assert.equal(recovered.calls.filter(x=>x==='hover').length,1);
    assert.equal((await scenario(c,'hover-empty')).result.error_code,'DETAIL_CARD_TIMEOUT');
  }
  console.log('SOURCE_READ_DATABASES_PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
""".replace("CASES", json.dumps(cases, ensure_ascii=False), 1)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "databases.cjs"
        path.write_text(fixture, encoding="utf-8")
        subprocess.run(["node", str(path)], check=True)


if __name__ == "__main__":
    main()

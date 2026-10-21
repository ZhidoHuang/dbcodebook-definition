const assert = require('node:assert/strict');
const {prepareWebsite} = require('../scripts/website_prepare.js');
global.readWebsiteTaxonomy = async () => ({directory_tag:{current:'CHNS',options:['CHNS']}});
const origin = 'http://localhost:8000';
const existing = {base_url:origin,create:false,post_id:'132',edit_id:null,identity_title_parts:['CHARLS','ADL']};
function fake(options={}) {
  const s = {url:origin+'/nodes/post/132/',auth:true,title:'CHARLS — ADL',body:'saved body',
    button:'发布文章', attachments:2, ready:true, clicks:[], clickOptions:[], navigations:[],
    hitPoints:[], measurements:0, viewport:{width:1000,height:600},
    rect:{left:10,top:10,right:110,bottom:50}, border:2, ...options};
  global.window = {__GUIDE_USER__:{authenticated:s.auth},innerWidth:s.viewport.width,innerHeight:s.viewport.height};
  const child = {};
  const editElement = {getBoundingClientRect:()=>s.rect,contains:element=>element===child};
  global.getComputedStyle = () => Object.fromEntries(
    ['borderLeftWidth','borderTopWidth','borderRightWidth','borderBottomWidth'].map(side=>[side,s.border+'px']));
  const nodes = () => ({'#title':{value:s.title},'#editor':{value:s.body},'#category':{value:'CHARLS'},
    '.btn-publish':{textContent:s.button},'#directory-tag-trigger':{},'#cross-database-topic-trigger':{}});
  global.document = {querySelector:sel=>nodes()[sel],querySelectorAll:()=>Array(s.attachments).fill({}),
    elementFromPoint:(x,y)=>{s.hitPoints.push({x,y});return s.obscured?{}:s.hitChild?child:editElement;}};
  const page = {
    url:()=>s.url,
    evaluate:async fn=>fn(),
    goto:async url=>{s.navigations.push(url);s.url=url;},
    locator:sel=>({count:async()=>1,waitFor:async()=>{},innerText:async()=>s.title,
      evaluate:async fn=>{assert.equal(sel,'.edit-post-btn:visible');s.measurements++;return fn(editElement);},
      click:async options=>{
        assert.equal(options.force,undefined);s.clicks.push(sel);s.clickOptions.push(options);
        if(sel==='.edit-post-btn:visible')s.url=origin+'/nodes/edit/335/';
      }}),
    waitForURL:async fn=>assert.ok(fn(new URL(s.url))),
    waitForFunction:async(fn,arg)=>{
      // Simulate delayed editor population; a visible input alone is insufficient.
      if(!arg) assert.equal(fn(arg), false);
      if(s.ready) s.button=arg?'发布文章':'更新文章';
      if(!fn(arg))throw new Error('editor timeout');
    }
  };
  return {page,s};
}
let caseCount=0;
async function run(action,opts,status) {
  const {page,s}=fake(opts);const result=await prepareWebsite(page,action);
  assert.equal(result.status,status,JSON.stringify(result));caseCount++;return {result,s};
}
(async()=>{
  let r=await run(existing,{},'WEBSITE_EDITOR_READY');
  assert.equal(r.result.edit_id,'335');assert.deepEqual(r.s.clicks,['.edit-post-btn:visible']);
  assert.equal(r.result.body_length,10);
  assert.equal(r.s.clickOptions[0].position,undefined);assert.deepEqual(r.s.hitPoints,[]);
  const croppedCases=[
    [{left:-80,top:10,right:20,bottom:50},{x:87,y:18},{x:9,y:30}],
    [{left:980,top:10,right:1080,bottom:50},{x:9,y:18},{x:991,y:30}],
    [{left:10,top:-30,right:110,bottom:10},{x:48,y:32},{x:60,y:4}],
    [{left:10,top:590,right:110,bottom:630},{x:48,y:4},{x:60,y:596}]
  ];
  for(const [rect,position,hit] of croppedCases) {
    r=await run(existing,{rect},'WEBSITE_EDITOR_READY');
    assert.deepEqual(r.s.clickOptions[0].position,position);assert.deepEqual(r.s.hitPoints,[hit]);
    assert.equal(r.s.clicks.length,1);
  }
  r=await run(existing,{rect:croppedCases[0][0],hitChild:true},'WEBSITE_EDITOR_READY');
  assert.equal(r.s.clicks.length,1);
  r=await run(existing,{rect:croppedCases[0][0],obscured:true},'WEBSITE_PREPARE_INCOMPLETE');
  assert.match(r.result.error,/obscured/);assert.equal(r.s.clicks.length,0);assert.equal(r.s.navigations.length,0);
  r=await run(existing,{rect:{left:-100,top:10,right:1,bottom:50}},'WEBSITE_PREPARE_INCOMPLETE');
  assert.match(r.result.error,/no visible clickable area/);assert.equal(r.s.clicks.length,0);
  r=await run(existing,{rect:{left:10,top:700,right:110,bottom:740}},'WEBSITE_EDITOR_READY');
  assert.equal(r.s.clickOptions[0].position,undefined);assert.deepEqual(r.s.hitPoints,[]);
  await run({...existing,edit_id:'335'},{url:origin+'/nodes/edit/335/'},'WEBSITE_EDITOR_READY');
  r=await run(existing,{url:origin+'/nodes/edit/999/'},'EDITOR_ALREADY_OPEN');
  assert.equal(r.s.navigations.length,0);
  await run(existing,{url:'http://other/nodes/post/132/'},'WRONG_SITE');
  await run(existing,{auth:false},'LOGIN_REQUIRED');
  r=await run({...existing,open_login:true},{auth:false},'LOGIN_REQUIRED');
  assert.equal(r.s.clicks.length,1);assert.equal(r.s.navigations.length,0);
  await run(existing,{auth:null},'LOGIN_STATE_UNKNOWN');
  r=await run(existing,{title:'Other article',rect:croppedCases[0][0]},'ARTICLE_IDENTITY_MISMATCH');
  assert.equal(r.s.measurements,0);assert.equal(r.s.clicks.length,0);
  await run({...existing,edit_id:'336'},{},'EDITOR_IDENTITY_MISMATCH');
  await run(existing,{ready:false},'WEBSITE_PREPARE_INCOMPLETE');
  const create={base_url:origin,create:true};
  r=await run(create,{title:'',body:'',attachments:0},'WEBSITE_EDITOR_READY');
  assert.deepEqual(r.s.navigations,[origin+'/nodes/edit/']);assert.equal(r.s.clicks.length,0);
  await run(create,{url:origin+'/nodes/edit/',body:'draft'},'NONEMPTY_DRAFT');
  await run(create,{url:origin+'/nodes/edit/',title:'',body:'',attachments:1},'NONEMPTY_DRAFT');
  console.log('website preparation: '+caseCount+' browser-state cases passed; no write methods available');
})().catch(e=>{console.error(e);process.exitCode=1;});

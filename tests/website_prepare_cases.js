const assert = require('node:assert/strict');
const {prepareWebsite} = require('../scripts/website_prepare.js');
global.readWebsiteTaxonomy = async () => ({directory_tag:{current:'CHNS',options:['CHNS']}});
const origin = 'http://localhost:8000';
const existing = {base_url:origin,create:false,post_id:'132',edit_id:null,identity_title_parts:['CHARLS','ADL']};
function fake(options={}) {
  const s = {url:origin+'/nodes/post/132/',auth:true,title:'CHARLS — ADL',body:'saved body',
    button:'发布文章', disabled:false, busy:null, attachments:2, ready:true, clicks:[], clickOptions:[], navigations:[],
    hitPoints:[], measurements:0, loadWaits:0, evaluations:0, identityReads:0, clock:0, viewport:{width:1000,height:600},
    rect:{left:10,top:10,right:110,bottom:50}, border:2, ...options};
  global.window = {__GUIDE_USER__:{authenticated:s.auth},innerWidth:s.viewport.width,innerHeight:s.viewport.height};
  const child = {};
  const editElement = {getBoundingClientRect:()=>s.rect,contains:element=>element===child};
  global.getComputedStyle = () => Object.fromEntries(
    ['borderLeftWidth','borderTopWidth','borderRightWidth','borderBottomWidth'].map(side=>[side,s.border+'px']));
  const nodes = () => ({'#title':{value:s.title},'#editor':{value:s.body},'#category':{value:'CHARLS'},
    '.btn-publish':{textContent:s.button,disabled:s.disabled,getAttribute:name=>name==='aria-busy'?s.busy:null},'#directory-tag-trigger':{},'#cross-database-topic-trigger':{}});
  global.document = {readyState:'interactive',querySelector:sel=>s.missing?.includes(sel)?null:nodes()[sel],querySelectorAll:()=>Array(s.attachments).fill({}),
    elementFromPoint:(x,y)=>{s.hitPoints.push({x,y});return s.obscured?{}:s.hitChild?child:editElement;}};
  const page = {
    url:()=>s.url,
    waitForLoadState:async(state,options)=>{
      assert.equal(state,'domcontentloaded');assert.ok(options.timeout>0);s.loadWaits++;
      if(s.destroyAuthOnce && s.loadWaits===1) s.pendingNavigation=true;
      else s.pendingNavigation=false;
    },
    evaluate:async (fn,arg)=>{
      s.evaluations++;
      if((s.destroyAuthOnce && s.evaluations===1) || s.pendingNavigation || s.destroyAuthAlways)
        throw new Error('Execution context was destroyed, most likely because of a navigation');
      if(s.expireOn==='auth' && s.evaluations===1) s.clock=25001;
      if(arg?.editId) {
        s.identityReads++;
        if(s.identityReadError)throw new Error('Editor article identity could not be read');
        return {id:arg.editId,url:'/nodes/post/'+(s.actualPostId || '132')+'/'};
      }
      return fn();
    },
    goto:async (url,options)=>{
      s.navigations.push(url);
      assert.equal(options.waitUntil,'commit');
      if(!s.navigationStuck) s.url=url;
      if(s.navigationTimeout || s.navigationStuck) throw new Error('page.goto: Timeout exceeded');
      if(s.navigationError) throw new Error(s.navigationError);
    },
    locator:sel=>({count:async()=>{if(s.expireOn==='login-count')s.clock=25001;return 1;},waitFor:async()=>{},innerText:async()=>s.title,
      evaluate:async fn=>{assert.equal(sel,'.edit-post-btn:visible');s.measurements++;const value=fn(editElement);if(s.expireOn==='measurement')s.clock=25001;return value;},
      click:async options=>{
        assert.equal(options.force,undefined);s.clicks.push(sel);s.clickOptions.push(options);
        if(sel==='.edit-post-btn:visible') {
          assert.equal(options.noWaitAfter,true);
          if(!s.editorNavigationStuck)s.url=origin+'/nodes/edit/335/';
        }
      }}),
    waitForURL:async (fn,options)=>{
      assert.equal(options.waitUntil,'commit');
      if(s.editorNavigationTimeout || s.editorNavigationStuck)throw new Error('page.waitForURL: Timeout exceeded');
      assert.ok(fn(new URL(s.url)));
    },
    waitForFunction:async(fn,arg)=>{
      if(arg===null) {s.pendingNavigation=false;assert.ok(fn());return;}
      // Simulate delayed editor population; a visible input alone is insufficient.
      if(s.ready) s.button=arg?'发布文章':'更新文章';
      if(!fn(arg))throw new Error('editor timeout');
    }
  };
  if (options.targetId) page[Symbol.for('dbCodeBook.targetId')] = options.targetId;
  page.context = () => ({[Symbol.for('dbCodeBook.syncReceipts')]:s.receipts});
  return {page,s};
}
let caseCount=0;
async function run(action,opts,status) {
  const {page,s}=fake(opts);const clock=Date.now;Date.now=()=>s.clock;
  let result;try {result=await prepareWebsite(page,action);} finally {Date.now=clock;}
  assert.equal(result.status,status,JSON.stringify(result));caseCount++;return {result,s};
}
(async()=>{
  let r=await run(existing,{},'WEBSITE_EDITOR_READY');
  assert.equal(r.result.edit_id,'335');assert.deepEqual(r.s.clicks,['.edit-post-btn:visible']);
  assert.equal(r.result.body_length,10);
  assert.equal(r.s.loadWaits,0);
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
  r=await run({...existing,edit_id:'335'},{url:origin+'/nodes/edit/335/'},'WEBSITE_EDITOR_READY');
  assert.deepEqual(r.s.clicks,[]);assert.deepEqual(r.s.navigations,[]);
  r=await run({...existing,edit_id:'335'},{url:origin+'/nodes/edit/335/',actualPostId:'999'},'EDITOR_IDENTITY_MISMATCH');
  assert.deepEqual(r.s.clicks,[]);assert.deepEqual(r.s.navigations,[]);
  r=await run({...existing,edit_id:'335'},{url:origin+'/nodes/edit/335/',identityReadError:true},'WEBSITE_PREPARE_INCOMPLETE');
  assert.equal(r.result.phase,'editor_identity');assert.deepEqual(r.s.clicks,[]);assert.deepEqual(r.s.navigations,[]);
  const receipt = (post='132', edit='335', target='task') => ({scope:{kind:'website-prepare'},state:'completed',tab_id:target,
    result:{ok:true,status:'WEBSITE_EDITOR_READY',authenticated:true,create:false,post_id:post,edit_id:edit,
      url:origin+'/nodes/edit/'+edit+'/',title:'CHARLS — ADL',tab_id:target}});
  const editorAction = {...existing,edit_id:'335'};
  const receipts = new Map([['other',receipt('999','336')],['correct',receipt()]]);
  r=await run(editorAction,{url:origin+'/nodes/edit/335/',targetId:'task',receipts,identityReadError:true},'WEBSITE_EDITOR_READY');
  assert.equal(r.s.identityReads,0);
  for (const candidate of [receipt('999'),receipt('132','335','another'),
    {...receipt(),state:'running'}, {...receipt(),result:{...receipt().result,url:'http://other/nodes/edit/335/'}}]) {
    r=await run(editorAction,{url:origin+'/nodes/edit/335/',targetId:'task',receipts:new Map([['prior',candidate]]),identityReadError:true},'WEBSITE_PREPARE_INCOMPLETE');
    assert.equal(r.result.phase,'editor_identity');assert.equal(r.s.identityReads,1);
  }
  {
    const {page,s}=fake({targetId:'task',ready:false});
    const first=await prepareWebsite(page,existing);
    assert.equal(first.status,'WEBSITE_PREPARE_INCOMPLETE');assert.equal(first.phase,'editor');
    assert.equal(first.editor_state.ready_state,'interactive');assert.equal(first.editor_state.button_text,'发布文章');
    assert.deepEqual(first.editor_state.missing_controls,[]);assert.equal(s.identityReads,0);
    s.ready=true;s.identityReadError=true;
    const resumed=await prepareWebsite(page,editorAction);
    assert.equal(resumed.status,'WEBSITE_EDITOR_READY');assert.equal(s.identityReads,0);
  }
  r=await run(existing,{destroyAuthOnce:true},'WEBSITE_EDITOR_READY');
  assert.equal(r.s.loadWaits,0);assert.equal(r.s.clicks.length,1);
  r=await run(existing,{destroyAuthAlways:true},'WEBSITE_PREPARE_INCOMPLETE');
  assert.equal(r.s.loadWaits,0);assert.deepEqual(r.s.clicks,[]);
  r=await run(existing,{url:origin+'/',navigationTimeout:true},'WEBSITE_EDITOR_READY');
  assert.equal(r.s.navigations.length,1);assert.equal(r.s.clicks.length,1);assert.equal(r.s.loadWaits,0);
  r=await run(existing,{editorNavigationTimeout:true},'WEBSITE_EDITOR_READY');
  assert.equal(r.s.clicks.length,1);assert.equal(r.s.navigations.length,0);
  r=await run(existing,{url:origin+'/',navigationStuck:true},'WEBSITE_PREPARE_INCOMPLETE');
  assert.equal(r.s.navigations.length,1);assert.equal(r.s.clicks.length,0);
  r=await run(existing,{editorNavigationStuck:true},'WEBSITE_PREPARE_INCOMPLETE');
  assert.equal(r.s.clicks.length,1);assert.equal(r.s.navigations.length,0);
  r=await run(existing,{url:origin+'/',navigationError:'net::ERR_CONNECTION_REFUSED'},'WEBSITE_PREPARE_INCOMPLETE');
  assert.equal(r.s.clicks.length,0);
  r=await run(existing,{editorNavigationTimeout:true,ready:false},'WEBSITE_PREPARE_INCOMPLETE');
  assert.equal(r.s.clicks.length,1);
  r=await run(existing,{expireOn:'measurement'},'WEBSITE_PREPARE_INCOMPLETE');
  assert.match(r.result.error,/deadline exceeded/);assert.deepEqual(r.s.clicks,[]);
  r=await run({...existing,open_login:true},{auth:false,expireOn:'login-count'},'WEBSITE_PREPARE_INCOMPLETE');
  assert.match(r.result.error,/deadline exceeded/);assert.deepEqual(r.s.clicks,[]);
  r=await run(existing,{expireOn:'auth'},'WEBSITE_PREPARE_INCOMPLETE');
  assert.match(r.result.error,/deadline exceeded/);assert.deepEqual(r.s.clicks,[]);assert.deepEqual(r.s.navigations,[]);
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
  r=await run(existing,{ready:false,missing:['#editor']},'WEBSITE_PREPARE_INCOMPLETE');
  assert.equal(r.result.phase,'editor');assert.deepEqual(r.result.editor_state.missing_controls,['#editor']);
  for (const [disabled,busy] of [[true,'true'],[true,null],[false,'true']]) {
    r=await run(editorAction,{url:origin+'/nodes/edit/335/',button:'更新文章',disabled,busy},'WEBSITE_PREPARE_INCOMPLETE');
    assert.equal(r.result.phase,'editor');assert.equal(r.result.editor_state.button_text,'更新文章');
    assert.equal(r.result.editor_state.button_disabled,disabled);assert.equal(r.result.editor_state.button_aria_busy,busy);
    assert.deepEqual(r.s.clicks,[]);assert.deepEqual(r.s.navigations,[]);
  }
  r=await run(editorAction,{url:origin+'/nodes/edit/335/',button:'更新文章',disabled:false,busy:null},'WEBSITE_EDITOR_READY');
  assert.deepEqual(r.s.clicks,[]);
  const create={base_url:origin,create:true};
  r=await run(create,{title:'',body:'',attachments:0},'WEBSITE_EDITOR_READY');
  assert.deepEqual(r.s.navigations,[origin+'/nodes/edit/']);assert.equal(r.s.clicks.length,0);
  await run(create,{url:origin+'/nodes/edit/',body:'draft'},'NONEMPTY_DRAFT');
  await run(create,{url:origin+'/nodes/edit/',title:'',body:'',attachments:1},'NONEMPTY_DRAFT');
  console.log('website preparation: '+caseCount+' browser-state cases passed; no write methods available');
})().catch(e=>{console.error(e);process.exitCode=1;});

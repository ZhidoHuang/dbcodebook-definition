const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {downloadCapture,observeDownload} = require('../scripts/download_capture.js');
const page = () => Object.assign(new EventEmitter(), {url:()=> 'http://localhost:8000/home/share/'});
(async () => {
  const p=page(); let saved=0;
  const first=downloadCapture(p,'one','one.zip');
  assert.equal(await first.wait(1),'waiting');
  const pending=await observeDownload(p,'one',1);
  assert.equal(pending.status,'DOWNLOAD_EVENT_PENDING');
  assert.equal(pending.allow_new_export,false);
  assert.throws(()=>downloadCapture(p,'two','two.zip'), /pending/);
  assert.equal((await observeDownload(p,'other',1)).status,'DOWNLOAD_RECEIVER_UNAVAILABLE');
  // Event arrives in the gap AFTER the initial call ended, BEFORE observation resumes.
  p.emit('download',{saveAs:async target=>{assert.equal(target,'one.zip');saved++;}});
  const ready=await observeDownload(p,'one',10);
  assert.equal(ready.status,'DOWNLOAD_FILE_READY');assert.equal(saved,1);
  assert.equal((await observeDownload(p,'one',1)).download_path,'one.zip');
  assert.equal(saved,1);assert.equal(p.listenerCount('download'),0);
  assert.equal(p.listenerCount('close'),0);

  // File saving is separate from receiving an event; not ready until saveAs resolves.
  const slow=page();let finish;
  downloadCapture(slow,'slow','slow.zip');
  slow.emit('download',{saveAs:()=>new Promise(resolve=>{finish=resolve;})});
  assert.equal((await observeDownload(slow,'slow',1)).status,'DOWNLOAD_FILE_SAVING');
  finish();assert.equal((await observeDownload(slow,'slow',10)).status,'DOWNLOAD_FILE_READY');

  const broken=page();downloadCapture(broken,'bad','bad.zip');
  broken.emit('download',{saveAs:async()=>{throw Error('disk full');}});
  const failed=await observeDownload(broken,'bad',10);
  assert.equal(failed.status,'DOWNLOAD_PATH_UNAVAILABLE');assert.match(failed.error,/disk full/);
  assert.equal(failed.allow_new_export,false);

  const closed=page();downloadCapture(closed,'closed','x.zip');closed.emit('close');
  assert.equal((await observeDownload(closed,'closed',1)).receiver_state,'unavailable');
  assert.equal(closed.listenerCount('download'),0);
  const moved=page();downloadCapture(moved,'moved','x.zip');moved.url=()=> 'http://localhost:8000/home/elsa/';
  moved.emit('download',{saveAs:async()=>{throw Error('must not save another page download');}});
  assert.match((await observeDownload(moved,'moved',1)).error,/Page changed/);

  // Expiration detaches the receiver; it never authorizes another paid export.
  const originalTimer=globalThis.setTimeout;let expire;
  globalThis.setTimeout=(fn,ms)=>ms===600000?(expire=fn,{unref(){}}):originalTimer(fn,ms);
  const expired=page();downloadCapture(expired,'expired','x.zip');
  globalThis.setTimeout=originalTimer;expire();
  const expiry=await observeDownload(expired,'expired',1);
  assert.equal(expiry.allow_new_export,false);assert.equal(expired.listenerCount('download'),0);
  assert.match(expiry.error,/expired/);
  console.log('DOWNLOAD_CAPTURE_PASS: late event, continued saving, same-attempt observation, failure, identity, cleanup; no clicks');
})().catch(error=>{console.error(error);process.exitCode=1;});

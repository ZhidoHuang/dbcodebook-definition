// Keep the same attempt's receiver across CLI calls. Observation never clicks.
function downloadCapture(page, attemptId, target, observeOnly = false) {
  const key = Symbol.for('dbCodeBook.downloadCapture');
  let record = page[key];
  if (record && record.attempt_id === attemptId) return record;
  if (observeOnly) return null;
  if (record && ['waiting', 'saving'].includes(record.state))
    throw new Error('An earlier download attempt is still pending; observe it before another export');
  let complete;
  record = {attempt_id: attemptId, state: 'waiting', source_url: page.url(),
    started_at: new Date().toISOString(), target, promise: new Promise(resolve => {complete = resolve;})};
  page[key] = record;
  let expiry;
  const cleanup = () => {page.off('download', receive); page.off('close', closed); globalThis.clearTimeout(expiry);};
  const closed = () => {
    if (record.state === 'waiting') {
      record.state = 'unavailable'; record.error = 'Bound page closed before download event';
      cleanup(); complete();
    }
  };
  const receive = download => {
    cleanup();
    if (page.url() !== record.source_url) {
      record.state = 'unavailable'; record.error = 'Page changed before download event'; complete(); return;
    }
    record.state = 'saving';
    record.event_at = new Date().toISOString();
    record.promise = Promise.resolve().then(() => download.saveAs(target)).then(() => {
      record.state = 'ready'; record.completed_at = new Date().toISOString(); complete();
    }, error => {record.state = 'failed'; record.error = String(error); complete();});
  };
  record.wait = async timeoutMs => {
    let timer;
    try {
      await Promise.race([record.promise, new Promise(resolve => {
        timer = globalThis.setTimeout(resolve, timeoutMs);
      })]);
    } finally {globalThis.clearTimeout(timer);}
    return record.state;
  };
  page.on('download', receive);
  page.on('close', closed);
  expiry = globalThis.setTimeout(() => {
    if (record.state === 'waiting') {
      record.state = 'unavailable'; record.error = 'Receiver expired after 10 minutes; inspect files and the same download record';
      cleanup(); complete();
    }
  }, 600000);
  if (expiry && typeof expiry.unref === 'function') expiry.unref();
  return record;
}

async function observeDownload(page, attemptId, timeoutMs = 20000) {
  const record = downloadCapture(page, attemptId, null, true);
  const common = {attempt_id: attemptId, allow_new_export: false};
  if (!record) return {ok:false, status:'DOWNLOAD_RECEIVER_UNAVAILABLE',
    next_action:'run_watch_command', ...common};
  await record.wait(timeoutMs);
  const evidence = {...common, receiver_state:record.state, source_url:record.source_url,
    started_at:record.started_at, event_at:record.event_at || null, error:record.error || null};
  if (record.state === 'ready') return {ok:true,status:'DOWNLOAD_FILE_READY',
    download_path:record.target,next_action:'install_download_path',...evidence};
  return {ok:false,status: record.state === 'waiting' ? 'DOWNLOAD_EVENT_PENDING'
    : record.state === 'saving' ? 'DOWNLOAD_FILE_SAVING' : 'DOWNLOAD_PATH_UNAVAILABLE',
    next_action: ['waiting','saving'].includes(record.state) ? 'observe_same_attempt' : 'run_watch_command', ...evidence};
}
if (typeof module !== 'undefined') module.exports = {downloadCapture, observeDownload};

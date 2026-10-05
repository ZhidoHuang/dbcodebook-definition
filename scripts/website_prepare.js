// Navigate and inspect only. Never fill, upload, delete, or submit.
async function prepareWebsite(page, action) {
  const deadline = Date.now() + 25000;
  let phase = 'login';
  const fail = (status, extra = {}) => ({ok: false, status, phase, url: page.url(), ...extra});
  const remaining = () => Math.max(1, deadline - Date.now());
  const sameSite = () => new URL(page.url()).origin === action.base_url;
  const editorPath = /^\/nodes\/edit\/(?:([1-9][0-9]*)\/)?$/;
  const matchesTitle = title => action.identity_title_parts.every(part => title.includes(part));
  async function login() {
    if (!sameSite()) return fail('WRONG_SITE');
    const authenticated = await page.evaluate(() => window.__GUIDE_USER__?.authenticated ?? null);
    if (authenticated === true) return null;
    if (authenticated !== false) return fail('LOGIN_STATE_UNKNOWN');
    if (action.open_login === true) {
      const trigger = page.locator('.auth-panel-trigger[data-mode="login"]:visible');
      if (await trigger.count() !== 1) return fail('LOGIN_CONTROL_CHANGED');
      await trigger.click({timeout: Math.min(3000, remaining())});
    }
    return fail('LOGIN_REQUIRED');
  }
  try {
    let blocked = await login();
    if (blocked) return blocked;
    let path = new URL(page.url()).pathname;
    const currentEditor = path.match(editorPath);
    let editId = action.edit_id;
    if (currentEditor) {
      // Do not leave an editor: it may contain unsaved user work.
      if (action.create ? !!currentEditor[1] : (!editId || currentEditor[1] !== editId))
        return fail('EDITOR_ALREADY_OPEN', {message: 'Keep this editor; supply its verified edit_id or use the task article page.'});
    } else if (action.create) {
      phase = 'open_editor';
      await page.goto(action.base_url + '/nodes/edit/', {waitUntil: 'domcontentloaded', timeout: remaining()});
    } else {
      phase = 'article';
      const articlePath = '/nodes/post/' + action.post_id + '/';
      if (path !== articlePath)
        await page.goto(action.base_url + articlePath, {waitUntil: 'domcontentloaded', timeout: remaining()});
      blocked = await login();
      if (blocked) return blocked;
      if (new URL(page.url()).pathname !== articlePath) return fail('ARTICLE_IDENTITY_MISMATCH');
      const heading = page.locator('.post-detail-header h1');
      await heading.waitFor({state: 'visible', timeout: remaining()});
      const title = (await heading.innerText()).trim();
      if (!matchesTitle(title)) return fail('ARTICLE_IDENTITY_MISMATCH', {title});
      const edit = page.locator('.edit-post-btn:visible');
      await edit.waitFor({state: 'visible', timeout: remaining()});
      phase = 'open_editor';
      await edit.click({timeout: remaining()});
      await page.waitForURL(url => url.origin === action.base_url && editorPath.test(url.pathname)
        && !!url.pathname.match(editorPath)[1], {timeout: remaining(), waitUntil: 'domcontentloaded'});
      editId = new URL(page.url()).pathname.match(editorPath)[1];
      if (action.edit_id && editId !== action.edit_id) return fail('EDITOR_IDENTITY_MISMATCH', {edit_id: editId});
    }
    phase = 'editor';
    blocked = await login();
    if (blocked) return blocked;
    path = new URL(page.url()).pathname;
    if (path !== (action.create ? '/nodes/edit/' : '/nodes/edit/' + editId + '/'))
      return fail('EDITOR_IDENTITY_MISMATCH');
    // Existing content is loaded asynchronously; the update label is set last.
    await page.waitForFunction(create => {
      const title = document.querySelector('#title'), body = document.querySelector('#editor');
      const button = document.querySelector('.btn-publish');
      return title && body && document.querySelector('#category') && button
        && document.querySelector('#directory-tag-trigger')
        && document.querySelector('#cross-database-topic-trigger')
        && button.textContent.trim() === (create ? '发布文章' : '更新文章');
    }, action.create, {timeout: remaining()});
    const state = await page.evaluate(() => ({
      title: document.querySelector('#title').value,
      body_length: document.querySelector('#editor').value.trim().length,
      category: document.querySelector('#category').value,
      attachment_count: document.querySelectorAll('.document-item').length
    }));
    if (action.create && (state.title.trim() || state.body_length || state.attachment_count))
      return fail('NONEMPTY_DRAFT', state);
    if (!action.create && !matchesTitle(state.title)) return fail('EDITOR_IDENTITY_MISMATCH', state);
    const fields = await readWebsiteTaxonomy({playwright: page});
    return {ok: true, status: 'WEBSITE_EDITOR_READY', url: page.url(), authenticated: true,
      create: action.create, post_id: action.post_id || null, edit_id: editId || null, ...state, fields};
  } catch (error) {
    return fail('WEBSITE_PREPARE_INCOMPLETE', {error: String(error), message: 'Keep the page and inspect this failure; no submission was made.'});
  }
}
if (typeof module !== 'undefined') module.exports = {prepareWebsite};

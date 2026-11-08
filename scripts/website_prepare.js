// Navigate and inspect only. Never fill, upload, delete, or submit.
async function prepareWebsite(page, action) {
  const startedAt = Date.now();
  let deadline = startedAt + 25000;
  let phase = 'login';
  let phaseStartedAt = startedAt;
  const timings = {};
  const enter = next => {
    timings[phase] = (timings[phase] || 0) + Date.now() - phaseStartedAt;
    phase = next;
    phaseStartedAt = Date.now();
  };
  const timing = () => ({preparation_elapsed_ms: Date.now() - startedAt,
    phase_timings_ms: {...timings, [phase]: (timings[phase] || 0) + Date.now() - phaseStartedAt}});
  const fail = (status, extra = {}) => ({ok: false, status, phase, url: page.url(), ...timing(), ...extra});
  const remaining = () => {
    const ms = deadline - Date.now();
    if (ms <= 0) throw new Error('Website preparation deadline exceeded');
    return ms;
  };
  const sameSite = () => new URL(page.url()).origin === action.base_url;
  const editorPath = /^\/nodes\/edit\/(?:([1-9][0-9]*)\/)?$/;
  const matchesTitle = title => action.identity_title_parts.every(part => title.includes(part));
  const isTimeout = error => error?.name === 'TimeoutError' || /timeout|timed out|deadline exceeded/i.test(String(error));
  const identityKey = Symbol.for('dbCodeBook.websiteIdentity');
  const targetKey = Symbol.for('dbCodeBook.targetId');
  const matchesIdentity = (value, editId) => value && value.origin === action.base_url
    && value.post_id === action.post_id && value.edit_id === editId
    && value.edit_url === page.url();
  function knownIdentity(editId) {
    if (matchesIdentity(page[identityKey], editId)) return true;
    const targetId = page[targetKey];
    const receipts = page.context?.()[Symbol.for('dbCodeBook.syncReceipts')];
    if (!targetId || !receipts) return false;
    return [...receipts.values()].some(receipt => {
      const result = receipt.result;
      return receipt.scope?.kind === 'website-prepare' && receipt.state === 'completed'
        && receipt.tab_id === targetId && result?.tab_id === targetId
        && result.ok === true && result.status === 'WEBSITE_EDITOR_READY'
        && result.authenticated === true && result.create === false
        && typeof result.title === 'string' && result.title.length > 0
        && matchesIdentity({origin:action.base_url, post_id:result.post_id,
          edit_id:result.edit_id, edit_url:result.url}, editId);
    });
  }
  async function navigate(url) {
    try {
      await page.goto(url, {waitUntil: 'commit', timeout: Math.min(25000, remaining())});
    } catch (error) {
      if (!isTimeout(error)) throw error;
      // The original navigation can finish after Playwright's first wait.
      // Observe it on the same page; never dispatch a second navigation.
      if (page.url() !== url)
        await page.waitForURL(actual => actual.href === url, {timeout: remaining(), waitUntil: 'commit'});
    }
    remaining();
  }
  async function login() {
    remaining();
    if (!sameSite()) return fail('WRONG_SITE');
    let authenticated;
    try {
      await page.waitForFunction(() => window.__GUIDE_USER__
        && 'authenticated' in window.__GUIDE_USER__, null, {timeout: remaining()});
      authenticated = await page.evaluate(() => window.__GUIDE_USER__?.authenticated ?? null);
    } catch (error) {
      if (!/execution context was destroyed|cannot find context with specified id|because of a navigation/i.test(String(error))) throw error;
      await page.waitForFunction(() => typeof window.__GUIDE_USER__?.authenticated === 'boolean',
        null, {timeout: remaining()});
      remaining();
      if (!sameSite()) return fail('WRONG_SITE');
      authenticated = await page.evaluate(() => window.__GUIDE_USER__?.authenticated ?? null);
    }
    remaining();
    if (authenticated === true) return null;
    if (authenticated !== false) return fail('LOGIN_STATE_UNKNOWN');
    if (action.open_login === true) {
      const trigger = page.locator('.auth-panel-trigger[data-mode="login"]:visible');
      const count = await trigger.count();
      remaining();
      if (count !== 1) return fail('LOGIN_CONTROL_CHANGED');
      await trigger.click({timeout: Math.min(3000, remaining())});
      remaining();
    }
    return fail('LOGIN_REQUIRED');
  }
  try {
    let blocked = await login();
    remaining();
    if (blocked) return blocked;
    let path = new URL(page.url()).pathname;
    const currentEditor = path.match(editorPath);
    let editId = action.edit_id;
    let needsEditorIdentity = false;
    if (currentEditor) {
      // Do not leave an editor: it may contain unsaved user work.
      if (action.create ? !!currentEditor[1] : (!editId || currentEditor[1] !== editId))
        return fail('EDITOR_ALREADY_OPEN', {message: 'Keep this editor; supply its verified edit_id or use the task article page.'});
      needsEditorIdentity = !action.create && !knownIdentity(editId);
    } else if (action.create) {
      enter('open_editor');
      deadline = Date.now() + 60000;
      await navigate(action.base_url + '/nodes/edit/');
    } else {
      enter('article');
      deadline = Date.now() + 60000;
      const articlePath = '/nodes/post/' + action.post_id + '/';
      if (path !== articlePath) {
        await navigate(action.base_url + articlePath);
      }
      blocked = await login();
      remaining();
      if (blocked) return blocked;
      if (new URL(page.url()).pathname !== articlePath) return fail('ARTICLE_IDENTITY_MISMATCH');
      const heading = page.locator('.post-detail-header h1');
      await heading.waitFor({state: 'visible', timeout: remaining()});
      remaining();
      const title = (await heading.innerText()).trim();
      remaining();
      if (!matchesTitle(title)) return fail('ARTICLE_IDENTITY_MISMATCH', {title});
      const edit = page.locator('.edit-post-btn:visible');
      await edit.waitFor({state: 'visible', timeout: remaining()});
      remaining();
      // The detail page's server data identifies the button's destination.
      // Retain the verified mapping even if navigation completes after our wait.
      const article = await page.evaluate(() => window.post
        ? {id: window.post.id, url: window.post.public_url, title: window.post.title} : null);
      remaining();
      let observedEditId = null;
      if (article) {
        observedEditId = String(article.id);
        if (!/^[1-9][0-9]*$/.test(observedEditId) || typeof article.url !== 'string'
            || new URL(article.url, action.base_url).href !== action.base_url + articlePath
            || typeof article.title !== 'string' || !matchesTitle(article.title)
            || !title.startsWith(article.title.trim()))
          return fail('ARTICLE_IDENTITY_MISMATCH');
        if (action.edit_id && observedEditId !== action.edit_id) return fail('EDITOR_IDENTITY_MISMATCH');
        page[identityKey] = {origin:action.base_url, post_id:action.post_id,
          edit_id:observedEditId, edit_url:action.base_url + '/nodes/edit/' + observedEditId + '/'};
      }
      enter('open_editor');
      deadline = Date.now() + 60000;
      const visiblePosition = await edit.evaluate(element => {
        const rect = element.getBoundingClientRect();
        const width = window.innerWidth, height = window.innerHeight;
        // Keep normal scrolling/actionability for controls wholly inside or outside
        // the viewport. A cropped control may have an unreachable default center.
        if ((rect.left >= 0 && rect.top >= 0 && rect.right <= width && rect.bottom <= height)
            || rect.right <= 0 || rect.bottom <= 0 || rect.left >= width || rect.top >= height)
          return null;
        const style = getComputedStyle(element);
        const border = side => Number.parseFloat(style[side]) || 0;
        const paddingLeft = rect.left + border('borderLeftWidth');
        const paddingTop = rect.top + border('borderTopWidth');
        const left = Math.max(0, paddingLeft), top = Math.max(0, paddingTop);
        const right = Math.min(width, rect.right - border('borderRightWidth'));
        const bottom = Math.min(height, rect.bottom - border('borderBottomWidth'));
        if (right <= left || bottom <= top) throw new Error('Edit button has no visible clickable area');
        const x = (left + right) / 2, y = (top + bottom) / 2;
        const hit = document.elementFromPoint(x, y);
        if (!hit || (hit !== element && !element.contains(hit)))
          throw new Error('Visible edit button area is obscured');
        // Playwright position is relative to the element padding box.
        return {x: x - paddingLeft, y: y - paddingTop};
      });
      remaining();
      await edit.click({timeout: remaining(), noWaitAfter: true,
        ...(visiblePosition ? {position: visiblePosition} : {})});
      remaining();
      const atEditor = url => url.origin === action.base_url && editorPath.test(url.pathname)
        && !!url.pathname.match(editorPath)[1];
      try {
        await page.waitForURL(atEditor, {timeout: Math.min(25000, remaining()), waitUntil: 'commit'});
      } catch (error) {
        if (!isTimeout(error)) throw error;
        if (!atEditor(new URL(page.url())))
          await page.waitForURL(atEditor, {timeout: remaining(), waitUntil: 'commit'});
      }
      editId = new URL(page.url()).pathname.match(editorPath)[1];
      if (observedEditId && editId !== observedEditId) return fail('EDITOR_IDENTITY_MISMATCH');
      if (action.edit_id && editId !== action.edit_id) return fail('EDITOR_IDENTITY_MISMATCH', {edit_id: editId});
      if (page.url() !== action.base_url + '/nodes/edit/' + editId + '/') return fail('EDITOR_IDENTITY_MISMATCH');
      page[identityKey] = {origin:action.base_url, post_id:action.post_id,
        edit_id:editId, edit_url:page.url()};
      remaining();
    }
    // The editor's own article request can take longer than navigation.
    // Give that load a separate bound instead of retrying a still-loading page.
    deadline = Date.now() + 60000;
    enter('editor');
    blocked = await login();
    remaining();
    if (blocked) return blocked;
    path = new URL(page.url()).pathname;
    if (path !== (action.create ? '/nodes/edit/' : '/nodes/edit/' + editId + '/'))
      return fail('EDITOR_IDENTITY_MISMATCH');
    // Editing starts disabled and becomes available only after article data loads.
    try {
      await page.waitForFunction(create => {
        const title = document.querySelector('#title'), body = document.querySelector('#editor');
        const button = document.querySelector('.btn-publish');
        return title && body && document.querySelector('#category') && button
          && document.querySelector('#directory-tag-trigger')
          && document.querySelector('#cross-database-topic-trigger')
          && !button.disabled && button.getAttribute('aria-busy') !== 'true'
          && button.textContent.trim() === (create ? '发布文章' : '更新文章');
      }, action.create, {timeout: remaining()});
    } catch (error) {
      if (!isTimeout(error)) throw error;
      let state, timer;
      try {
        state = await Promise.race([page.evaluate(() => ({
          ready_state: document.readyState,
          missing_controls: ['#title', '#editor', '#category', '.btn-publish',
            '#directory-tag-trigger', '#cross-database-topic-trigger']
            .filter(selector => !document.querySelector(selector)),
          button_text: document.querySelector('.btn-publish')?.textContent.trim() ?? null,
          button_disabled: document.querySelector('.btn-publish')?.disabled ?? null,
          button_aria_busy: document.querySelector('.btn-publish')?.getAttribute('aria-busy') ?? null
        })), new Promise((_, reject) => {timer = setTimeout(() => reject(new Error('diagnostic timeout')), 1000);})]);
      } catch { state = {unavailable:true}; }
      finally { clearTimeout(timer); }
      return fail('WEBSITE_PREPARE_INCOMPLETE', {error:String(error), editor_state:state,
        message:'Editor readiness was not confirmed; keep the page. No submission was made.'});
    }
    remaining();
    if (needsEditorIdentity) {
      // Let the editor finish its own load before a fallback identity request.
      // Normal article -> editor navigation already has a verified mapping.
      enter('editor_identity');
      const post = await page.evaluate(async ({editId, timeout}) => {
        const response = await fetch('/nodes/api/posts/' + editId + '/',
          {signal: AbortSignal.timeout(timeout)});
        if (!response.ok) throw new Error('Editor article identity could not be read');
        const data = await response.json();
        return {id: data.post?.id, url: data.post?.public_url};
      }, {editId, timeout: remaining()});
      remaining();
      if (String(post.id) !== editId || typeof post.url !== 'string'
          || new URL(post.url, action.base_url).href !== action.base_url + '/nodes/post/' + action.post_id + '/')
        return fail('EDITOR_IDENTITY_MISMATCH');
      page[identityKey] = {origin:action.base_url, post_id:action.post_id,
        edit_id:editId, edit_url:page.url()};
      enter('editor');
    }
    const state = await page.evaluate(() => ({
      title: document.querySelector('#title').value,
      body_length: document.querySelector('#editor').value.trim().length,
      category: document.querySelector('#category').value,
      attachment_count: document.querySelectorAll('.document-item').length
    }));
    remaining();
    if (action.create && (state.title.trim() || state.body_length || state.attachment_count))
      return fail('NONEMPTY_DRAFT', state);
    if (!action.create && !matchesTitle(state.title)) return fail('EDITOR_IDENTITY_MISMATCH', state);
    const fields = await readWebsiteTaxonomy({playwright: page});
    remaining();
    return {ok: true, status: 'WEBSITE_EDITOR_READY', url: page.url(), authenticated: true,
      create: action.create, post_id: action.post_id || null, edit_id: editId || null, ...state, fields, ...timing()};
  } catch (error) {
    return fail('WEBSITE_PREPARE_INCOMPLETE', {error: String(error), message: 'Keep the page and inspect this failure; no submission was made.'});
  }
}
if (typeof module !== 'undefined') module.exports = {prepareWebsite};

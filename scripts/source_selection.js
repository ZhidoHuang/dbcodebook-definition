async (page, action, mode) => {
  let phase = 'page';
  const fail = (status, extra = {}) => ({ok: false, status, phase, ...extra});
  try {
    const expected = new URL(action.url), actual = new URL(page.url());
    if (actual.origin !== expected.origin || actual.pathname !== expected.pathname)
      return fail('WRONG_PAGE');
    const authenticated = await page.evaluate(() => window.__GUIDE_USER__?.authenticated ?? null);
    if (authenticated !== true) {
      if (authenticated !== false) return fail('LOGIN_STATE_UNKNOWN');
      if (mode === 'login-open') {
        const trigger = page.locator('.auth-panel-trigger[data-mode="login"]:visible');
        if (await trigger.count() !== 1) return fail('LOGIN_CONTROL_CHANGED');
        await trigger.click({timeout: 3000});
      }
      return fail('LOGIN_REQUIRED');
    }
    if (mode !== 'select') return {ok: true, status: 'LOGGED_IN'};
    phase = 'input';
    const modal = page.locator('#input-modal');
    if (await modal.isVisible()) return fail('INPUT_DIALOG_ALREADY_OPEN');
    const open = page.getByRole('button', {name: '批量输入标签', exact: true});
    if (await open.count() !== 1) return fail('SELECTION_CONTROL_CHANGED');
    await open.click({timeout: 3000});
    await page.locator('#tag-input').fill(action.input_text, {timeout: 3000});
    const confirm = page.locator('#input-modal .bili-btn.confirm');
    if (await confirm.count() !== 1) return fail('SELECTION_CONTROL_CHANGED');
    phase = 'submit_selection';
    // Attach the response listener before the one UI click; never call the API directly.
    const pending = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.origin === expected.origin &&
        url.pathname === expected.pathname + 'validate_tags/' &&
        response.request().method() === 'POST';
    }, {timeout: 12000}).then(response => response.ok() ? response.json() : null)
      .catch(() => null);
    await confirm.click({timeout: 3000});
    const result = await pending;
    if (!result || !Array.isArray(result.valid_tags) || !Array.isArray(result.invalid_tags))
      return fail('SELECTION_UNCERTAIN');
    if (result.invalid_tags.length) return fail('SOURCE_REJECTED', {invalid: result.invalid_tags});
    if (result.valid_tags.length !== action.aliases.length)
      return fail('SELECTION_COUNT_MISMATCH', {expected: action.aliases.length, received: result.valid_tags.length});
    phase = 'complete';
    await modal.waitFor({state: 'hidden', timeout: 5000});
    await page.locator('#loading-overlay').waitFor({state: 'hidden', timeout: 10000});
    const count = await page.locator('#tag-area .tag').count();
    if (count !== action.aliases.length) return fail('SELECTION_COUNT_MISMATCH', {count});
    const selected = await page.locator('#tag-area .tag').evaluateAll(tags => tags.map(tag => ({
      variable: tag.getAttribute('data-variable'), file: tag.getAttribute('data-file'),
      alias: tag.getAttribute('data-display'), text: tag.querySelector('.tag-text')?.textContent?.trim()
    })));
    const expectedRows = action.input_text.split('\n').map(line => {
      const [identity, alias] = line.split('=');
      const match = identity.match(/^([^()\s]+)\s+\((.+)\)$/);
      return {variable: match[1], file: match[2].trim(), alias};
    });
    const key = row => JSON.stringify([row.variable, row.file, row.alias]);
    if (selected.some(row => !row.variable || !row.file || !row.alias || row.text !== row.alias) ||
        JSON.stringify(selected.map(key).sort()) !== JSON.stringify(expectedRows.map(key).sort()))
      return fail('SELECTION_CONTENT_MISMATCH', {expected: expectedRows, selected});
    return {ok: true, status: 'SELECTION_READY', count, selected};
  } catch (error) {
    return fail('SELECTION_UNCERTAIN', {error: String(error)});
  }
}

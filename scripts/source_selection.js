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
    const scoped = action.kind === 'mhas_scoped_selection_v2';
    const rawColumns = action.kind === 'mhas_raw_column_selection_v1';
    let validatedSources;
    const stateKey = row => JSON.stringify([row.variable_id, row.variable, row.alias, row.periods]);
    const states = () => page.locator('#tag-area .tag').evaluateAll(tags => tags.map(t => ({
      variable_id: t.dataset.identity, variable: t.dataset.variable, alias: t.dataset.display,
      periods: JSON.parse(t.dataset.periods || JSON.stringify([t.dataset.period])).sort()
    })));
    if (action.rename_offset === undefined && !action.selection_resume) {
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
    if (result.valid_tags.length !== (scoped ? action.source_cell_count : action.aliases.length))
      return fail('SELECTION_COUNT_MISMATCH', {expected: action.aliases.length, received: result.valid_tags.length});
    if (rawColumns) {
      validatedSources = result.valid_tags.map(row => ({variable:row.variable,file:row.file,
        periods:String(row.wave || '').split(',').map(p=>p.trim()).filter(Boolean).sort(),
        raw_column:row.raw_column === true,input:row.input}));
      const key = row => JSON.stringify([row.variable,row.file,row.periods,row.raw_column,row.input]);
      const expected = action.selected.map(row=>({...row,raw_column:true,input:row.variable+' ('+row.file+')'}));
      if (JSON.stringify(validatedSources.map(key).sort()) !== JSON.stringify(expected.map(key).sort()))
        return fail('SELECTION_CONTENT_MISMATCH', {expected,validated_sources:validatedSources});
    }
    phase = 'complete';
    await modal.waitFor({state: 'hidden', timeout: 5000});
    await page.locator('#loading-overlay').waitFor({state: 'hidden', timeout: 10000});
    }
    if (action.selection_resume) {
      phase = 'complete';
      await page.locator('#input-modal').waitFor({state: 'hidden', timeout: 3000});
      await page.locator('#loading-overlay').waitFor({state: 'hidden', timeout: 10000});
    }
    let count = await page.locator('#tag-area .tag').count();
    if (scoped && action.rename_offset === undefined) {
      if (count !== action.initial.length) return fail('SELECTION_COUNT_MISMATCH', {count});
      const shape = row => JSON.stringify([row.variable_id, row.variable, row.periods]);
      const wanted = new Set(action.selected.map(shape));
      const observed = await page.locator('#tag-area .tag').evaluateAll(tags => tags.map(t => ({
        variable_id: t.dataset.identity, variable: t.dataset.variable,
        periods: JSON.parse(t.dataset.periods || JSON.stringify([t.dataset.period])).sort()
      })));
      if (JSON.stringify(observed.map(shape).sort()) !== JSON.stringify(action.initial.map(shape).sort()))
        return fail('SELECTION_CONTENT_MISMATCH', {observed});
      // Remove only this batch's verified over-broad tags, then select exact cells below.
      for (const row of observed.filter(row => !wanted.has(shape(row)))) {
        await page.locator('#tag-area .tag[data-identity="' + row.variable_id + '"][data-variable="' + row.variable + '"] .delete-btn').click({timeout: 3000, force: true});
      }
      const ready = new Set((await states()).map(stateKey));
      const next = action.selected.findIndex(row => !ready.has(stateKey(row)));
      if (next >= 0) return {ok: true, status: 'SELECTION_NAMES_PENDING', count, next_offset: next};
    }
    if (!scoped && count !== action.aliases.length) return fail('SELECTION_COUNT_MISMATCH', {count});
    if (scoped && action.rename_offset !== undefined) {
      phase = 'rename';
      const end = Math.min(action.rename_offset + 4, action.selected.length);
      for (const row of action.selected.slice(action.rename_offset, end)) {
        const base = '#tag-area .tag[data-identity="' + row.variable_id + '"][data-variable="' + row.variable + '"]';
        const selector = base + '[data-period="' + row.periods[0] + '"]';
        let tag = page.locator(selector);
        if (await tag.count() === 0) {
          if (row.periods.length !== 1) return fail('MHAS_PERIOD_CELL_REQUIRED', {row});
          const cell = await page.evaluate(row => {
            const rows = window.currentTableData || [];
            const ri = rows.findIndex(r => r.Variable_id === row.variable_id && r.File === row.file
              && r[row.periods[0] + '_variable'] === row.variable);
            const ci = [...document.querySelectorAll('#table-header th')].findIndex(h => h.dataset.column === row.periods[0]);
            return {ri, ci};
          }, row);
          if (cell.ri < 0 || cell.ci < 0) return fail('MHAS_PERIOD_CELL_NOT_VISIBLE', {row});
          const periodCell = page.locator('#table-body tr').nth(cell.ri).locator('td').nth(cell.ci);
          await periodCell.evaluate(element => element.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'}));
          await periodCell.click({timeout: 8000});
          tag = page.locator(selector);
        }
        if (await tag.count() !== 1) return fail('SELECTION_CONTENT_MISMATCH', {row});
        const periods = JSON.parse(await tag.getAttribute('data-periods') || JSON.stringify([await tag.getAttribute('data-period')])).sort();
        if (JSON.stringify(periods) !== JSON.stringify(row.periods)) return fail('SELECTION_CONTENT_MISMATCH', {row, periods});
        const before = await tag.getAttribute('data-display');
        if (before === row.alias) continue;
        if (before !== row.initial_alias) return fail('SELECTION_CONTENT_MISMATCH', {row, before});
        // Newly added year-cell tags ignore edit clicks for the site's 150ms guard.
        await page.waitForFunction(selector => {
          const tag = document.querySelector(selector);
          return tag && !tag.hasAttribute('data-just-added');
        }, selector, {timeout: 3000});
        await tag.locator('.tag-text').click({timeout: 3000});
        const input = tag.locator('.tag-input');
        await input.fill(row.alias, {timeout: 3000});
        await input.press('Enter', {timeout: 3000});
        await page.waitForFunction(({selector, alias}) => {
          const tag = document.querySelector(selector);
          return tag?.getAttribute('data-display') === alias && !tag.classList.contains('editing');
        }, {selector, alias: row.alias}, {timeout: 8000});
      }
      const ready = new Set((await states()).map(stateKey));
      const next = action.selected.findIndex((row, index) => index >= end && !ready.has(stateKey(row)));
      if (next >= 0) return {ok: true, status: 'SELECTION_NAMES_PENDING', count, next_offset: next};
    }
    count = await page.locator('#tag-area .tag').count();
    if (count !== action.selected?.length && scoped) return fail('SELECTION_COUNT_MISMATCH', {count});
    const selected = await page.locator('#tag-area .tag').evaluateAll((tags, database) => tags.map(tag => ({
      variable: tag.getAttribute('data-variable'), file: tag.getAttribute(database === 'nhanes' ? 'data-source-type' : 'data-file'),
      alias: tag.getAttribute('data-display'), text: tag.querySelector('.tag-text')?.textContent?.trim(),
      ...(database === 'mhas' && tag.dataset.identity ? {variable_id: tag.dataset.identity, periods: JSON.parse(tag.dataset.periods || JSON.stringify([tag.dataset.period])).sort(),
        dictionary_sha256: tag.dataset.dictionarySha256} : {})
    })), action.database);
    const expectedRows = scoped || rawColumns ? action.selected : action.input_text.split('\n').map(line => {
      const [identity, alias] = line.split('=');
      const match = identity.match(/^([^()\s]+)\s+\((.+)\)$/);
      return {variable: match[1], file: match[2].trim(), alias};
    });
    const key = row => JSON.stringify([row.variable, row.file, row.alias,
      ...(scoped ? [row.variable_id, row.periods, row.dictionary_sha256] : [])]);
    if (selected.some(row => !row.variable || !row.file || !row.alias || row.text !== row.alias) ||
        JSON.stringify(selected.map(key).sort()) !== JSON.stringify(expectedRows.map(key).sort()))
      return fail('SELECTION_CONTENT_MISMATCH', {expected: expectedRows, selected});
    return {ok: true, status: 'SELECTION_READY', count, selected,
      ...(rawColumns ? {validated_sources:validatedSources,dictionary_version_check:'local_binding'} : {})};
  } catch (error) {
    return fail('SELECTION_UNCERTAIN', {error: String(error)});
  }
}

async (page, action) => {
  const key = Symbol.for('dbCodeBook.sourceRead');
  if (page[key]?.running) return {ok:false,status:'READ_BUSY',message:'本标签的上一项读取尚未结束，未启动新动作。'};
  const operation = {request_id:action.request_id, running:true, result:null};
  page[key] = operation;
  const run = async () => {
  let phase = 'page';
  const started = Date.now();
  const diagnostics = {action:action.kind, searches:[]};
  const fail = (status, extra = {}) => ({ok:false, status, phase,
    diagnostics:{...diagnostics, elapsed_ms:Date.now()-started}, ...extra});
  const stop = code => { const error = new Error(code); error.code = code; throw error; };
  const norm = s => String(s ?? '').replace(/\s+/g, ' ').trim();
  try {
    const expected = new URL(action.url), actual = new URL(page.url());
    if (actual.origin !== expected.origin || actual.pathname !== expected.pathname) return fail('WRONG_PAGE');
    const auth = await page.evaluate(() => window.__GUIDE_USER__?.authenticated ?? null);
    if (auth !== true) return fail(auth === false ? 'LOGIN_REQUIRED' : 'LOGIN_STATE_UNKNOWN');
    const table = page.locator('#results-table');
    if (await table.count() !== 1) return fail('READ_CONTROL_CHANGED');

    // Listen before a normal UI action. Never send an API request ourselves.
    const search = async (query, click) => {
      phase = 'search';
      const since = Date.now();
      const observed = {query, request_observed:false, response_observed:false,
        response_timeout_ms:12000, table_timeout_ms:8000};
      diagnostics.searches.push(observed);
      const matchesRequest = request => {
        try {
          const u = new URL(request.url());
          return u.origin === expected.origin && u.pathname === expected.pathname &&
            request.method() === 'POST' && request.postDataJSON()?.search === query;
        } catch { return false; }
      };
      const onRequest = request => {
        if (matchesRequest(request)) {
          observed.request_observed = true; observed.request_ms = Date.now()-since;
        }
      };
      const onFailed = request => {
        if (matchesRequest(request)) {
          observed.request_observed = true;
          observed.request_failure = request.failure()?.errorText || 'unknown';
        }
      };
      page.on('request', onRequest);
      page.on('requestfailed', onFailed);
      try {
      const pending = page.waitForResponse(r => {
        try {
          const u = new URL(r.url());
          return u.origin === expected.origin && u.pathname === expected.pathname &&
            r.request().method() === 'POST' && r.request().postDataJSON()?.search === query;
        } catch { return false; }
      }, {timeout:12000}).catch(error => {
        observed.wait_error = error.name || 'Error'; return null;
      });
      phase = 'search_click';
      await click();
      observed.click_ms = Date.now()-since;
      phase = 'search_response';
      const response = await pending;
      if (!response) {
        if (observed.request_failure) stop('SEARCH_REQUEST_FAILED');
        if (observed.wait_error && observed.wait_error !== 'TimeoutError') stop('SEARCH_RESPONSE_WAIT_FAILED');
        stop(observed.request_observed ? 'SEARCH_RESPONSE_TIMEOUT' : 'SEARCH_REQUEST_NOT_OBSERVED');
      }
      observed.response_observed = true;
      observed.response_ms = Date.now()-since;
      observed.http_status = response.status();
      if (!response.ok()) stop('SEARCH_HTTP_ERROR');
      phase = 'search_body';
      let data;
      try { data = await response.json(); } catch { stop('SEARCH_RESPONSE_NOT_JSON'); }
      if (!data || data.status === 'fail' || !Array.isArray(data.data)) stop('SEARCH_REJECTED');
      const rows = data.data;
      observed.result_rows = rows.length;
      phase = 'search_table';
      // Match fresh response identities AND period counts against the visible table.
      await page.waitForFunction(rows => {
        const clean = s => String(s ?? '').replace(/\s+/g, ' ').trim();
        const table = document.querySelector('#results-table');
        const displayed = [...table.querySelectorAll('tbody tr')];
        // CHARLS clears the header when a fresh search returns no results.
        if (!rows.length) return displayed.length === 0 ||
          (displayed.length === 1 && displayed[0].querySelector('td[colspan]') !== null);
        const heads = [...table.querySelectorAll('thead th')].map(x => x.getAttribute?.('data-column') || x.innerText.trim().split(/\s/)[0]);
        const vi = heads.indexOf('Variable'), fi = heads.indexOf('File');
        if (vi < 0 || fi < 0) return false;
        return displayed.length === rows.length && rows.every((r, i) => {
          const cells = displayed[i].querySelectorAll('td');
          return clean(cells[vi]?.innerText) === clean(r.Variable) && clean(cells[fi]?.innerText) === clean(r.File) &&
            heads.every((h, j) => !/^\d{4}$|^Wave \d+$|^Corona Survey \d+$|^Cross-wave$/.test(h) || clean(cells[j]?.innerText) === clean(r[h]));
        });
      }, rows, {timeout:8000});
      return {total_results:data.total_results, total_pages:data.total_pages,
        page:response.request().postDataJSON().page, rows};
      } finally {
        observed.elapsed_ms = Date.now()-since;
        page.off('request', onRequest);
        page.off('requestfailed', onFailed);
      }
    };
    const submit = async query => {
      phase = 'search_fill';
      await page.locator('#search').fill(query, {timeout:3000});
      return search(query, () => page.getByRole('button', {name:'\uf002', exact:true}).click({timeout:3000}));
    };
    const summarize = result => ({...result, rows:result.rows.map(r => ({
      variable:r.Variable, file:r.File, label:r.Label,
      periods:Object.fromEntries(Object.entries(r).filter(([k]) => /^\d{4}$|^Wave \d+$|^Corona Survey \d+$|^Cross-wave$/.test(k)))
    }))});

    if (action.kind === 'directory') {
      phase = 'directory';
      let container = page.locator('.nav-item.nav-level-1').locator('..');
      // All top-level nodes share the same container; avoid hidden same-name descendants.
      container = container.first();
      let result = null;
      const path = action.path || [];
      for (let i = 0; i < path.length; i++) {
        phase = 'directory';
        const titles = container.locator(':scope > .nav-item > .nav-item-title');
        const names = await titles.evaluateAll(es => es.map(e => e.querySelector('span')?.textContent?.trim()));
        const matches = names.flatMap((name, index) => name === path[i] ? [index] : []);
        if (matches.length !== 1) return fail('DIRECTORY_AMBIGUOUS_OR_MISSING', {path:path.slice(0,i+1), candidates:names});
        const title = titles.nth(matches[0]), node = title.locator('..');
        if (!await title.isVisible()) return fail('DIRECTORY_NOT_VISIBLE');
        const state = await node.getAttribute('class');
        const parent = state.split(/\s+/).includes('parent-item');
        const expanded = state.split(/\s+/).includes('expanded');
        if ((parent && !expanded) || !parent) {
          if (i === 0 && parent) await title.click({timeout:3000});
          else {
            const query = path.slice(0,i+1).map((x,j) => `section${j+1}[${x}]`).join(' AND ');
            result = await search(query, () => title.click({timeout:3000}));
          }
        } else if (i === path.length - 1 && i > 0) {
          result = await submit(path.map((x,j) => `section${j+1}[${x}]`).join(' AND '));
        }
        if (!parent && i !== path.length - 1) return fail('DIRECTORY_IS_LEAF');
        container = node.locator(':scope > .nav-children');
      }
      const children = await container.locator(':scope > .nav-item > .nav-item-title > span').allTextContents();
      return {ok:true, status:'DIRECTORY_READ', path, children:children.map(norm), ...(result ? {results:summarize(result)} : {})};
    }
    if (action.kind === 'search') return {ok:true, status:'SEARCH_READ', query:action.query.trim(), ...summarize(await submit(action.query.trim()))};

    // One variable per action bounds execution time and preserves each completed receipt.
    const query = `Variable[${action.variable}] AND File[${action.file}]`;
    const result = await submit(query);
    const matches = result.rows.map((r,i) => ({r,i})).filter(x => x.r.Variable === action.variable && x.r.File === action.file);
    if (matches.length !== 1) return fail('SOURCE_AMBIGUOUS_OR_NOT_ON_PAGE', {query, ...summarize(result)});
    phase = 'detail';
    const {r, i} = matches[0];
    const heads = await table.locator('thead th').evaluateAll(es => es.map(x => x.getAttribute?.('data-column') || x.innerText.trim().split(/\s/)[0]));
    const details = [];
    for (const period of action.periods) {
      phase = 'detail';
      diagnostics.detail = {variable:action.variable, file:action.file, period,
        completed_periods:details.map(d => d.period), click_timeout_ms:3000, card_timeout_ms:3000};
      const col = heads.indexOf(period);
      if (col < 0) return fail('PERIOD_COLUMN_MISSING', {period, details});
      if (r[period] == null || r[period] === '' || r[period] === 0 || r[period] === '0') {
        details.push({period, status:'NO_RECORDS', count:r[period] ?? null}); continue;
      }
      const identity = `${action.variable} (${action.file})`;
      if (action.database === 'share') {
        // SHARE displays a transient tooltip rather than CHARLS' persistent detail cards.
        // Compare all published categories, including refusal/DK; do not infer a count denominator.
        await page.locator('#search').click({timeout:3000});
        await table.locator('tbody tr').nth(i).locator('td').nth(col).click({timeout:3000});
        const target = {variable:action.variable, label:r[`${period}_label`] ?? r.Label,
          summary:r[`${period}_summary`]};
        phase = 'detail_card';
        await page.waitForFunction(target => {
          const clean = s => String(s ?? '').replace(/\s+/g,' ').trim();
          const cards = [...document.querySelectorAll('.tooltip-content')].filter(e=>e.getClientRects().length);
          return cards.length === 1 && clean(cards[0].querySelector('.tooltip-title')?.textContent) === target.variable &&
            clean(cards[0].querySelector('.tooltip-item.label')?.textContent) === clean(target.label);
        }, target, {timeout:3000});
        const cards = await page.locator('.tooltip-content:visible').evaluateAll(es=>es.map(e=>({
          variable:e.querySelector('.tooltip-title')?.textContent?.trim(),
          label:e.querySelector('.tooltip-item.label')?.textContent?.trim(),
          text:e.innerText,
          distribution:[...e.querySelectorAll('.code-table tr')].map(row=>({
            label:row.querySelector('.code-cell')?.textContent?.trim(),
            count:row.querySelector('.count-cell')?.textContent?.trim()
          }))
        })));
        const card = cards[0];
        if (cards.length === 1 && !card.distribution.length)
          return fail('DETAIL_LAYOUT_UNSUPPORTED', {period, details, source_row:r, cards});
        if (cards.length !== 1 ||
            norm(card.distribution.map(x=>`${x.label} ( ${x.count} )`).join(', ')) !== norm(target.summary))
          return fail('DETAIL_CONTENT_MISMATCH', {period, details, source_row:r, cards});
        details.push({...card, identity, period, status:'DETAIL_READ', count:r[period],
          summary:target.summary, source:r[`${period}_text`] ?? '', source_row:r});
        continue;
      }
      const boxes = page.locator('#display-content .content-box');
      const read = async () => await boxes.evaluateAll((es, target) => {
        const clean = s => String(s ?? '').replace(/\s+/g, ' ').trim();
        return es.filter(e => clean(e.querySelector('.variable')?.textContent) === target.identity &&
          clean(e.querySelector('.year')?.textContent) === `[${target.period}]`).map(e => ({
            identity:clean(e.querySelector('.variable')?.textContent), period:target.period,
            label:e.querySelector('.label-text')?.textContent?.trim() ?? '',
            summary:e.querySelector('.summary-text')?.textContent?.trim() ?? '',
            source:e.querySelector('.year-text')?.textContent?.trim() ?? ''
          }));
      }, {identity, period});
      let cards = await read();
      if (!cards.length) {
        phase = 'detail_click';
        await table.locator('tbody tr').nth(i).locator('td').nth(col).click({timeout:3000});
        phase = 'detail_card';
        // Detail cards are produced synchronously by the cell handler; wait on their identity.
        await page.waitForFunction(target => [...document.querySelectorAll('#display-content .content-box')].some(e =>
          e.querySelector('.variable')?.textContent.replace(/\s+/g,' ').trim() === target.identity &&
          e.querySelector('.year')?.textContent.trim() === `[${target.period}]`), {identity, period}, {timeout:3000});
        cards = await read();
      }
      if (cards.length !== 1 || norm(cards[0].summary) !== norm(r[`${period}_summary`]) ||
          norm(cards[0].source) !== norm(r[`${period}_text`]) || norm(cards[0].label) !== norm(r[`${period}_label`]))
        return fail('DETAIL_CONTENT_MISMATCH', {period, details});
      details.push({...cards[0], status:'DETAIL_READ', count:r[period]});
    }
    return {ok:true, status:'SOURCE_READ', variable:action.variable, file:action.file, details};
  } catch (error) {
    const code = error.code || `${phase.toUpperCase()}_${error.name === 'TimeoutError' ? 'TIMEOUT' : 'FAILED'}`;
    const messages = {
      SEARCH_REQUEST_NOT_OBSERVED:'未观察到与本次搜索匹配的请求；不能据此断定请求未发送。',
      SEARCH_REQUEST_FAILED:'本次搜索请求连接失败，具体原因见 request_failure。',
      SEARCH_RESPONSE_TIMEOUT:'已观察到搜索请求，但未在时限内确认成功响应。',
      SEARCH_RESPONSE_WAIT_FAILED:'等待搜索响应时发生异常，具体类型见 wait_error。',
      SEARCH_HTTP_ERROR:'搜索收到非成功HTTP状态，具体状态码见 http_status。',
      SEARCH_RESPONSE_NOT_JSON:'搜索响应无法读取为JSON。',
      SEARCH_REJECTED:'网站拒绝搜索或响应缺少预期的结果列表。',
      SEARCH_TABLE_TIMEOUT:'已收到搜索结果，但页面表格未在时限内通过对应核对。',
      SEARCH_CLICK_TIMEOUT:'搜索点击未在时限内完成，具体控件状态见原始错误。',
      DETAIL_CLICK_TIMEOUT:'详情单元格点击未在时限内完成，变量和年份见 detail。',
      DETAIL_CARD_TIMEOUT:'点击后未在时限内找到对应变量和年份的详情。'
    };
    return fail('READ_INCOMPLETE', {error_code:code,
      message:messages[code] || '读取操作失败，具体步骤和原因见 phase 与 error。', error:String(error)});
  }
  };
  try {
    operation.result = {...await run(), operation_completed:true};
    return operation.result;
  } finally { operation.running = false; }
}

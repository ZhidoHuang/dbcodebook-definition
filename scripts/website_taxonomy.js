// Shared by the read-only options command and the fixed publication action.
async function readWebsiteTaxonomy(tab) {
  return tab.playwright.evaluate(() => {
    const fields = {
      directory_tag: ['directory-tag-trigger', 'directory-tag-options-data'],
      cross_database_topic: ['cross-database-topic-trigger', 'cross-database-topic-options-data']
    };
    const result = {};
    for (const [field, [triggerId, optionsId]] of Object.entries(fields)) {
      const trigger = document.getElementById(triggerId);
      const options = document.getElementById(optionsId);
      if (!trigger || !options) throw new Error('TAXONOMY_CONTROLS_MISSING: ' + field);
      result[field] = {
        current: trigger.dataset.value || '',
        options: Array.from(options.querySelectorAll('[data-value]'), node => node.dataset.value.trim()).filter(Boolean)
      };
    }
    return result;
  });
}

function resolveWebsiteTaxonomy(spec, options) {
  const normalize = text => String(text).trim().normalize('NFKC').toLowerCase();
  const matches = options.filter(value => normalize(value) === normalize(spec.value));
  if (matches.length > 1) throw new Error('TAXONOMY_AMBIGUOUS: ' + spec.value);
  if (matches.length === 1) return {value: matches[0], mode: 'existing'};
  if (spec.mode !== 'create') throw new Error('TAXONOMY_NO_MATCH: ' + spec.value);
  if (!Array.isArray(spec.options) || !String(spec.reason || '').trim()) {
    throw new Error('TAXONOMY_CREATION_REQUIRES_REVIEW: ' + spec.value);
  }
  const sorted = values => JSON.stringify([...new Set(values)].sort());
  if (sorted(spec.options) !== sorted(options)) throw new Error('TAXONOMY_OPTIONS_CHANGED: ' + spec.value);
  return {value: spec.value.trim(), mode: 'create'};
}

async function applyWebsiteTaxonomy(tab, plans) {
  const snapshot = await readWebsiteTaxonomy(tab);
  // Resolve both fields before changing either control.
  const decisions = Object.fromEntries(Object.entries(plans).map(([field, spec]) =>
    [field, resolveWebsiteTaxonomy(spec, snapshot[field].options)]));
  const triggers = {directory_tag: '#directory-tag-trigger', cross_database_topic: '#cross-database-topic-trigger'};
  for (const [field, decision] of Object.entries(decisions)) {
    if (snapshot[field].current === decision.value) continue;
    await tab.playwright.locator(triggers[field]).click();
    await tab.playwright.locator('#editor-taxonomy-select-menu .post-manager-select-input').fill(decision.value);
    const selector = '#editor-taxonomy-select-menu .post-manager-select-option' +
      (decision.mode === 'create' ? '.is-create' : ':not(.is-create)');
    const values = await tab.playwright.evaluate(selector =>
      Array.from(document.querySelectorAll(selector), node => node.dataset.value), selector);
    const index = values.indexOf(decision.value);
    if (index < 0 || values.lastIndexOf(decision.value) !== index) throw new Error('TAXONOMY_OPTION_NOT_UNIQUE: ' + field);
    await tab.playwright.locator(selector).nth(index).click();
    const actual = (await readWebsiteTaxonomy(tab))[field].current;
    if (actual !== decision.value) throw new Error('TAXONOMY_SELECTION_FAILED: ' + field);
  }
  return decisions;
}

async function verifyWebsiteTaxonomy(tab, decisions) {
  const current = await readWebsiteTaxonomy(tab);
  for (const [field, decision] of Object.entries(decisions)) {
    if (current[field].current !== decision.value) throw new Error('TAXONOMY_CHANGED_BEFORE_SUBMIT: ' + field);
  }
}

if (typeof module !== 'undefined') module.exports = {resolveWebsiteTaxonomy, readWebsiteTaxonomy, applyWebsiteTaxonomy, verifyWebsiteTaxonomy};

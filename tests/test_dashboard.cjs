// Dependency-free behavioral checks for the actual dashboard script.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function settle() {
  for (let index = 0; index < 20; index++) await new Promise(setImmediate);
}

function dashboard({ active = true, remembered = false, runs = [], workflowStatus = () => ({ status: 'RUNNING' }) } = {}) {
  const elements = new Map();
  const events = new Map();
  const timers = new Map();
  const calls = [];
  const saved = new Map();
  let created = false;
  let timerId = 0;
  if (remembered) saved.set('molt-temporal-run', JSON.stringify({ workflow_id: 'wf-test', status: 'RUNNING' }));
  function element(selector) {
    if (!elements.has(selector)) elements.set(selector, { textContent: '', innerHTML: '', dataset: {}, style: {}, disabled: false, value: '', files: [], appendChild() {}, remove() {} });
    return elements.get(selector);
  }
  const version = { id: 'v1', status: active ? 'ACTIVE' : 'AWAITING_APPROVAL', recipe: {}, verification: {} };
  const files = new Map();
  const document = {
    querySelector: element,
    createElement: () => ({ remove() {}, classList: { add() {}, remove() {} } }),
    documentElement: { dataset: {} },
    addEventListener: (event, fn) => events.set(event, fn),
  };
  const window = {
    setTimeout: (fn, delay) => { timers.set(++timerId, { fn, delay }); return timerId; },
    clearTimeout: id => timers.delete(id),
    matchMedia: () => ({ matches: false }),
    prompt: () => 'in/golden.csv',
    location: { href: '' },
  };
  const fetch = async (url, options = {}) => {
    calls.push({ url, options });
    let body;
    if (url.startsWith('/api/temporal-runs/')) body = workflowStatus();
    else if (url.endsWith('/temporal-runs')) body = { workflow_id: 'wf-test', status: 'STARTED' };
    else if (url === '/api/health') body = { status: 'ok', ollama: { status: 'unreachable', configured: true } };
    else if (url === '/api/config') body = { temporal: { address: '127.0.0.1:7233' } };
    else if (url === '/api/automations' && options.method === 'POST') { created = true; body = { id: 'a2', name: 'Monthly cleanup', description: 'Normalize the expense export' }; }
    else if (url === '/api/automations') body = { automations: created ? [{ id: 'a2', name: 'Monthly cleanup', description: 'Normalize the expense export' }] : [{ id: 'a1', name: 'Test automation' }] };
    else if (url.endsWith('/runs')) body = { runs };
    else if (url.endsWith('/versions')) body = { versions: [version] };
    else if (url.endsWith('/profile')) body = { columns: ['merchant', 'amount'], row_count: 2 };
    else body = { versions: [version], runs: [] };
    return { ok: true, text: async () => JSON.stringify(body) };
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../molt/web/app.js'), 'utf8'), {
    document, window, fetch, localStorage: { getItem: key => saved.get(key) || null, setItem: (key, value) => saved.set(key, value) },
  });
  return {
    element, calls, timers, saved,
    click: selector => events.get('click')({ target: { closest: match => match === selector ? { dataset: { runId: 'run-drift' } } : null } }),
    setValue: (selector, value) => { element(selector).value = value; },
    files,
  };
}

test('durable start polls to drift outcome rather than calling workflow completion success', async () => {
  let complete = false;
  const ui = dashboard({ workflowStatus: () => complete
    ? { status: 'COMPLETED', result: { status: 'BLOCKED_DRIFT' } }
    : { status: 'RUNNING' } });
  await settle();
  assert.equal(ui.element('#temporal-run-button').disabled, false);
  assert.match(ui.element('#model-chip').innerHTML, /Model unavailable/);
  ui.click('#temporal-run-button');
  await settle();
  const post = ui.calls.find(call => call.options.method === 'POST');
  assert.equal(post.url, '/api/automations/a1/temporal-runs');
  assert.equal(JSON.parse(post.options.body).wait, false);
  assert.equal(JSON.parse(ui.saved.get('molt-temporal-run')).workflow_id, 'wf-test');
  assert.match(ui.element('#temporal-status').textContent, /RUNNING/);
  complete = true;
  const timer = [...ui.timers.entries()].find(([, item]) => item.delay === 3000);
  assert.ok(timer);
  ui.timers.delete(timer[0]);
  await timer[1].fn();
  await settle();
  assert.match(ui.element('#temporal-status').textContent, /COMPLETED · Molt BLOCKED_DRIFT/);
  assert.equal([...ui.timers.values()].filter(item => item.delay === 3000).length, 0);
});

test('unapproved recipes cannot launch from the dashboard', async () => {
  const ui = dashboard({ active: false });
  await settle();
  assert.equal(ui.element('#temporal-run-button').disabled, true);
});

test('remembered run resumes checks; a status outage is not reported as workflow failure', async () => {
  const ui = dashboard({ remembered: true, workflowStatus: () => { throw new Error('connection unavailable'); } });
  await settle();
  assert.match(ui.element('#temporal-status').textContent, /Status unavailable; retrying/);
  assert.doesNotMatch(ui.element('#temporal-status').textContent, /FAILED/);
  assert.ok([...ui.timers.values()].some(item => item.delay === 3000));
});

test('builder creates an automation, profiles its CSV, and compiles a fixture candidate', async () => {
  const ui = dashboard({ active: false });
  await settle();
  ui.setValue('#builder-name', 'Monthly cleanup');
  ui.setValue('#builder-task', 'Normalize the expense export');
  ui.setValue('#builder-path', 'in/expense.csv');
  await ui.click('#create-automation-button');
  assert.ok(ui.calls.some(call => call.url === '/api/automations' && call.options.method === 'POST'));
  await ui.click('#profile-input-button');
  await settle();
  assert.ok(ui.calls.some(call => call.url.endsWith('/profile')));
  ui.element('#builder-source').value = 'fixture';
  await ui.click('#compile-recipe-button');
  await settle();
  const compile = ui.calls.find(call => call.url.endsWith('/compile'));
  assert.ok(compile);
  assert.equal(JSON.parse(compile.options.body).recipe_file, 'examples/recipes/expense-v1.json');
});

test('dashboard explains the contract and exposes structural drift details', async () => {
  const ui = dashboard({ runs: [{ id: 'run-drift', status: 'BLOCKED_DRIFT', rows_read: 4, rows_written: 0, llm_calls: 0, error_code: 'REQUIRED_COLUMN_MISSING', error_message: 'Missing required column', error_details: { missing: ['category'] }, input: '/workspace/in/changed.csv' }] });
  await settle();
  assert.match(ui.element('#journey-graph').innerHTML, /Profile input/);
  assert.match(ui.element('#journey-graph').innerHTML, /Drift blocked/);
  await ui.click('[data-run-id]');
  assert.equal(ui.element('#run-inspector').hidden, false);
  assert.match(ui.element('#run-inspector').innerHTML, /Why Molt blocked this file/);
  assert.match(ui.element('#run-inspector').innerHTML, /category/);
});

test('graphite dashboard uses truthful empty states and exposes roles and repair surface', () => {
  const html = fs.readFileSync(path.join(__dirname, '../molt/web/index.html'), 'utf8');
  const css = fs.readFileSync(path.join(__dirname, '../molt/web/style.css'), 'utf8');
  const script = fs.readFileSync(path.join(__dirname, '../molt/web/app.js'), 'utf8');
  assert.match(html, /No runs yet/);
  assert.match(html, /System and roles/);
  assert.match(html, /repair-card/);
  assert.match(css, /--bg:#131416/);
  assert.match(css, /Barlow Semi Condensed/);
  assert.doesNotMatch(html + css + script, /1,428|24,680|12\.4 ms|3\.5s agent/);
  assert.doesNotMatch(html + css + script, /🔍|↗|🧊|🛡️|💰|⏱️/);
});

test('dashboard explains recipe acceptance and the ordered repair path', () => {
  const html = fs.readFileSync(path.join(__dirname, '../molt/web/index.html'), 'utf8');
  const script = fs.readFileSync(path.join(__dirname, '../molt/web/app.js'), 'utf8');
  assert.match(html, /Recipe and approval/);
  assert.match(html, /The recipe is visible before it can run/);
  assert.match(script, /Accept recipe/);
  assert.match(script, /Candidate awaiting independent verification/);
  assert.match(script, /1\. Drift blocked/);
  assert.match(script, /2\. Ask Mastra/);
  assert.match(script, /3\. Candidate stored/);
  assert.match(script, /4\. Run tests/);
  assert.match(script, /5\. Human decision/);
  assert.match(script, /Not accepted/);
});

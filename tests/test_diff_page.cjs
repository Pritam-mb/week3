const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('evidence diff page is served with its companion assets', async () => {
  for (const file of ['diff.html', 'diff.css', 'diff.js']) {
    const content = fs.readFileSync(path.join(__dirname, '../molt/web', file), 'utf8');
    assert.ok(content.length > 100, `${file} should contain the evidence page`);
  }
  const html = fs.readFileSync(path.join(__dirname, '../molt/web/diff.html'), 'utf8');
  assert.match(html, /Before Molt/);
  assert.match(html, /After Molt/);
  assert.match(html, /DECISION TRACE/);
});

test('evidence diff page does not render raw CSV values by design', () => {
  const script = fs.readFileSync(path.join(__dirname, '../molt/web/diff.js'), 'utf8');
  assert.match(script, /error_details/);
  assert.match(script, /missing/);
  assert.doesNotMatch(script, /sample\s*:/);
});

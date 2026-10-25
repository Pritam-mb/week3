const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:8765/');
  await page.waitForTimeout(1000);

  const items = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('#automations-list [data-id]')).map(e => ({
      text: e.innerText.trim(),
      id: e.dataset.id
    }));
  });
  console.log('Automations in sidebar:', items);

  // Click on auto_6b98511d12c04ef2
  await page.click('[data-id="auto_6b98511d12c04ef2"]');
  await page.waitForTimeout(500);

  const uiState = await page.evaluate(() => {
    const beads = Array.from(document.querySelectorAll('#run-beads .run-bead')).map(e => ({
      text: e.innerText.trim(),
      className: e.className
    }));
    const runs = Array.from(document.querySelectorAll('#runs-body tr')).map(e => e.innerText.replace(/\s+/g, ' ').trim());
    const chart = document.querySelector('#chart-text-summary') ? document.querySelector('#chart-text-summary').innerText : '';
    const selectedTitle = document.querySelector('#selected-automation-title') ? document.querySelector('#selected-automation-title').innerText : '';
    const repairCard = document.querySelector('#repair-card') ? document.querySelector('#repair-card').innerText.replace(/\s+/g, ' ') : '';
    return { selectedTitle, beads, runs, chart, repairCard };
  });
  console.log('UI State for auto_6b98511d12c04ef2:\n', JSON.stringify(uiState, null, 2));

  await browser.close();
})();

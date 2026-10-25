from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1400, 'height': 900})
    page.goto('http://127.0.0.1:8765/')
    time.sleep(1)

    # Click on the last case (auto_6b98511d12c04ef2 - Expense Export Normalizer)
    page.click('[data-auto-id="auto_6b98511d12c04ef2"]')
    time.sleep(1)

    # Capture screenshot
    page.screenshot(path='evidence/dashboard_expense_verified.png')

    # Read state
    beads = page.eval_on_selector_all('#run-beads .run-bead', 'els => els.map(e => ({ text: e.innerText.trim(), className: e.className }))')
    runs = page.eval_on_selector_all('#runs-body tr', 'els => els.map(e => e.innerText.replace(/\\s+/g, " ").trim())')
    inspector = page.inner_text('#run-inspector') if page.query_selector('#run-inspector') else ''
    chart_summary = page.inner_text('#chart-text-summary') if page.query_selector('#chart-text-summary') else ''

    print('=== BEADS ===')
    for b in beads:
        print(b)
    print('\n=== RUNS TABLE ===')
    for r in runs:
        print(r)
    print('\n=== CHART SUMMARY ===')
    print(chart_summary)
    print('\n=== INSPECTOR ===')
    print(inspector.replace('\n', ' | ')[:200])

    browser.close()

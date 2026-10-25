from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1400, 'height': 900})
    page.goto('http://127.0.0.1:8765/')
    time.sleep(1)
    page.click('[data-auto-id="auto_6b98511d12c04ef2"]')
    time.sleep(1)
    steps = page.eval_on_selector_all('#journey-graph .lifecycle-step', 'els => els.map(e => ({ text: e.innerText.replace(/\\s+/g, " "), className: e.className }))')
    for s in steps:
        print(s)
    browser.close()

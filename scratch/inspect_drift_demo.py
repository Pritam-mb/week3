from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1400, 'height': 1200})
    page.goto('http://127.0.0.1:8765/')
    time.sleep(1)

    # Click on Drift & Mastra Repair Demo
    page.click('[data-auto-id="auto_d571a2f79bb14567"]')
    time.sleep(1)

    page.screenshot(path='evidence/dashboard_drift_demo.png', full_page=True)
    browser.close()

print('Saved evidence/dashboard_drift_demo.png successfully!')

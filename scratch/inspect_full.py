from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1400, 'height': 1200})
    page.goto('http://127.0.0.1:8765/')
    time.sleep(1)

    # Click on the last case (auto_6b98511d12c04ef2 - Expense Export Normalizer)
    page.click('[data-auto-id="auto_6b98511d12c04ef2"]')
    time.sleep(1)

    # Capture full page screenshot
    page.screenshot(path='evidence/dashboard_expense_full.png', full_page=True)

    browser.close()
print("Saved evidence/dashboard_expense_full.png successfully!")

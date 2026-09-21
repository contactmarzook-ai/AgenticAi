from playwright.sync_api import sync_playwright, expect
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("http://localhost:5173")
        page.locator("button:has-text('Admin')").click()
        page.wait_for_selector("text=Management")
        page.get_by_role("button", name="Management", exact=True).click()
        page.wait_for_selector("text=Platform Management")
        page.locator("button:has-text('Workflow Builder')").click()

        time.sleep(1)

        page.locator("button:has-text('Agent Node')").click()

        time.sleep(0.5)

        # Click on the agent node to select it (so properties sidebar updates)
        page.locator("text=Agent Node").last.click()

        time.sleep(0.5)

        page.screenshot(path="/home/jules/verification/workflow_builder_selected.png")

        browser.close()

if __name__ == "__main__":
    run()

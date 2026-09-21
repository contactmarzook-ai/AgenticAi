from playwright.sync_api import sync_playwright, expect
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Go to frontend
        page.goto("http://localhost:5173")

        # Click admin login
        page.locator("button:has-text('Admin')").click()

        # Wait for Management to load in sidebar
        page.wait_for_selector("text=Management")

        # Click Management
        page.get_by_role("button", name="Management", exact=True).click()

        # Wait for Management to load
        page.wait_for_selector("text=Platform Management")

        # Click Workflow Builder tab
        page.locator("button:has-text('Workflow Builder')").click()

        # Wait a bit
        time.sleep(1)

        # Add some nodes
        page.locator("button:has-text('Input Node')").click()
        page.locator("button:has-text('Agent Node')").click()
        page.locator("button:has-text('Condition Node')").click()
        page.locator("button:has-text('End Node')").click()

        # Wait a bit
        time.sleep(1)

        # Take a screenshot
        page.screenshot(path="/home/jules/verification/workflow_builder.png")

        browser.close()

if __name__ == "__main__":
    run()

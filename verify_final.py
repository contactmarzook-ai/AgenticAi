import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Login as Admin
        await page.goto("http://localhost:5173")
        await page.wait_for_selector("text=AgentOS")
        await page.click("button:has-text('Admin')")

        # Test Agents Schema Builder UI
        await page.wait_for_selector("text=Agents")
        await page.click("button:has-text('Agents')")

        # Wait for Agents page to load
        await page.wait_for_selector("h1:has-text('Agents')")
        await page.click("button:has-text('Create Agent')")

        # Wait for Modal
        await page.wait_for_selector("text=Create New Agent")
        await page.wait_for_selector("text=Input Schema Builder")

        await page.screenshot(path="verification/agents_schema_modal.png")

        # Close the modal
        await page.click("button:has-text('Cancel')")

        # Test Chat Session Deletion UI
        await page.click("button:has-text('New Chat')")
        await page.wait_for_selector("text=Chat")
        # Ensure there's a chat session
        await page.fill("input[placeholder*='Type your request']", "Hello World")
        await page.press("input[placeholder*='Type your request']", "Enter")
        await page.wait_for_selector("text=Reasoning") # wait for response

        # Look for Trash icon in sidebar by hovering over a session
        await page.hover("text=Hello World")

        await page.screenshot(path="verification/sidebar_with_trash.png")

        await browser.close()
        print("Final verification script completed.")

if __name__ == "__main__":
    asyncio.run(main())

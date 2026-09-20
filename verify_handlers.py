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
        await page.wait_for_selector("text=Agent Handler")

        await page.screenshot(path="verification/agents_handler_modal.png")

        await browser.close()
        print("Final verification script completed.")

if __name__ == "__main__":
    asyncio.run(main())

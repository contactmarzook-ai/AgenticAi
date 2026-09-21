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

        # Test Chat UI doesn't have reasoning block
        await page.click("button:has-text('New Chat')")
        await page.wait_for_selector("text=Chat")
        await page.fill("input[placeholder*='Type your request']", "Hello World")
        await page.press("input[placeholder*='Type your request']", "Enter")
        # Wait for the system response, there shouldn't be any reasoning block anymore
        await asyncio.sleep(3)
        await page.screenshot(path="verification/clean_chat_ui.png")

        # Open Management Tab
        await page.click("button:has-text('Management')")
        await page.wait_for_selector("text=Platform Management")

        await page.screenshot(path="verification/agent_management.png")

        # Open Monitoring Tab
        await page.click("button:has-text('Execution Monitoring')")
        await page.wait_for_selector("text=Avg Latency")

        await page.screenshot(path="verification/monitoring_tab.png")

        await browser.close()
        print("Final verification script completed.")

if __name__ == "__main__":
    asyncio.run(main())

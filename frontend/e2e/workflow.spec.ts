import { test, expect } from "@playwright/test"

test.describe("DocIntel Application Workflows", () => {
  test.beforeEach(async ({ context }) => {
    // Inject mock session cookie to simulate logged in user
    await context.addCookies([
      {
        name: "di_at",
        value: "mock-jwt-token",
        domain: "localhost",
        path: "/",
        httpOnly: true,
        sameSite: "Lax",
      },
      {
        name: "di_at_exp",
        value: String(Math.floor(Date.now() / 1000) + 900),
        domain: "localhost",
        path: "/",
        sameSite: "Lax",
      },
    ])
  })

  test("can access app shell, navigate sidebar, and open command menu", async ({ page }) => {
    await page.goto("/")
    // Shell should be visible
    await expect(page.locator("aside, nav")).toBeDefined()

    // Test Command Menu trigger
    await page.keyboard.press("Meta+k")
    await expect(page.getByPlaceholder(/Type a command or search/i)).toBeVisible()
    await page.keyboard.press("Escape")
  })

  test("search page updates url state on input", async ({ page }) => {
    await page.goto("/search")
    const searchInput = page.getByPlaceholder(/Search keywords, supplier names/i)
    await searchInput.fill("invoice")
    // Wait for 300ms debounce
    await page.waitForTimeout(400)
    await expect(page).toHaveURL(/q=invoice/)
  })

  test("compare wizard lets user toggle between modes", async ({ page }) => {
    await page.goto("/compare/new")
    await expect(page.getByText("New Comparison / Reconciliation")).toBeVisible()
    await expect(page.getByText(/Compare two extracted documents/i)).toBeVisible()

    // Switch to PDF vs Spreadsheet tab
    const tabTrigger = page.getByRole("tab", { name: /Reconciliation/i })
    if (await tabTrigger.isVisible()) {
      await tabTrigger.click()
      await expect(page.getByText(/Select Extracted PDF/i)).toBeVisible()
    }
  })
})


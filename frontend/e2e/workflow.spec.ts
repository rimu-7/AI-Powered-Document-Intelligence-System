import { test, expect } from "@playwright/test"

test.describe("DocIntel Application Workflows", () => {
  test("can access app shell, navigate sidebar, and open command menu", async ({
    page,
  }) => {
    await page.goto("/")
    await expect(page).toHaveURL("/")
    await expect(
      page.getByRole("link", { name: "Documents" }).first()
    ).toBeVisible()

    // Test Command Menu trigger
    await page.keyboard.press("ControlOrMeta+k")
    await expect(
      page.getByPlaceholder(/Type a command or search/i)
    ).toBeVisible()
    await page.keyboard.press("Escape")
  })

  test("search page updates url state on input", async ({ page }) => {
    await page.goto("/search")
    const searchInput = page.getByPlaceholder(
      /Search keywords, supplier names/i
    )
    await searchInput.fill("invoice")
    // Wait for 300ms debounce
    await page.waitForTimeout(400)
    await expect(page).toHaveURL(/q=invoice/)
  })

  test("compare wizard lets user toggle between modes", async ({ page }) => {
    await page.goto("/compare/new")
    await expect(
      page.getByText("New Comparison / Reconciliation")
    ).toBeVisible()
    await expect(page.getByText("Compare Two Documents")).toBeVisible()

    await page.getByRole("tab", { name: /Reconciliation/i }).click()
    await expect(
      page.getByText("Reconcile Invoices with Spreadsheet")
    ).toBeVisible()
  })
})

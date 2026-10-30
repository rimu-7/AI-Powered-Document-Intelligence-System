import { test, expect } from "@playwright/test"

test.describe("Authentication flow", () => {
  test("redirects unauthenticated users to /login with next parameter", async ({
    page,
  }) => {
    await page.goto("/documents")
    await expect(page).toHaveURL(/\/login\?next=%2Fdocuments/)
  })

  test("displays validation errors when submitting empty form", async ({
    page,
  }) => {
    await page.goto("/login")
    await page.click('button[type="submit"]')

    await expect(page.getByText(/Invalid email address/i)).toBeVisible()
    await expect(
      page.getByText(/Password must be at least 12 characters/i)
    ).toBeVisible()
  })

  test("shows registration link if registration mode is open", async ({
    page,
  }) => {
    await page.goto("/login")
    const registerLink = page.getByRole("link", {
      name: /Register organization/i,
    })
    await expect(registerLink).toBeVisible()
    await registerLink.click()
    await expect(page).toHaveURL(/\/register/)
  })
})

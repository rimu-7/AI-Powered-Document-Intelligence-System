import { test, expect } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

test.describe("Accessibility (axe-core)", () => {
  test("login page meets WCAG 2.1 AA accessibility in light mode", async ({ page }) => {
    await page.goto("/login")
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze()

    const criticalOrSerious = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious"
    )
    expect(criticalOrSerious).toEqual([])
  })

  test("register page meets WCAG 2.1 AA accessibility", async ({ page }) => {
    await page.goto("/register")
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze()

    const criticalOrSerious = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious"
    )
    expect(criticalOrSerious).toEqual([])
  })
})


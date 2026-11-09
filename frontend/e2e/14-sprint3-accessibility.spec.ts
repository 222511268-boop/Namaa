import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

test("Sprint 3 reports and activity are accessible on desktop and phone", async ({ page }) => {
  test.setTimeout(180_000);
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await signInAs(page, "viewer");
    await page.goto("/reports");
    await expect(page.getByRole("heading", { name: /Green spaces \(/ })).toBeVisible();
    const reports = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(reports.violations.filter(v => v.impact === "serious" || v.impact === "critical")).toEqual([]);
    await signInAs(page, "admin");
    await page.goto("/activity");
    await expect(page.getByRole("table")).toBeVisible();
    const activity = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(activity.violations.filter(v => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  }
});

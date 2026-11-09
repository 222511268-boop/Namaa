import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

// Uses real Sentinel-2 data from the Planetary Computer for the imported Al Rawdah parks.
test.describe("US07 Process satellite observations and US08 condition history", () => {
  test.setTimeout(8 * 60_000);

  test("AC-07.1 manager starts a run that completes in the background", async ({ page }) => {
    await signInAs(page, "manager");
    await page.getByRole("link", { name: "Satellite data", exact: true }).filter({ visible: true }).click();
    await expect(page).toHaveURL(/\/processing$/);
    await expect(page.getByRole("heading", { name: "Start a processing run" })).toBeVisible();
    await page.getByLabel("From").filter({ visible: true }).fill("2025-06-01");
    await expect(page.getByLabel("From").filter({ visible: true })).toHaveValue("2025-06-01");
    await page.getByLabel("To").filter({ visible: true }).fill("2025-06-20");
    await page.getByLabel("To").filter({ visible: true }).blur();
    await expect(page.getByLabel("To").filter({ visible: true })).toHaveValue("2025-06-20");
    await page.getByRole("button", { name: "Start run" }).filter({ visible: true }).click();
    await expect(page.getByText("Run queued.")).toBeVisible();
    const latest = page.getByTestId("run-list").locator("li").first();
    await expect(latest).toContainText("Sentinel-2 vegetation · 2025-06-01 to 2025-06-20");
    await expect(latest).toContainText("Completed", { timeout: 7 * 60_000 });
    await expect(latest).toContainText(/observations written/);
  });

  test("AC-08.1–08.4 profile shows the condition chart, attribution, quality and explanations", async ({ page }) => {
    await signInAs(page, "viewer");
    await page.goto("/map");
    // Open a site that now has satellite observations (an imported Al Rawdah park).
    await page.getByTestId("site-list").locator('a[data-has-observation="true"]').first().click();
    const chart = page.getByTestId("condition-chart");
    await expect(chart).toBeVisible();
    await expect(page.getByText("Satellite-derived", { exact: true }).first()).toBeVisible();
    await expect(page.getByTestId("s2-attribution")).toHaveText(/Contains modified Copernicus Sentinel data 2025/);
    await expect(page.getByTestId("data-quality")).toContainText("Usable observations");

    // Keyboard access to values (AC-08.1).
    await chart.focus();
    await page.keyboard.press("End");
    await expect(page.getByRole("status").filter({ hasText: "NDVI" })).toContainText(/Jun 2025/);

    // Table view lists every observation.
    await page.getByRole("button", { name: "Show as table" }).filter({ visible: true }).click();
    await expect(page.getByRole("table")).toContainText("Clear pixels");

    // AC-08.4 explanations including the caveat.
    await page.getByText("What do NDVI and NDMI mean?").click();
    await expect(page.getByText("Greenness is not the same as health.")).toBeVisible();
  });

  test("AC-08.5 a site without observations shows a clear message", async ({ page }) => {
    await signInAs(page, "viewer");
    await page.goto("/map");
    await page.getByLabel("Search by name").filter({ visible: true }).fill("E2E Small Planter");
    await expect(page.getByTestId("result-count")).toHaveText("1 site");
    await page.getByTestId("site-list").getByText("E2E Small Planter").click();
    await expect(page).toHaveURL(/\/sites\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("no-observations")).toBeVisible();
    await expect(page.getByTestId("condition-chart")).toHaveCount(0);
  });
});

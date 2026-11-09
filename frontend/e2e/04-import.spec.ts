import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

// The E2E stack answers Overpass queries with a real response recorded for Al Rawdah District.
test.describe("US04 Import green spaces", () => {
  test("AC-04.1 manager imports a district and sees a summary; AC-04.2 repeating creates nothing new", async ({ page }) => {
    await signInAs(page, "manager");
    await page.getByRole("link", { name: "Import", exact: true }).filter({ visible: true }).click();
    await page.getByLabel("Filter districts").filter({ visible: true }).fill("Rawdah");
    await page.getByLabel("District", { exact: true }).filter({ visible: true }).selectOption({ label: "Al Rawdah District · الروضة" });
    await page.getByRole("button", { name: "Import parks" }).filter({ visible: true }).click();
    const summary = page.getByTestId("import-summary");
    await expect(summary).toBeVisible({ timeout: 60_000 });
    const added = Number(await summary.locator("dd").nth(1).textContent());
    expect(added).toBeGreaterThan(0);
    await expect(page.getByText("Data © OpenStreetMap contributors")).toBeVisible();

    await page.getByRole("button", { name: "Import parks" }).filter({ visible: true }).click();
    await expect(summary.locator("dd").nth(1)).toHaveText("0");
    await expect(summary.locator("dd").nth(2)).toHaveText(String(added));
  });

  test("AC-04.5 imported sites are flagged for review", async ({ page }) => {
    await signInAs(page, "manager");
    await page.goto("/map");
    await expect(page.getByTestId("site-list").getByText("Needs review").first()).toBeVisible();
  });
});

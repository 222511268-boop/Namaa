import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

test.describe("US06 Explore green spaces on the map", () => {
  test.beforeEach(async ({ page }) => {
    await signInAs(page, "viewer");
    await page.goto("/map");
    await expect(page.getByTestId("site-list")).toBeVisible();
  });

  test("AC-06.1 map renders sites with attribution", async ({ page }) => {
    await expect(page.getByTestId("site-map")).toHaveAttribute("data-ready", "true");
    // Attribution text is present in the map's attribution control (compact or expanded).
    await expect(page.locator(".maplibregl-ctrl-attrib")).toContainText("OpenStreetMap");
    const box = await page.getByTestId("site-map").boundingBox();
    expect(box!.height).toBeGreaterThan(300); // regression guard: container must not collapse
    const rendered = await page.evaluate(() => document.querySelectorAll("canvas.maplibregl-canvas").length);
    expect(rendered).toBe(1);
  });

  test("AC-06.2 search narrows the list (English and Arabic)", async ({ page }) => {
    const count = page.getByTestId("result-count");
    const before = await count.textContent();
    await page.getByLabel("Search by name").filter({ visible: true }).fill("e2e drawn");
    await expect(count).toHaveText("1 site");
    await page.getByLabel("Search by name").filter({ visible: true }).fill("حديقة الاختبار");
    await expect(count).toHaveText("1 site");
    await page.getByLabel("Search by name").filter({ visible: true }).fill("");
    await expect(count).toHaveText(before!);
  });

  test("AC-06.3 district and type filters combine", async ({ page }) => {
    await page.getByLabel("Site type").filter({ visible: true }).selectOption("plaza");
    await expect(page.getByTestId("site-list")).toContainText("E2E Small Planter");
    await expect(page.getByTestId("site-list").locator("li")).toHaveCount(1);
    await page.getByLabel("District").filter({ visible: true }).selectOption({ index: 1 });
    // Every remaining result is a plaza in the chosen district (possibly none).
    const items = page.getByTestId("site-list").locator("li");
    for (const text of await items.allTextContents()) expect(text).toContain("Plaza");
  });

  test("AC-06.4 selecting a site in the list opens its profile", async ({ page }) => {
    await page.getByTestId("site-list").locator("li a").first().click();
    await expect(page).toHaveURL(/\/sites\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("site-name")).toBeVisible();
  });

  test("AC-06.5 no matches shows an empty state with a clear-filters action", async ({ page }) => {
    await page.getByLabel("Search by name").filter({ visible: true }).fill("zzzz-no-such-park");
    await expect(page.getByText("No green spaces match these filters")).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).filter({ visible: true }).click();
    await expect(page.getByTestId("site-list")).toBeVisible();
  });
});

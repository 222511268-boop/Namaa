import { expect, test } from "@playwright/test";
import { chooseChip, drawPolygon, signInAs } from "./helpers";

test.describe("US05 Register and edit a green space", () => {
  test("AC-05.1 draw a boundary, register the site, and see the calculated area", async ({ page }) => {
    await signInAs(page, "manager");
    await page.goto("/sites/new");
    await drawPolygon(page, [[0.45, 0.45], [0.55, 0.45], [0.55, 0.55], [0.45, 0.55]]);
    await page.getByLabel("Name (English)").filter({ visible: true }).fill("E2E Drawn Park");
    await page.getByRole("button", { name: "+ Arabic name and notes" }).filter({ visible: true }).click();
    await page.getByLabel("Name (Arabic, optional)").filter({ visible: true }).fill("حديقة الاختبار");
    await chooseChip(page, "Site type", "Park");
    await chooseChip(page, "Planting category", "Mixed planting");
    await page.getByRole("button", { name: "Register green space" }).filter({ visible: true }).click();
    await expect(page.getByTestId("site-name")).toHaveText("E2E Drawn Park");
    await expect(page.getByText("Drawn in Namaa")).toBeVisible();
    await expect(page.getByText(/\d[\d,.]* (ha|m²)/).first()).toBeVisible();
  });

  test("AC-05.3 missing details are reported per field", async ({ page }) => {
    await signInAs(page, "manager");
    await page.goto("/sites/new");
    await page.getByRole("button", { name: "Register green space" }).filter({ visible: true }).click();
    await expect(page.getByText("Enter the green space's name.")).toBeVisible();
    await expect(page.getByText("Choose a site type.")).toBeVisible();
    await expect(page.getByText("Choose a planting category.")).toBeVisible();
    await expect(page.getByText("Draw the boundary on the map.")).toBeVisible();
  });

  test("AC-05.5 a small boundary is flagged low confidence", async ({ page }) => {
    await signInAs(page, "manager");
    await page.goto("/sites/new");
    const editor = page.getByTestId("boundary-editor");
    await expect(editor).toHaveAttribute("data-ready", "true");
    for (let i = 0; i < 6; i++) await page.getByRole("button", { name: "Zoom in" }).filter({ visible: true }).click();
    await page.waitForTimeout(800);
    await drawPolygon(page, [[0.49, 0.49], [0.51, 0.49], [0.51, 0.51], [0.49, 0.51]]);
    await page.getByLabel("Name (English)").filter({ visible: true }).fill("E2E Small Planter");
    await chooseChip(page, "Site type", "Plaza");
    await chooseChip(page, "Planting category", "Shrubs and groundcover");
    await page.getByRole("button", { name: "Register green space" }).filter({ visible: true }).click();
    await expect(page.getByTestId("site-name")).toHaveText("E2E Small Planter");
    await expect(page.getByText("Low confidence")).toBeVisible();
  });

  test("AC-05.4 edits persist after reopening", async ({ page }) => {
    await signInAs(page, "manager");
    await page.goto("/map");
    await page.getByLabel("Search by name").filter({ visible: true }).fill("E2E Drawn Park");
    await expect(page.getByTestId("result-count")).toHaveText("1 site");
    await page.getByTestId("site-list").getByText("E2E Drawn Park").click();
    await expect(page).toHaveURL(/\/sites\/[0-9a-f-]{36}$/);
    await page.getByRole("button", { name: "Edit details" }).filter({ visible: true }).click();
    await page.getByLabel("Name (English)").filter({ visible: true }).fill("E2E Drawn Park (renamed)");
    await chooseChip(page, "Planting category", "Trees");
    await page.getByRole("button", { name: "Save changes" }).filter({ visible: true }).click();
    await expect(page.getByTestId("site-name")).toHaveText("E2E Drawn Park (renamed)");
    await page.reload();
    await expect(page.getByTestId("site-name")).toHaveText("E2E Drawn Park (renamed)");
    await expect(page.getByText("Trees", { exact: true })).toBeVisible();
  });
});

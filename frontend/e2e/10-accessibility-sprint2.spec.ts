import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { signInAs } from "./helpers";

// Accessibility scans for the Sprint 2 screens (runs after 09, which creates the data).
async function scan(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).exclude(".maplibregl-canvas").analyze();
  return results.violations
    .filter((v) => v.impact === "critical" || v.impact === "serious")
    .map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")})`);
}

test("attention queue", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto("/queue");
  await page.getByLabel("Status").filter({ visible: true }).selectOption("all");
  await expect(page.getByTestId("signal-list")).toBeVisible();
  expect(await scan(page)).toEqual([]);
});

test("signal evidence", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto("/queue");
  await page.getByLabel("Status").filter({ visible: true }).selectOption("all");
  await page.getByTestId("signal-list").locator("a").first().click();
  await expect(page.getByTestId("condition-chart")).toBeVisible();
  expect(await scan(page)).toEqual([]);
});

test("task detail and task list", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto("/tasks");
  await page.getByLabel("Show").filter({ visible: true }).selectOption("all");
  await expect(page.getByTestId("task-list")).toBeVisible();
  expect(await scan(page)).toEqual([]);
  await page.getByTestId("task-list").locator("a").first().click();
  await expect(page.getByTestId("task-title")).toBeVisible();
  expect(await scan(page)).toEqual([]);
});

test("account and reset pages", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "Account" })).toBeVisible();
  expect(await scan(page)).toEqual([]);
  await page.goto("/reset-password?token=invalid-token-value");
  await expect(page.getByText(/invalid or has expired/)).toBeVisible();
  expect(await scan(page)).toEqual([]);
});

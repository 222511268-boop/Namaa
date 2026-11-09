import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

// NFR-S2: automated accessibility scan reports no critical or serious violations on core screens.
async function scan(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .exclude(".maplibregl-canvas") // the map canvas is supplementary; the list provides the same content
    .analyze();
  const blocking = results.violations.filter((v) => v.impact === "critical" || v.impact === "serious");
  return blocking.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`);
}

test("login page", async ({ page }) => {
  await page.goto("/login");
  expect(await scan(page)).toEqual([]);
});

test("map page", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto("/map");
  await expect(page.getByTestId("site-list")).toBeVisible();
  expect(await scan(page)).toEqual([]);
});

test("site profile", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto("/map");
  await page.getByTestId("site-list").locator("li a").first().click();
  await expect(page.getByTestId("site-name")).toBeVisible();
  expect(await scan(page)).toEqual([]);
});

test("users page", async ({ page }) => {
  await signInAs(page, "admin");
  await page.goto("/users");
  await expect(page.getByTestId("user-table")).toBeVisible();
  expect(await scan(page)).toEqual([]);
});

test("mobile layout keeps navigation reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await page.getByLabel("Email").filter({ visible: true }).fill("e2e.viewer@example.com");
  await page.getByLabel("Password").filter({ visible: true }).fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).filter({ visible: true }).click();
  await page.getByRole("button", { name: "Menu" }).filter({ visible: true }).click();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Green spaces" }).click();
  await expect(page.getByRole("heading", { name: "Green spaces" })).toBeVisible();
});

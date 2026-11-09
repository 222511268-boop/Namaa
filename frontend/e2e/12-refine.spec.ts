import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

// CR-04 click reduction: command palette, shortcuts, quick preview, inline editing, live status, smart defaults.

test("command palette finds a green space and opens it with the keyboard", async ({ page }) => {
  await signInAs(page, "manager");
  await page.keyboard.press("Control+k");
  const palette = page.getByTestId("command-palette");
  await expect(palette).toBeVisible();
  await page.keyboard.type("Small Planter");
  await expect(palette.getByRole("option", { name: /E2E Small Planter/ })).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("site-name").filter({ visible: true })).toHaveText("E2E Small Planter");
});

test("command palette offers only the actions the role allows", async ({ page }) => {
  await signInAs(page, "inspector");
  await page.keyboard.press("Control+k");
  const palette = page.getByTestId("command-palette");
  await expect(palette.getByRole("option", { name: /Keyboard shortcuts/ })).toBeVisible();
  await expect(palette.getByRole("option", { name: /Register a green space/ })).toHaveCount(0);
  await expect(palette.getByRole("option", { name: /Update satellite data/ })).toHaveCount(0);
  await expect(palette.getByRole("option", { name: /^Users$/ })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(palette).toBeHidden();
});

test("shortcuts: / focuses the list search, ? lists the shortcuts", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto("/map");
  await expect(page.getByTestId("site-list").filter({ visible: true })).toBeVisible();
  await page.keyboard.press("/");
  await expect(page.getByLabel("Search by name").filter({ visible: true })).toBeFocused();
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("?");
  const dialog = page.getByRole("dialog", { name: "Keyboard shortcuts" });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("map list quick preview shows the condition trend without leaving the map", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto("/map");
  const row = page.getByTestId("site-list").filter({ visible: true }).locator("li").filter({ has: page.locator('a[data-has-observation="true"]') }).first();
  await row.getByRole("button", { name: /^Preview/ }).click();
  const preview = page.getByTestId("site-preview").filter({ visible: true });
  await expect(preview.getByTestId("preview-name")).toBeVisible();
  await expect(preview.getByRole("img", { name: /^NDVI from/ })).toBeVisible();
  await expect(preview.getByRole("link", { name: /Open profile/ })).toBeVisible();
  await expect(page).toHaveURL(/\/map$/);
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("site-preview")).toHaveCount(0);
});

test("inline editing opens in place, focuses the name and Esc cancels without saving", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto("/map");
  await page.getByLabel("Search by name").filter({ visible: true }).fill("E2E Small Planter");
  await expect(page.getByTestId("result-count")).toHaveText("1 site");
  await page.getByTestId("site-list").filter({ visible: true }).locator("li a").first().click();
  const name = page.getByTestId("site-name").filter({ visible: true });
  await expect(name).toHaveText("E2E Small Planter");
  await page.getByRole("button", { name: /Edit details|Review details/ }).filter({ visible: true }).click();
  const field = page.getByLabel("Name (English)").filter({ visible: true });
  await expect(field).toBeFocused();
  await field.fill("Should not be saved");
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("inline-editor")).toHaveCount(0);
  await expect(name).toHaveText("E2E Small Planter");
});

test("Update now queues a run and live status appears without a reload", async ({ page }) => {
  await signInAs(page, "manager");
  // Stub the run itself: real Sentinel-2 processing is covered by AC-07.1. This checks the live UI.
  const now = new Date().toISOString();
  const queued = {
    id: "00000000-0000-0000-0000-0000000000aa", kind: "sentinel2", status: "running", params: { start_date: "2025-06-01", end_date: "2025-06-02" },
    requested_by_name: "Maha Manager", scenes_found: 10, scenes_processed: 4, items_written: 3, items_skipped: 0, error: null, messages: [],
    created_at: now, started_at: now, finished_at: null,
  };
  let started = false;
  await page.route("**/api/processing-runs", async (route) => {
    if (route.request().method() === "POST") {
      started = true;
      return route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify(queued) });
    }
    if (!started) return route.continue();
    const res = await route.fetch();
    return route.fulfill({ response: res, json: [queued, ...(await res.json())] });
  });
  await page.getByTestId("satellite-card").filter({ visible: true }).getByRole("button", { name: "Update now" }).click();
  await expect(page.getByTestId("toast").filter({ hasText: "Run queued" })).toBeVisible();
  await expect(page.getByTestId("live-run").filter({ visible: true })).toContainText("4 / 10 scenes");
  await expect(page).toHaveURL(/\/$/);
});

test("new accounts get a generated password; reset links are copied automatically", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await signInAs(page, "admin");
  await page.goto("/users");
  const password = page.getByLabel("Initial password").filter({ visible: true });
  await expect(password).toHaveValue(/^[A-Za-z0-9]{14}$/);
  await page.locator('tr[data-email="e2e.manager@example.com"]').getByRole("button", { name: "Reset link" }).click();
  await expect(page.getByTestId("toast").filter({ hasText: "copied" })).toBeVisible();
  const link = await page.getByTestId("reset-link").inputValue();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(link);
});

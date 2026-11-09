import { expect, test, type Page } from "@playwright/test";
import { signIn, signInAs, USERS } from "./helpers";

// CR-03 redesign quality bars: keyboard access to the new shell, theme choice, the first-run strip,
// reduced motion, and no horizontal overflow at 360 px.

async function noOverflow(page: Page) {
  // The page must never be wider than the viewport (P1 in the redesign audit).
  await page.waitForTimeout(300);
  const { scroll, client } = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(scroll, `page width at ${page.url()}`).toBeLessThanOrEqual(client);
}

test("mobile menu works with the keyboard: opens, Esc closes, focus returns", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 780 });
  await signInAs(page, "inspector");
  const menu = page.getByRole("button", { name: "Menu" }).filter({ visible: true });
  await menu.focus();
  await page.keyboard.press("Enter");
  const drawer = page.getByRole("dialog", { name: "Menu" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("link", { name: "Overview" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(menu).toBeFocused();
});

test("theme choice applies immediately and persists across reloads", async ({ page }) => {
  await signInAs(page, "inspector");
  const themes = page.getByRole("group", { name: "Colour theme" }).filter({ visible: true });
  await themes.getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const canvas = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(await canvas()).toBe("rgb(14, 20, 17)");
  await page.reload();
  await expect(page.locator("#main")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("group", { name: "Colour theme" }).filter({ visible: true }).getByRole("button", { name: "Auto" }).click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", /.+/);
  expect(await canvas()).toBe("rgb(246, 244, 238)");
});

test("first-run strip: one action, dismissible, remembered per user", async ({ page }) => {
  await signInAs(page, "inspector");
  const intro = page.getByTestId("first-run").filter({ visible: true });
  await expect(intro).toBeVisible();
  await expect(intro.getByRole("listitem")).toHaveCount(3);
  await expect(intro.getByRole("link", { name: "Open map" })).toBeVisible();
  await intro.getByRole("button", { name: "Dismiss introduction" }).click();
  await expect(page.getByTestId("first-run")).toHaveCount(0);
  await page.reload();
  await expect(page.locator("#main")).toBeVisible();
  await expect(page.getByTestId(`home-inspector`)).toBeVisible();
  await expect(page.getByTestId("first-run")).toHaveCount(0);

  // Another user on the same browser still sees it; managers get the import action.
  await page.getByRole("button", { name: "Sign out" }).filter({ visible: true }).click();
  await page.waitForURL(/\/login/);
  await signIn(page, USERS.manager.email);
  const managerIntro = page.getByTestId("first-run").filter({ visible: true });
  await expect(managerIntro).toBeVisible();
  await expect(managerIntro.getByRole("link", { name: "Import parks" })).toBeVisible();
});

test("reduced motion: entrance animations and transitions are switched off", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await signInAs(page, "inspector");
  const intro = page.getByTestId("first-run").filter({ visible: true });
  await expect(intro).toBeVisible();
  const timing = await intro.evaluate((el) => {
    const s = getComputedStyle(el);
    const step = getComputedStyle(el.querySelector("li")!);
    return [s.animationDuration, step.animationDuration, step.animationDelay];
  });
  expect(timing).toEqual(["0s", "0s", "0s"]);
});

test("no horizontal overflow at 360 px on the main screens", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 360, height: 780 });
  await signInAs(page, "manager");
  for (const path of ["/", "/map", "/queue?status=all", "/tasks", "/processing", "/import", "/account"]) {
    await page.goto(path);
    await expect(page.locator("#main")).toBeVisible();
    await noOverflow(page);
  }
  await page.goto("/queue");
  await page.getByLabel("Status").filter({ visible: true }).selectOption("all");
  await page.getByTestId("signal-list").locator("a").first().click();
  await expect(page.getByTestId("signal-hero")).toBeVisible();
  await noOverflow(page);
  await page.goto("/map");
  await page.getByTestId("site-list").locator('a[data-has-observation="true"]').first().click();
  await expect(page.getByTestId("site-name")).toBeVisible();
  await noOverflow(page);

  await page.getByRole("button", { name: "Menu" }).filter({ visible: true }).click();
  await page.getByRole("dialog", { name: "Menu" }).getByRole("button", { name: "Sign out" }).click();
  await page.waitForURL(/\/login/);
  await signInAs(page, "admin");
  await page.goto("/users");
  await expect(page.getByTestId("user-table")).toBeVisible();
  await noOverflow(page);
});

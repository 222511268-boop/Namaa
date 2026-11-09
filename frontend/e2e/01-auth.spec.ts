import { expect, test } from "@playwright/test";
import { signIn, USERS } from "./helpers";

test.describe("US01 Sign in securely", () => {
  test("AC-01.4 protected page redirects to sign-in and returns after login (AC-01.1)", async ({ page }) => {
    await page.goto("/map");
    await expect(page).toHaveURL(/\/login\?next=%2Fmap/);
    await page.getByLabel("Email").filter({ visible: true }).fill(USERS.viewer.email);
    await page.getByLabel("Password").filter({ visible: true }).fill("e2e-password-123");
    await page.getByRole("button", { name: "Sign in" }).filter({ visible: true }).click();
    await expect(page).toHaveURL(/\/map$/);
    await expect(page.getByRole("heading", { name: "Green spaces" })).toBeVisible();
  });

  test("AC-01.2 wrong password and unknown email show the same message", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").filter({ visible: true }).fill(USERS.viewer.email);
    await page.getByLabel("Password").filter({ visible: true }).fill("wrong-password");
    await page.getByRole("button", { name: "Sign in" }).filter({ visible: true }).click();
    const msg = page.getByRole("alert").filter({ hasText: /\S/ });
    await expect(msg).toHaveText("Email or password is incorrect.");
    await page.getByLabel("Email").filter({ visible: true }).fill("nobody@example.com");
    await page.getByLabel("Password").filter({ visible: true }).fill("e2e-password-123");
    await page.getByRole("button", { name: "Sign in" }).filter({ visible: true }).click();
    await expect(msg).toHaveText("Email or password is incorrect.");
    await expect(page).toHaveURL(/\/login/);
  });

  test("AC-01.3 sign-out ends the session", async ({ page, context }) => {
    await signIn(page, USERS.viewer.email);
    await page.getByRole("button", { name: "Sign out" }).filter({ visible: true }).click();
    await expect(page).toHaveURL(/\/login/);
    // The session cookie no longer works against the API.
    const res = await page.request.get("/api/auth/me");
    expect(res.status()).toBe(401);
    // Signed-out visitors see the public introduction at "/", never the Overview.
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: /See which green spaces need attention/ })).toBeVisible();
    await page.goto("/map");
    await expect(page).toHaveURL(/\/login/);
    expect((await context.cookies()).find((c) => c.name === "namaa_session")).toBeUndefined();
  });

  test("landing page leads to sign-in and then to the Overview, not back to the landing page", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: /See which green spaces need attention/ })).toBeVisible();
    await page.getByRole("link", { name: "Sign in" }).first().click();
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel("Email").filter({ visible: true }).fill(USERS.viewer.email);
    await page.getByLabel("Password").filter({ visible: true }).fill("e2e-password-123");
    await page.getByRole("button", { name: "Sign in" }).filter({ visible: true }).click();
    await expect(page.locator("#main")).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: /See which green spaces need attention/ })).toHaveCount(0);
  });

  test("AC-01.1 session cookie is HttpOnly", async ({ page, context }) => {
    await signIn(page, USERS.viewer.email);
    const cookie = (await context.cookies()).find((c) => c.name === "namaa_session");
    expect(cookie?.httpOnly).toBe(true);
    expect(await page.evaluate(() => document.cookie)).not.toContain("namaa_session");
  });
});

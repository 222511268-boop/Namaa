import { expect, test } from "@playwright/test";
import { chooseChip, PASSWORD, signIn, signInAs, USERS } from "./helpers";

test.describe("US02 Manage user accounts and roles", () => {
  test("AC-02.1 administrator creates an account that can sign in", async ({ page, browser }) => {
    await signInAs(page, "admin");
    await page.getByRole("link", { name: "Users", exact: true }).filter({ visible: true }).click();
    await page.getByLabel("Full name").filter({ visible: true }).fill("Nora New");
    await page.getByLabel("Email", { exact: true }).filter({ visible: true }).fill("e2e.nora@example.com");
    await chooseChip(page, "Role", "Field inspector");
    await page.getByLabel("Initial password").filter({ visible: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).filter({ visible: true }).click();
    await expect(page.getByText("Account created for Nora New")).toBeVisible();
    await expect(page.locator('tr[data-email="e2e.nora@example.com"]')).toContainText("Active");

    const other = await browser.newPage();
    await signIn(other, "e2e.nora@example.com");
    await expect(other.getByText("Field inspector").first()).toBeVisible();
    await other.close();
  });

  test("AC-02.1 duplicate email and short password show field messages", async ({ page }) => {
    await signInAs(page, "admin");
    await page.goto("/users");
    await page.getByLabel("Full name").filter({ visible: true }).fill("Duplicate Person");
    await page.getByLabel("Email", { exact: true }).filter({ visible: true }).fill(USERS.viewer.email);
    await page.getByLabel("Initial password").filter({ visible: true }).fill("short");
    await page.getByRole("button", { name: "Create account" }).filter({ visible: true }).click();
    await expect(page.getByText("Use at least 10 characters.")).toBeVisible();
    await page.getByLabel("Initial password").filter({ visible: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).filter({ visible: true }).click();
    await expect(page.getByText("An account with this email already exists.")).toBeVisible();
  });

  test("AC-02.3 deactivated user cannot sign in until reactivated", async ({ page, browser }) => {
    await signInAs(page, "admin");
    await page.goto("/users");
    const row = page.locator('tr[data-email="e2e.nora@example.com"]');
    await row.getByRole("button", { name: "Deactivate" }).click();
    await expect(row).toContainText("Deactivated");

    const other = await browser.newPage();
    await other.goto("/login");
    await other.getByLabel("Email").filter({ visible: true }).fill("e2e.nora@example.com");
    await other.getByLabel("Password").filter({ visible: true }).fill(PASSWORD);
    await other.getByRole("button", { name: "Sign in" }).filter({ visible: true }).click();
    await expect(other.getByRole("alert").filter({ hasText: /\S/ })).toHaveText("Email or password is incorrect.");

    await row.getByRole("button", { name: "Reactivate" }).click();
    await expect(row).toContainText("Active");
    await signIn(other, "e2e.nora@example.com");
    await other.close();
  });

  test("AC-02.4 non-administrators cannot see or open user management", async ({ page }) => {
    await signInAs(page, "manager");
    await expect(page.getByRole("link", { name: "Users", exact: true }).filter({ visible: true })).toHaveCount(0);
    await page.goto("/users");
    await expect(page.getByText("You do not have access to this page")).toBeVisible();
    expect((await page.request.get("/api/users")).status()).toBe(403);
  });
});

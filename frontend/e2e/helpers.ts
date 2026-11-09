import { expect, type Page } from "@playwright/test";

export const PASSWORD = "e2e-password-123";
export const ADMIN = { email: "e2e.admin@example.com", password: "e2e-admin-password" };
export const USERS = {
  manager: { email: "e2e.manager@example.com", name: "Maha Manager" },
  inspector: { email: "e2e.inspector@example.com", name: "Ibrahim Inspector" },
  viewer: { email: "e2e.viewer@example.com", name: "Vera Viewer" },
} as const;

export async function signIn(page: Page, email: string, password = PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("Email").filter({ visible: true }).fill(email);
  await page.getByLabel("Password").filter({ visible: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).filter({ visible: true }).click();
  // The main region appears after sign-in on every screen size (the menu is collapsed on phones).
  await expect(page.locator("#main")).toBeVisible();
  await expect(page).not.toHaveURL(/\/login/);
}

export async function signInAs(page: Page, role: "admin" | keyof typeof USERS) {
  if (role === "admin") return signIn(page, ADMIN.email, ADMIN.password);
  return signIn(page, USERS[role].email);
}

/** Click points (fractions of the map box) to draw a closed polygon in the boundary editor. */
export async function drawPolygon(page: Page, points: [number, number][]) {
  const editor = page.getByTestId("boundary-editor");
  await expect(editor).toHaveAttribute("data-ready", "true");
  await page.waitForTimeout(500); // let tiles settle so clicks are not swallowed by map transitions
  const box = (await editor.boundingBox())!;
  const abs = points.map(([fx, fy]) => [box.x + fx * box.width, box.y + fy * box.height] as const);
  for (const [x, y] of abs) {
    await page.mouse.click(x, y);
    await page.waitForTimeout(150);
  }
  await page.mouse.click(abs[0][0], abs[0][1]); // close the ring on the first corner
  await expect(page.getByText(/1 shape drawn/)).toBeVisible();
}

/** Pick an option in a chip group (native radios styled as chips): click its visible label. */
export async function chooseChip(page: Page, group: string, option: string) {
  await page.getByRole("group", { name: group }).filter({ visible: true }).locator("label", { hasText: option }).first().click();
  await expect(page.getByRole("group", { name: group }).filter({ visible: true }).getByRole("radio", { name: option, exact: true })).toBeChecked();
}

import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

// AC-03.1: navigation matches the permission matrix. AC-03.3: role-specific home content.
const EXPECTED = {
  admin: ["Overview", "Attention queue", "Tasks", "Green spaces", "Reports", "Satellite data", "Users", "Activity"],
  manager: ["Overview", "Attention queue", "Tasks", "Green spaces", "Reports", "Import", "Satellite data"],
  inspector: ["Overview", "Tasks", "Green spaces"],
  viewer: ["Overview", "Green spaces", "Reports"],
} as const;

for (const [role, items] of Object.entries(EXPECTED)) {
  test(`AC-03.1/03.3 ${role} sees only permitted navigation and a role home`, async ({ page }) => {
    await signInAs(page, role as keyof typeof EXPECTED);
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link")).toHaveText([...items]);
    await expect(page.getByTestId(`home-${role}`)).toBeVisible();
    const processingCard = page.getByText("Latest satellite processing");
    if (role === "admin" || role === "manager") await expect(processingCard).toBeVisible();
    else await expect(processingCard).toHaveCount(0);
  });
}

test("AC-03.2 viewer is refused by the server when calling manager actions directly", async ({ page }) => {
  await signInAs(page, "viewer");
  const r = await page.request.post("/api/processing-runs", { data: { start_date: "2025-06-01", end_date: "2025-06-30" } });
  expect(r.status()).toBe(403);
  await page.goto("/sites/new");
  await expect(page.getByText("You do not have access to this page")).toBeVisible();
});

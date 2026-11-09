import { execSync } from "node:child_process";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { PASSWORD, signIn, signInAs, USERS } from "./helpers";

// Sprint 2: US09-US16. The two "E2E Decline Park" sites carry CONSTRUCTED observations (see backend/tests/e2e_seed.py).
const ROOT = path.resolve(__dirname, "..", "..");
const COMPOSE = `docker compose -p namaa-e2e --env-file "${ROOT}/.env" -f "${ROOT}/docker-compose.yml" -f "${ROOT}/docker-compose.e2e.yml"`;
let seeded: { sites: string[]; signals: Record<string, string> };

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  const out = execSync(`${COMPOSE} exec -T backend python -m tests.e2e_seed`, { encoding: "utf-8" });
  seeded = JSON.parse(out.trim().split("\n").pop()!);
  expect(Object.keys(seeded.signals)).toHaveLength(2);
});

async function openSignal(page: Page, name: string) {
  await page.goto("/queue");
  await page.getByTestId("signal-list").getByText(name).click();
  await expect(page.getByTestId("signal-site")).toHaveText(name);
}

test("AC-11.1/11.2 queue ranks signals and shows factor contributions", async ({ page }) => {
  await signInAs(page, "manager");
  await page.getByRole("link", { name: "Attention queue", exact: true }).filter({ visible: true }).click();
  const items = page.getByTestId("signal-list").locator("li");
  await expect(items).toHaveCount(2);
  await expect(items.first()).toContainText("E2E Decline Park A");
  await expect(items.first()).toContainText("Severity");
  await expect(items.first()).toContainText("Persistence");
  await expect(page.getByTestId("queue-count")).toHaveText("2 signals");
});

test("AC-11.3 empty state for a status with no signals", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto("/queue");
  await page.getByLabel("Status").filter({ visible: true }).selectOption("closed");
  await expect(page.getByText("No signals match these filters")).toBeVisible();
});

test("AC-12.1-12.3 evidence view: baseline band, highlighted observations, images or fallback", async ({ page }) => {
  await signInAs(page, "manager");
  await openSignal(page, "E2E Decline Park A (constructed data)");
  await expect(page.getByTestId("condition-chart")).toBeVisible();
  await expect(page.getByTestId("baseline-legend")).toContainText("Expected range for the season");
  await expect(page.getByTestId("signal-marker")).toHaveCount(3);
  await expect(page.getByTestId("trigger-table").locator("tbody tr")).toHaveCount(3);
  // Constructed observations have no real scene, so the image fallback is shown with the dates.
  await expect(page.getByTestId("evidence-images")).toContainText("Image unavailable");
  await expect(page.getByTestId("evidence-images")).toContainText("2026");
  await expect(page.getByText("Satellite-derived")).toBeVisible();
});

test("AC-13.2/13.3 dismissal requires a reason and is recorded", async ({ page }) => {
  await signInAs(page, "manager");
  await openSignal(page, "E2E Decline Park B (constructed data)");
  await page.getByRole("button", { name: "Dismiss…" }).filter({ visible: true }).click();
  await page.getByRole("button", { name: "Dismiss signal" }).filter({ visible: true }).click();
  await expect(page.getByText("Give a reason for dismissing the signal.")).toBeVisible();
  await page.getByLabel("Reason for dismissing (required)").filter({ visible: true }).fill("Replanting works under way (E2E)");
  await page.getByRole("button", { name: "Dismiss signal" }).filter({ visible: true }).click();
  await expect(page.getByTestId("signal-status")).toContainText("Dismissed");
  await expect(page.getByTestId("decision-history")).toContainText("Replanting works under way (E2E)");
  await expect(page.getByTestId("decision-history")).toContainText(USERS.manager.name);
});

test("AC-14.4 sending for inspection creates the task", async ({ page }) => {
  await signInAs(page, "manager");
  await openSignal(page, "E2E Decline Park A (constructed data)");
  await page.getByRole("button", { name: "Send for inspection" }).filter({ visible: true }).click();
  await page.getByLabel("Assign to").filter({ visible: true }).selectOption({ label: USERS.inspector.name });
  await page.getByLabel("Instructions (optional)").filter({ visible: true }).fill("Check irrigation and turf condition");
  await page.getByRole("button", { name: "Create inspection task" }).filter({ visible: true }).click();
  await expect(page.getByTestId("signal-status")).toContainText("Under inspection");
  await expect(page.getByTestId("decision-panel")).toContainText(`Waiting for ${USERS.inspector.name}`);
});

test("AC-14.2/15.1-15.5 inspector completes the task on a phone-sized screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInAs(page, "inspector");
  await page.goto("/tasks");
  const task = page.getByTestId("task-list").getByText("Inspect vegetation decline at E2E Decline Park A");
  await expect(task).toBeVisible();
  await task.click();
  await page.getByRole("button", { name: "Start task" }).filter({ visible: true }).click();
  await expect(page.getByTestId("task-status")).toContainText("In progress");
  // Completion without findings is refused with field messages.
  await page.getByRole("button", { name: "Complete task" }).filter({ visible: true }).click();
  await expect(page.getByText("Choose the observed condition.")).toBeVisible();
  await page.getByLabel("Stressed (dry, yellowing, thinning)").check();
  await page.getByLabel("Notes").filter({ visible: true }).fill("Turf yellowing on the north side; sprinkler line broken (E2E).");
  await page.getByTestId("photo-input").setInputFiles(path.join(__dirname, "fixtures", "test-photo.jpg"));
  await expect(page.getByTestId("photo-list").locator("li")).toHaveCount(1);
  // A non-image is rejected with a message.
  await page.getByTestId("photo-input").setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
  await expect(page.getByText(/not a readable image/)).toBeVisible();
  await page.getByRole("button", { name: "Complete task" }).filter({ visible: true }).click();
  await expect(page.getByTestId("task-status")).toContainText("Completed");
  await expect(page.getByTestId("findings-view")).toContainText("Turf yellowing");
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(390); // no horizontal scrolling on a phone
});

test("AC-14.2 other roles cannot see the inspector's task list", async ({ page }) => {
  await signInAs(page, "viewer");
  await expect(page.getByRole("link", { name: "Tasks", exact: true }).filter({ visible: true })).toHaveCount(0);
  expect((await page.request.get("/api/tasks")).status()).toBe(403);
});

test("AC-16.1/16.2 manager records the outcome; the site timeline shows the loop", async ({ page }) => {
  await signInAs(page, "manager");
  await openSignal(page, "E2E Decline Park A (constructed data)");
  await expect(page.getByTestId("findings-view")).toContainText("Turf yellowing");
  await page.getByRole("radio", { name: "Confirmed", exact: true }).check();
  await page.getByRole("button", { name: "Record outcome and close" }).filter({ visible: true }).click();
  await expect(page.getByTestId("signal-status")).toContainText("Closed · Confirmed");
  await page.getByRole("link", { name: "Open site profile" }).filter({ visible: true }).click();
  const timeline = page.getByTestId("site-timeline");
  await expect(timeline.locator("li")).toHaveCount(5);
  await expect(timeline.locator("li").first()).toContainText("Unusual decline detected");
  await expect(timeline.locator("li").last()).toContainText("Outcome recorded: confirmed");
  await expect(page.getByTestId("baseline-note")).toContainText("Seasonal baseline for 2026");
});

test("AC-25.1/25.2 administrator reset link lets the user set a new password", async ({ page, browser }) => {
  // The viewer is signed in elsewhere; that session must end after the reset.
  const viewerPage = await browser.newPage();
  await signInAs(viewerPage, "viewer");

  await signInAs(page, "admin");
  await page.goto("/users");
  await page.locator(`tr[data-email="${USERS.viewer.email}"]`).getByRole("button", { name: "Reset link" }).click();
  const link = await page.getByTestId("reset-link").inputValue();
  expect(link).toContain("/reset-password?token=");

  const anon = await browser.newPage();
  await anon.goto(new URL(link).pathname + new URL(link).search);
  await expect(anon.getByText(`Choose a new password for ${USERS.viewer.name}`)).toBeVisible();
  await anon.getByLabel("New password", { exact: true }).fill("viewer-reset-pass-1");
  await anon.getByLabel("Repeat new password").fill("viewer-reset-pass-1");
  await anon.getByRole("button", { name: "Set new password" }).click();
  await expect(anon.getByText("Your password has been changed.")).toBeVisible();

  expect((await viewerPage.request.get("/api/auth/me")).status()).toBe(401);
  // The link cannot be used twice.
  await anon.goto(new URL(link).pathname + new URL(link).search);
  await expect(anon.getByText(/invalid or has expired/)).toBeVisible();
  await signIn(anon, USERS.viewer.email, "viewer-reset-pass-1");
  // Leave the shared viewer account usable by the reporting and accessibility regressions.
  const restored = await anon.request.post("/api/auth/change-password", {
    data: { current_password: "viewer-reset-pass-1", new_password: PASSWORD },
  });
  expect(restored.status()).toBe(204);
  await anon.close();
  await viewerPage.close();
});

test("AC-25.4 a user changes their own password", async ({ page }) => {
  await signInAs(page, "inspector");
  await page.goto("/account");
  await page.getByLabel("Current password").fill("wrong-password-x");
  await page.getByLabel("New password", { exact: true }).fill("inspector-new-pass-1");
  await page.getByLabel("Repeat new password").fill("inspector-new-pass-1");
  await page.getByRole("button", { name: "Change password" }).filter({ visible: true }).click();
  await expect(page.getByText("The current password is incorrect.")).toBeVisible();
  await page.getByLabel("Current password").fill(PASSWORD);
  await page.getByRole("button", { name: "Change password" }).filter({ visible: true }).click();
  await expect(page.getByText("Password changed.")).toBeVisible();
  // Restore the shared test password for later runs of this suite.
  await page.getByLabel("Current password").fill("inspector-new-pass-1");
  await page.getByLabel("New password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Repeat new password").fill(PASSWORD);
  await page.getByRole("button", { name: "Change password" }).filter({ visible: true }).click();
  await expect(page.getByText("Password changed.")).toBeVisible();
});

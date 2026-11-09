import { execSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

// Isolated, CONSTRUCTED weather/heat/signal data; the test stack uses an HTTP OpenAI substitute.
const root = path.resolve(__dirname, "..", "..");
const compose = `docker compose -p namaa-e2e --env-file "${root}/.env" -f "${root}/docker-compose.yml" -f "${root}/docker-compose.e2e.yml"`;
let seeded: { site: string; signal: string };
test.beforeAll(() => {
  const out = execSync(`${compose} exec -T backend python -m tests.e2e_sprint3_seed`, { encoding: "utf8" });
  seeded = JSON.parse(out.trim().split("\n").pop()!);
});
test.describe.configure({ mode: "serial" });

test("US17–18 schedule persists and the comparison uses saved weather", async ({ page }) => {
  await signInAs(page, "manager");
  await page.goto(`/sites/${seeded.site}`);
  const water = page.getByTestId("water-card");
  await expect(water.getByTestId("water-total")).not.toHaveText("0 m³");
  await water.getByRole("button", { name: "Add schedule" }).click();
  const start = new Date(); start.setDate(start.getDate() - 35);
  await page.getByLabel("From", { exact: true }).fill(start.toISOString().slice(0, 10));
  await page.getByLabel("Litres per watering day").fill("10000");
  for (const day of ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]) {
    await page.getByTestId("schedule-form").locator("label").filter({ hasText: new RegExp(`^${day}$`) }).click();
    await expect(page.getByLabel(day, { exact: true })).toBeChecked();
  }
  await page.getByTestId("schedule-form").getByRole("button", { name: "Add schedule" }).click();
  await expect(water.getByTestId("water-comparison")).toContainText("30 scheduled days");
  await page.reload();
  await expect(page.getByTestId("water-comparison")).toBeVisible();
});

test("US19 map selects a stored dated heat layer with units and resolution", async ({ page }) => {
  await signInAs(page, "viewer"); await page.goto("/map");
  await expect(page.getByTestId("site-map")).toHaveAttribute("data-ready", "true");
  await expect(page.getByLabel("Surface heat layer").locator("option")).toHaveCount(2);
  await page.getByLabel("Surface heat layer").selectOption({ index: 1 });
  await expect(page.getByText("Land surface temperature (°C)", { exact: true })).toBeVisible();
  await expect(page.getByText(/100 m native resolution/)).toBeVisible();
});

test("US26 generated checklist is editable and saved in the actual inspection task", async ({ page }) => {
  await signInAs(page, "manager"); await page.goto(`/signals/${seeded.signal}`);
  await page.getByTestId("generate-brief").click();
  await expect(page.getByTestId("brief")).toBeVisible();
  await page.getByRole("button", { name: "Send for inspection" }).click();
  const instructions = page.getByLabel("Instructions");
  await expect(instructions).toHaveValue(/Check irrigation valves/);
  await instructions.fill((await instructions.inputValue()) + "\nCheck the northern valve.");
  const inspector = page.getByLabel("Assign to");
  await inspector.selectOption({ label: "Ibrahim Inspector" });
  await page.getByRole("button", { name: "Create inspection task" }).click();
  await expect(page.getByTestId("signal-status")).toContainText("Under inspection");
  const data = await (await page.request.get(`/api/signals/${seeded.signal}`)).json();
  expect(data.tasks[0].instructions).toContain("Check the northern valve.");
});

test("US21–22/27 overview filters regenerate the summary and printable reports include data", async ({ page }) => {
  await signInAs(page, "viewer"); await page.goto("/reports");
  await page.getByRole("button", { name: "Generate summary" }).click();
  await expect(page.getByTestId("ai-label")).toBeVisible();
  const start = "2026-01-01";
  const response = page.waitForResponse(r => r.url().endsWith("/api/overview/summary") && r.request().method() === "POST");
  await page.getByLabel("From", { exact: true }).fill(start);
  const generated = await (await response).json();
  expect(generated.filters.start).toBe(start);
  await page.emulateMedia({ media: "print" });
  await expect(page.getByTestId("ai-label")).toBeVisible();
  await page.emulateMedia({ media: "screen" });
  const exported = await page.request.get("/api/exports/sites.csv");
  expect(await exported.text()).toContain("E2E Sprint 3 Park");
  await page.goto(`/sites/${seeded.site}/report`);
  await expect(page.getByRole("heading", { name: "Water demand · Estimate" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Signals and decisions" })).toHaveCount(0);
});

test("US24 administrators can filter activity while viewers are refused", async ({ page }) => {
  await signInAs(page, "admin"); await page.goto("/activity");
  await page.getByLabel("Action", { exact: true }).selectOption("schedule.created");
  await expect(page.getByRole("table")).toContainText("Added irrigation schedule");
  await signInAs(page, "viewer");
  expect((await page.request.get("/api/activity")).status()).toBe(403);
});

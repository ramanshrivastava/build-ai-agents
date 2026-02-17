import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("clicking Generate shows loading overlay", async ({ page }) => {
  // Override briefing route with a delayed response
  await page.route("**/api/v1/patients/1/briefing", async (route) => {
    // Hold the request open for testing
    await new Promise((r) => setTimeout(r, 10_000));
    route.abort();
  });

  await page.goto("/patients/1");
  await page.getByRole("button", { name: "Generate Briefing" }).click();

  // Loading overlay should appear with a status message
  await expect(page.getByText("Reviewing patient record...")).toBeVisible();
});

test("loading shows step indicator", async ({ page }) => {
  await page.route("**/api/v1/patients/1/briefing", async (route) => {
    await new Promise((r) => setTimeout(r, 10_000));
    route.abort();
  });

  await page.goto("/patients/1");
  await page.getByRole("button", { name: "Generate Briefing" }).click();
  await expect(page.getByText("Step 1 of 11")).toBeVisible();
});

test("cancel button stops loading", async ({ page }) => {
  await page.route("**/api/v1/patients/1/briefing", async (route) => {
    await new Promise((r) => setTimeout(r, 10_000));
    route.abort();
  });

  await page.goto("/patients/1");
  await page.getByRole("button", { name: "Generate Briefing" }).click();
  await expect(page.getByText("Reviewing patient record...")).toBeVisible();

  // Click cancel
  await page.getByRole("button", { name: "Cancel" }).click();

  // Should return to generate button state
  await expect(page.getByRole("button", { name: /Generate Briefing|Retry/ })).toBeVisible();
});

test("status messages cycle over time", async ({ page }) => {
  await page.route("**/api/v1/patients/1/briefing", async (route) => {
    await new Promise((r) => setTimeout(r, 30_000));
    route.abort();
  });

  await page.goto("/patients/1");
  await page.getByRole("button", { name: "Generate Briefing" }).click();
  await expect(page.getByText("Reviewing patient record...")).toBeVisible();

  // Wait for message to cycle (3.5s per message)
  await page.waitForTimeout(4000);
  await expect(page.getByText("Step 1 of 11")).not.toBeVisible();
});

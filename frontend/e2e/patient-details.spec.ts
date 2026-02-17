import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("renders card grid (not details elements)", async ({ page }) => {
  await page.goto("/patients/1");
  // Should have section headings, not <details>/<summary>
  await expect(page.getByRole("heading", { name: "Conditions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Medications" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Labs" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Allergies" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Visits" })).toBeVisible();

  // No <details> elements
  const details = page.locator("details");
  await expect(details).toHaveCount(0);
});

test("displays patient data correctly", async ({ page }) => {
  await page.goto("/patients/1");
  await expect(page.getByText("Type 2 Diabetes")).toBeVisible();
  await expect(page.getByText("Metformin 1000mg")).toBeVisible();
  await expect(page.getByText("HbA1c: 7.2%")).toBeVisible();
  await expect(page.getByText("Penicillin")).toBeVisible();
  await expect(page.getByText("Diabetes follow-up")).toBeVisible();
});

test("empty state renders for no allergies", async ({ page }) => {
  await page.goto("/patients/2");
  await expect(page.getByText("No allergies on file")).toBeVisible();
});

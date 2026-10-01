import { expect, test } from "@playwright/test";
import { detailFixture, predictionId, queueFixture } from "../fixtures";

test("explores the complete immutable Attention workflow", async ({ page }) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") browserErrors.push(message.text()); });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.route("**/api/attention", (route) => route.fulfill({ json: queueFixture }));
  await page.route(`**/api/attention/${predictionId}`, (route) => route.fulfill({ json: detailFixture }));
  await page.goto("/attention");

  await expect(page.getByRole("heading", { name: "Attention" })).toBeVisible();
  await expect(page.getByText("Miro Spark One").first()).toBeVisible();
  await page.getByRole("button", { name: /Miro Spark One/i }).click();
  await expect(page.getByRole("button", { name: /Open planning context/ })).toBeEnabled();
  await page.getByRole("button", { name: /Open planning context/ }).click();
  await expect(page.getByRole("heading", { name: "Daily inventory paths" })).toBeVisible();
  await expect(page.getByText("Scheduled inbound").first()).toBeVisible();
  await page.getByRole("button", { name: "Low path" }).click();
  await expect(page.getByRole("button", { name: "Low path" })).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", { name: "Attention queue" }).click();
  await expect(page.getByText("Ranked by engine")).toBeVisible();
  await expect(page.getByText("1", { exact: true }).first()).toBeVisible();
  await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
  expect(browserErrors).toEqual([]);
});

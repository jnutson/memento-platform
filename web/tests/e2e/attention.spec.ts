import { expect, test } from "@playwright/test";
test("redirects the retired Attention pane to Memento Signal", async ({ page }) => {
  await page.goto("/attention");
  await expect(page).toHaveURL(/\/signal$/);
  await expect(page.getByText("Memento Signal").first()).toBeVisible();
});

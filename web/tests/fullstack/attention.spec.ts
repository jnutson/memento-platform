import { expect, test } from "@playwright/test";

test("drives the published pipeline through the complete Attention workflow", async ({ page }) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  const queueResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith("/api/attention"),
  );
  await page.goto("/attention");
  const queueResponse = await queueResponsePromise;
  expect(queueResponse.ok()).toBe(true);

  const queue = await queueResponse.json();
  expect(queue.run.source_release_set_id).toBe("437b6da3ad31abe0-20270130T120000Z");
  expect(queue.summary.eligible_candidate_count).toBe(1);
  expect(queue.summary.displayed_prediction_count).toBe(1);
  expect(queue.predictions).toHaveLength(1);

  await expect(page.getByRole("heading", { name: "Attention" })).toBeVisible();
  await expect(page.getByText("Demo Item").first()).toBeVisible();
  await expect(page.getByText("Demo Store").first()).toBeVisible();
  await expect(page.getByText("Eligible candidates").locator("..").getByText("1", { exact: true })).toBeVisible();

  const detailResponsePromise = page.waitForResponse((response) =>
    /\/api\/attention\/oos_[0-9a-f]{64}$/.test(response.url()),
  );
  await page.getByRole("button", { name: /Demo Item/i }).click();
  const detailResponse = await detailResponsePromise;
  expect(detailResponse.ok()).toBe(true);

  const detail = await detailResponse.json();
  expect(detail.evidence).toHaveLength(84);
  expect(detail.scheduled_inbound).toEqual([
    {
      expected_store_receipt_date: "2027-02-05",
      scheduled_inbound_units: "5.000000",
    },
  ]);

  const planningButton = page.getByRole("button", { name: "Open planning context" });
  await expect(planningButton).toBeEnabled();
  await planningButton.click();

  await expect(page.getByRole("heading", { name: "Daily inventory paths" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dated receipts in horizon" })).toBeVisible();
  await expect(page.getByText("Feb 5, 2027", { exact: true })).toBeVisible();
  await expect(page.getByText("5 units", { exact: true })).toBeVisible();

  const lowPath = page.getByRole("button", { name: "Low path" });
  await expect(lowPath).toHaveAttribute("aria-pressed", "true");
  await lowPath.click();
  await expect(lowPath).toHaveAttribute("aria-pressed", "false");

  await page.getByRole("button", { name: "Attention queue" }).click();
  await expect(page.getByText("Ranked by engine")).toBeVisible();
  await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
  expect(browserErrors).toEqual([]);
});

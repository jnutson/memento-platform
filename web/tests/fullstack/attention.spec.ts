import { expect, test } from "@playwright/test";

test("drives a published signal release through the Memento Signal workflow", async ({ page }) => {
  const browserErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  const queueResponsePromise = page.waitForResponse((response) => response.url().endsWith("/api/signals"));
  await page.goto("/signal");
  const queueResponse = await queueResponsePromise;
  expect(queueResponse.ok()).toBe(true);

  const queue = await queueResponse.json();
  expect(queue.run.source_release_set_id).toBe("437b6da3ad31abe0-20270130T120000Z");
  expect(queue.run.candidate_counts_by_type.availability).toBe(1);
  expect(queue.signals).toHaveLength(1);

  await expect(page.getByRole("heading", { name: "Memento Signal" })).toBeVisible();
  await expect(page.getByText("Demo Item").first()).toBeVisible();
  await expect(page.getByText("Demo Store").first()).toBeVisible();
  await expect(page.getByText("Eligible signals").locator("..").getByText("1", { exact: true })).toBeVisible();

  const detailResponsePromise = page.waitForResponse((response) =>
    /\/api\/signals\/sig_[0-9a-f]{64}$/.test(response.url()),
  );
  await page.getByRole("button", { name: /^#1 · Availability Risk/i }).click();
  const detailResponse = await detailResponsePromise;
  expect(detailResponse.ok()).toBe(true);

  const detail = await detailResponse.json();
  expect(detail.evidence).toHaveLength(84);
  expect(detail.signal.signal_type).toBe("availability");
  await expect(page.getByText(/84 published rows/)).toBeVisible();
  await expect(page.getByText("Confidence is an evidence-quality score, not a probability.")).toBeVisible();
  await expect(page.locator("[data-nextjs-dialog]")).toHaveCount(0);
  expect(browserErrors).toEqual([]);
});

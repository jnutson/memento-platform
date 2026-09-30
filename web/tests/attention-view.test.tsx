import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AttentionView from "@/components/attention/AttentionView";
import { detailFixture, queueFixture } from "./fixtures";

vi.mock("@/components/attention/AttentionScene", () => ({
  default: () => <div data-testid="attention-scene" />,
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Attention workflow", () => {
  it("keeps engine rank and opens evidence-backed planning context", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      return new Response(JSON.stringify(url.includes(queueFixture.predictions[0].prediction_id) ? detailFixture : queueFixture), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }));

    render(<AttentionView />);
    expect(await screen.findByText("Miro Spark One")).toBeInTheDocument();
    expect(screen.getByText("1", { selector: "span" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Miro Spark One/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Open planning context/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Open planning context/ }));
    expect(await screen.findByRole("heading", { name: "Daily inventory paths" })).toBeInTheDocument();
    expect(screen.getByText(/The base path depletes/)).toBeInTheDocument();
    expect(screen.queryByText(/Expedite|Transfer from DC|Dismiss/i)).not.toBeInTheDocument();
  });

  it("keeps planning context open while paging to another prediction", async () => {
    const secondId = `oos_${"b".repeat(64)}`;
    const secondPrediction = {
      ...queueFixture.predictions[0],
      prediction_id: secondId,
      rank_position: 2,
      product_id: "prd_test_2",
      identity: {
        ...queueFixture.predictions[0].identity,
        item_name: "Miro Spark Two",
        company_item_id: "MIRO-SPARK-002",
        source_product_id: "101",
      },
    };
    const queue = {
      ...queueFixture,
      run: { ...queueFixture.run, candidate_count: 2, display_count: 2 },
      summary: {
        ...queueFixture.summary,
        eligible_candidate_count: 2,
        displayed_prediction_count: 2,
      },
      predictions: [queueFixture.predictions[0], secondPrediction],
    };
    const secondDetail = {
      ...detailFixture,
      prediction: { ...detailFixture.prediction, ...secondPrediction },
      evidence: detailFixture.evidence.map((row) => ({ ...row, prediction_id: secondId })),
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.includes(secondId)
        ? secondDetail
        : url.includes(queueFixture.predictions[0].prediction_id)
          ? detailFixture
          : queue;
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }));

    render(<AttentionView />);
    fireEvent.click(await screen.findByRole("button", { name: /Miro Spark One/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Open planning context/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Open planning context/ }));
    expect(await screen.findByRole("heading", { name: "Daily inventory paths" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next prediction" }));
    expect(await screen.findByRole("heading", { name: "Miro Spark Two" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Daily inventory paths" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Attention queue/ })).toBeInTheDocument();
  });
});

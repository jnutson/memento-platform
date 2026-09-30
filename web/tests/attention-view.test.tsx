import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AttentionView from "@/components/attention/AttentionView";
import { detailFixture, queueFixture } from "./fixtures";

vi.mock("@/components/attention/AttentionScene", () => ({
  default: () => <div data-testid="attention-scene" />,
}));

afterEach(() => vi.restoreAllMocks());

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
});

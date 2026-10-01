import { describe, expect, it } from "vitest";
import { attentionDetailSchema, attentionQueueSchema } from "@/lib/attention/schema";
import { detailFixture, queueFixture } from "./fixtures";

describe("Attention API runtime contract", () => {
  it("accepts the complete queue and detail fixtures", () => {
    expect(attentionQueueSchema.parse(queueFixture)).toEqual(queueFixture);
    expect(attentionDetailSchema.parse(detailFixture)).toEqual(detailFixture);
  });

  it("rejects a queue that silently changes engine order", () => {
    const invalid = structuredClone(queueFixture);
    invalid.predictions[0].rank_position = 2;
    expect(attentionQueueSchema.safeParse(invalid).success).toBe(false);
  });

  it("rejects numeric decimals and out-of-range scores", () => {
    const numeric = structuredClone(queueFixture) as unknown as Record<string, unknown>;
    (numeric.summary as Record<string, unknown>).estimated_lost_units = 26;
    expect(attentionQueueSchema.safeParse(numeric).success).toBe(false);

    const invalidScore = structuredClone(queueFixture);
    invalidScore.predictions[0].prediction_confidence_score = "1.100000";
    expect(attentionQueueSchema.safeParse(invalidScore).success).toBe(false);
  });

  it("requires exactly 28 rows for every fixed path", () => {
    const invalid = structuredClone(detailFixture);
    invalid.evidence.pop();
    expect(attentionDetailSchema.safeParse(invalid).success).toBe(false);
  });
});

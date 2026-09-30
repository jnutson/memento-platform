import { ZodError, type ZodType } from "zod";
import { apiErrorSchema, attentionDetailSchema, attentionQueueSchema, type AttentionDetail, type AttentionQueue } from "./schema";

export class AttentionApiError extends Error {
  constructor(public readonly code: string, message: string, public readonly status?: number) {
    super(message);
    this.name = "AttentionApiError";
  }
}

async function fetchValidated<T>(url: string, schema: ZodType<T>, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { cache: "no-store", signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new AttentionApiError("network_error", "The local Attention API could not be reached.");
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new AttentionApiError("invalid_json", "The Attention API returned invalid JSON.", response.status);
  }

  if (!response.ok) {
    const parsed = apiErrorSchema.safeParse(payload);
    throw new AttentionApiError(parsed.success ? parsed.data.code : "unexpected_error", parsed.success ? parsed.data.message : "The Attention API request failed.", response.status);
  }

  try {
    return schema.parse(payload);
  } catch (error) {
    if (error instanceof ZodError) {
      throw new AttentionApiError("contract_integrity_error", "The Attention API response does not match the required contract.", response.status);
    }
    throw error;
  }
}

export function fetchAttentionQueue(signal?: AbortSignal): Promise<AttentionQueue> {
  return fetchValidated("/api/attention", attentionQueueSchema, signal);
}

export function fetchAttentionDetail(predictionId: string, signal?: AbortSignal): Promise<AttentionDetail> {
  return fetchValidated(`/api/attention/${encodeURIComponent(predictionId)}`, attentionDetailSchema, signal);
}

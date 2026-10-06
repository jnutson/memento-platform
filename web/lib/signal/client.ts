import { type ZodType } from "zod";
import { signalDetailSchema, signalQueueSchema, type SignalDetail, type SignalQueue, type SignalType } from "./schema";

async function validated<T>(url: string, schema: ZodType<T>, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { cache: "no-store", signal, headers: { Accept: "application/json" } });
  const payload: unknown = await response.json();
  if (!response.ok) throw new Error("Memento Signal API request failed.");
  return schema.parse(payload);
}

export function fetchSignalQueue(type?: SignalType, signal?: AbortSignal): Promise<SignalQueue> {
  return validated(`/api/signals${type ? `?signal_type=${type}` : ""}`, signalQueueSchema, signal);
}

export function fetchSignalDetail(id: string, signal?: AbortSignal): Promise<SignalDetail> {
  return validated(`/api/signals/${encodeURIComponent(id)}`, signalDetailSchema, signal);
}

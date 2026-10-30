/** Exponential backoff with jitter: base·2^attempt capped at max, scaled into [50 %, 100 %]. */
export function backoffDelay(attempt: number, baseMs = 1000, maxMs = 30_000, random: () => number = Math.random): number {
  const capped = Math.min(maxMs, baseMs * 2 ** Math.max(0, attempt));
  return Math.round(capped * (0.5 + random() * 0.5));
}

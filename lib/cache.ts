/**
 * A small time-limited cache for requests the browser has already paid for.
 * =========================================================================
 *
 * WHY THE BROWSER CACHES AT ALL. The API already asks the Vercel edge to hold
 * responses for sixty seconds, but the browser re-asks on every navigation,
 * and a full read of one company is ten to fifteen seconds of four engines on a
 * cold function. With path routes a reader moves between a stock page, the
 * compare view and back several times a minute; each move used to mean waiting
 * through the same skeletons for figures already on screen a moment ago.
 *
 * THE KEY IS THE REQUEST. A compare column and a stock page that ask for the
 * same company with the same tuning build the same query string, so they share
 * one entry — and the same string is what the edge caches on, so a miss here is
 * often still a hit there.
 *
 * WHAT IT DOES NOT DO. It never caches a failure: an upstream that throttled
 * once should be asked again, not remembered as broken for five minutes. It
 * never outlives the tab. And it is not where staleness is hidden — every
 * consumer stamps what it shows with when it was fetched.
 *
 * Pure (a clock is injected), so the frontend assertions pin its behaviour.
 */
export interface TtlCache<V> {
  /** A settled value younger than the TTL, or undefined. Never starts a fetch. */
  peek(key: string): { value: V; at: number } | undefined;
  set(key: string, value: V): void;
  /** One fetch per key at a time; a second caller joins the first. */
  getOrFetch(key: string, fetcher: () => Promise<V>): Promise<{ value: V; at: number }>;
  delete(key: string): void;
  size(): number;
}

export function createTtlCache<V>({
  ttlMs = 300_000, max = 8, now = () => Date.now(),
}: { ttlMs?: number; max?: number; now?: () => number } = {}): TtlCache<V> {
  const entries = new Map<string, { value: V; at: number }>();
  const inflight = new Map<string, Promise<{ value: V; at: number }>>();

  const fresh = (key: string) => {
    const hit = entries.get(key);
    if (!hit) return undefined;
    if (now() - hit.at > ttlMs) { entries.delete(key); return undefined; }
    return hit;
  };

  const store = (key: string, value: V) => {
    const entry = { value, at: now() };
    entries.delete(key);          // re-insert so Map order is recency order
    entries.set(key, entry);
    while (entries.size > max) entries.delete(entries.keys().next().value as string);
    return entry;
  };

  return {
    peek: fresh,
    set: (key, value) => { store(key, value); },
    delete: (key) => { entries.delete(key); },
    size: () => entries.size,
    getOrFetch(key, fetcher) {
      const hit = fresh(key);
      if (hit) return Promise.resolve(hit);
      const pending = inflight.get(key);
      if (pending) return pending;
      const promise = fetcher()
        .then((value) => store(key, value))
        .finally(() => inflight.delete(key));
      inflight.set(key, promise);
      return promise;
    },
  };
}

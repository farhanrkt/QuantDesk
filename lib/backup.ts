/**
 * What this browser holds for the reader, as one file they keep — and back.
 *
 * WHY. The watchlist, the thesis journal and the holdings live in this
 * browser's storage and nowhere else: the app has no accounts and no database,
 * on purpose. So a new phone, a cleared history or a private window loses all
 * of it, and the journal could be exported but never read back in. This is the
 * missing half: one dated file with everything QuantDesk keeps here, and a
 * restore that reads it.
 *
 * IT NEVER LEAVES THE BROWSER. The file is built and read on the page; nothing
 * here is sent anywhere, and the request layer cannot import this module
 * (scripts/check_frontend.mjs holds that for the stores it reads).
 *
 * RESTORING MERGES, IT NEVER REPLACES. A restore that overwrote the journal
 * would destroy whatever was written here since the file was saved, and the
 * journal's whole value is that an entry, once written, stays. So entries are
 * added by id, symbols are added to the lists, and the holdings and the
 * preferences are taken from the file only where this browser has none.
 *
 * EVERY PART IS READ BY ITS OWN STORE'S PARSER. The file is the reader's to
 * edit, and a hand-edited row must not plant something the stores would choke
 * on: symbols go through the watchlist's parser, entries through the journal's,
 * the holdings through a size and character check, preferences against the
 * values each one accepts. What does not pass is dropped, and the rest survives.
 */
import { JOURNAL_KEY, readJournal, type ThesisEntry } from "./journal";
import {
  RECENT_KEY, RECENT_MAX, WATCHLIST_KEY, WATCHLIST_MAX, parseList, serialiseList,
} from "./watchlist";

export const HOLDINGS_KEY = "quantdesk.holdings";
export const BACKUP_KIND = "quantdesk-backup";
export const BACKUP_VERSION = 1;
/** Far above any real journal; a file this large is not one of ours. */
export const BACKUP_MAX_BYTES = 2_000_000;
const HOLDINGS_MAX = 4_000;
const HOLDINGS_OK = /^[A-Za-z0-9.\-=^:,%\s]*$/;

/** The preferences worth carrying, and what each accepts. */
const PREFERENCES: Record<string, (value: string) => boolean> = {
  "quantdesk.language": (v) => v === "en" || v === "id",
  "quantdesk.detail": (v) => v === "simple" || v === "detailed",
  "quantdesk.horizon": (v) => ["1", "2", "3", "5", "10"].includes(v),
  "quantdesk.board.market": (v) => v === "US" || v === "ID",
  "quantdesk.board.rail": (v) => v === "open" || v === "closed",
};

export interface Backup {
  kind: typeof BACKUP_KIND;
  version: number;
  savedAt: string;
  watchlist: string[];
  recent: string[];
  journal: ThesisEntry[];
  holdings: string;
  preferences: Record<string, string>;
}

type Read = (key: string) => string | null;

function cleanHoldings(value: unknown): string {
  return typeof value === "string" && value.length <= HOLDINGS_MAX && HOLDINGS_OK.test(value)
    ? value.trim() : "";
}

function cleanPreferences(value: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!value || typeof value !== "object") return out;
  for (const [key, accepts] of Object.entries(PREFERENCES)) {
    const v = (value as Record<string, unknown>)[key];
    if (typeof v === "string" && accepts(v)) out[key] = v;
  }
  return out;
}

/** Everything QuantDesk keeps in this browser, read through each store's parser. */
export function makeBackup(read: Read, now: Date): Backup {
  const preferences: Record<string, string> = {};
  for (const key of Object.keys(PREFERENCES)) {
    const v = read(key);
    if (v != null) preferences[key] = v;
  }
  return {
    kind: BACKUP_KIND,
    version: BACKUP_VERSION,
    savedAt: now.toISOString(),
    watchlist: parseList(read(WATCHLIST_KEY), WATCHLIST_MAX),
    recent: parseList(read(RECENT_KEY), RECENT_MAX),
    journal: readJournal(read(JOURNAL_KEY)),
    holdings: cleanHoldings(read(HOLDINGS_KEY) ?? ""),
    preferences: cleanPreferences(preferences),
  };
}

/**
 * A backup file read back, or null when it is not one. The journal's own
 * export — a bare list of entries, written before this file existed — is
 * accepted as a backup holding only the journal.
 */
export function readBackup(text: string): Backup | null {
  if (!text || text.length > BACKUP_MAX_BYTES) return null;
  let parsed: unknown;
  try { parsed = JSON.parse(text); } catch { return null; }
  if (Array.isArray(parsed)) {
    const journal = readJournal(JSON.stringify(parsed));
    return journal.length ? {
      kind: BACKUP_KIND, version: BACKUP_VERSION, savedAt: "", watchlist: [], recent: [],
      journal, holdings: "", preferences: {},
    } : null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const file = parsed as Record<string, unknown>;
  if (file.kind !== BACKUP_KIND || typeof file.version !== "number" || file.version > BACKUP_VERSION) {
    return null;
  }
  return {
    kind: BACKUP_KIND,
    version: BACKUP_VERSION,
    savedAt: typeof file.savedAt === "string" ? file.savedAt.slice(0, 40) : "",
    watchlist: parseList(JSON.stringify(file.watchlist ?? []), WATCHLIST_MAX),
    recent: parseList(JSON.stringify(file.recent ?? []), RECENT_MAX),
    journal: readJournal(JSON.stringify(file.journal ?? [])),
    holdings: cleanHoldings(file.holdings ?? ""),
    preferences: cleanPreferences(file.preferences),
  };
}

export interface RestorePlan {
  /** Key to its new stored value; only keys that change. */
  writes: Record<string, string>;
  /** What the reader is told before anything is written. */
  added: { journal: number; watchlist: number; holdings: boolean; preferences: number };
}

/** What restoring `backup` here would write. Merges; never removes anything. */
export function planRestore(read: Read, backup: Backup): RestorePlan {
  const writes: Record<string, string> = {};

  const journal = readJournal(read(JOURNAL_KEY));
  const known = new Set(journal.map((e) => e.id));
  const newEntries = backup.journal.filter((e) => !known.has(e.id));
  if (newEntries.length) writes[JOURNAL_KEY] = JSON.stringify([...journal, ...newEntries]);

  const mergeList = (key: string, incoming: string[], max: number): number => {
    const current = parseList(read(key), max);
    const merged = [...current];
    for (const s of incoming) if (!merged.includes(s) && merged.length < max) merged.push(s);
    if (merged.length !== current.length) writes[key] = serialiseList(merged);
    return merged.length - current.length;
  };
  const watchlist = mergeList(WATCHLIST_KEY, backup.watchlist, WATCHLIST_MAX);
  mergeList(RECENT_KEY, backup.recent, RECENT_MAX);

  const holdings = !(read(HOLDINGS_KEY) ?? "").trim() && backup.holdings !== "";
  if (holdings) writes[HOLDINGS_KEY] = backup.holdings;

  let preferences = 0;
  for (const [key, value] of Object.entries(backup.preferences)) {
    if (read(key) == null) { writes[key] = value; preferences++; }
  }

  return { writes, added: { journal: newEntries.length, watchlist, holdings, preferences } };
}

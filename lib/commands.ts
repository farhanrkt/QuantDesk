/**
 * What the command palette offers, and in what order.
 * ===================================================
 *
 * The palette is a list of things to DO — open a company, go to a tab, switch
 * the reading mode — filtered by what is typed. Ordering is by how the text
 * matches the label, then by the group the command belongs to, so typing
 * "value" offers the Value tab before a company whose name happens to contain
 * the word.
 *
 * NOTHING HERE RANKS A COMPANY. Symbol results arrive from the server already
 * ordered by how their text matched; this file only decides where the "Open"
 * group sits relative to the navigation commands. A palette that sorted
 * companies by anything about the companies would be a screener with no
 * explanation attached.
 *
 * Pure: compiled into the frontend assertions and pinned there.
 */
export type CommandGroup = "Open" | "Recent" | "Watchlist" | "Go to" | "Settings" | "Actions";

export interface Command {
  id: string;
  label: string;
  group: CommandGroup;
  /** Shown on the right: a market, a shortcut, a hint. */
  detail?: string;
  /** Extra words that should find this command but are not in its label. */
  keywords?: string;
}

const GROUP_ORDER: CommandGroup[] = ["Open", "Recent", "Watchlist", "Go to", "Actions", "Settings"];

/** 0 best: label starts with it, a word starts with it, keywords match, anywhere. -1 none. */
export function matchScore(command: Command, query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  const label = command.label.toLowerCase();
  if (label.startsWith(q)) return 0;
  if ((" " + label).includes(" " + q)) return 1;
  if ((command.keywords ?? "").toLowerCase().split(/\s+/).some((k) => k.startsWith(q))) return 2;
  if (label.includes(q)) return 3;
  return -1;
}

/**
 * Filter and order. With no query every command keeps its group order and the
 * order it was supplied in; with one, commands that do not match are dropped
 * and the rest sort by match class, then group, then supplied order.
 */
export function rankCommands(commands: Command[], query: string, limit = 40): Command[] {
  return commands
    .map((command, index) => ({ command, index, score: matchScore(command, query) }))
    .filter((c) => c.score >= 0)
    .sort((a, b) => a.score - b.score
      || GROUP_ORDER.indexOf(a.command.group) - GROUP_ORDER.indexOf(b.command.group)
      || a.index - b.index)
    .slice(0, limit)
    .map((c) => c.command);
}

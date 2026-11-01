/**
 * Which keystrokes mean something, and when they must mean nothing.
 * =================================================================
 *
 * THE ONE RULE THAT MATTERS: never while typing. A reader entering "BBRI.JK"
 * in the ticker box must not have the `]` in a note or the `w` in a thesis
 * fire a shortcut. That is checked against the focused element, and against
 * IME composition — an Indonesian or Japanese input method produces keydown
 * events for keys that are part of a word being composed.
 *
 * NO MODIFIER CHORDS BEYOND THE PALETTE. ⌘K / Ctrl+K is the convention every
 * reader already knows. Everything else is a single unmodified key, and a key
 * pressed WITH a modifier is left alone, so browser and OS shortcuts (⌘[ for
 * back, Ctrl+W) are never shadowed.
 *
 * Pure: compiled into the frontend assertions and pinned there.
 */
export type ShortcutAction = "palette" | "prevTab" | "nextTab" | "watch" | "help" | null;

export interface KeyLike {
  key: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
  isComposing?: boolean;
}

export interface TargetLike {
  tagName?: string;
  isContentEditable?: boolean;
  type?: string;
}

const NON_TEXT_INPUTS = new Set(["checkbox", "radio", "button", "submit", "reset", "range", "color"]);

export function isTypingTarget(el: TargetLike | null | undefined): boolean {
  if (!el) return false;
  if (el.isContentEditable) return true;
  const tag = (el.tagName ?? "").toUpperCase();
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag === "INPUT") return !NON_TEXT_INPUTS.has((el.type ?? "text").toLowerCase());
  return false;
}

export function matchShortcut(e: KeyLike, target?: TargetLike | null): ShortcutAction {
  if (e.isComposing) return null;
  const mod = e.metaKey || e.ctrlKey;
  // The palette works from anywhere, a text field included: it is the one
  // chord, and opening a search box from a search box is never surprising.
  if (mod && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") return "palette";
  if (mod || e.altKey || isTypingTarget(target)) return null;
  switch (e.key) {
    case "/": return "palette";
    case "[": return "prevTab";
    case "]": return "nextTab";
    case "w": return "watch";
    case "?": return "help";
    default: return null;
  }
}

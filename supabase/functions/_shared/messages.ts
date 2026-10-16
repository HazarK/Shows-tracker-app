/** User-facing copy. HTML bold is how the PRD's emphasis is sent to Telegram. */

export const EMPTY_LIST =
  "You aren't following any shows yet. Use /add <show name> to add one.";
export const API_UNAVAILABLE =
  "I couldn't complete that request because the TV database is unavailable. Please try again later.";
export const USAGE_ADD = "Usage: /add <show name>";
export const USAGE_REMOVE = "Usage: /remove <show name>";
export const CANCELLED = "Cancelled.";
export const NOTHING_TO_CANCEL = "Nothing to cancel.";
export const CHOICE_EXPIRED = "That choice expired. Please try again.";
export const CHOICE_INVALID = "That choice is no longer valid. Please try again.";
export const PRIVATE_BOT = "This bot isn't available for this chat.";
export const SEVERAL_ADD = "Several shows match. Which one do you want to follow?";
export const SEVERAL_REMOVE =
  "Several shows match. Which one do you want to stop following?";
export const HELP_TEXT = `\
TV Season Tracker follows shows you care about and messages you when a new season is out.

/add <show name> — follow a show
/list — see shows you follow
/remove <show name> — stop following a show
/cancel — dismiss the current choice
/help — show this message`;

export function escapeHtml(text: string): string {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

export function formatShow(title: string, year: number | null): string {
  if (year === null) {
    return title;
  }
  return `${title} (${year})`;
}

export function foundPrompt(title: string, year: number | null): string {
  return `I found <b>${escapeHtml(formatShow(title, year))}</b>. Is this the show you want to follow?`;
}

export function removePrompt(title: string, year: number | null): string {
  return `Stop following <b>${escapeHtml(formatShow(title, year))}</b>?`;
}

export function notFoundMessage(query: string): string {
  return `I couldn't find a show matching <b>${escapeHtml(query)}</b>. Try another title.`;
}

export function newSeasonMessage(title: string, seasonNumber: number): string {
  return `🎬 New season available: ${title} — Season ${seasonNumber}`;
}

export function buttonLabel(title: string, year: number | null): string {
  const label = formatShow(title, year);
  if (label.length <= 60) {
    return label;
  }
  return `${label.slice(0, 57)}...`;
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "–";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "–";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "–";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "–";
  const seconds = Math.round((now - then) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return formatDate(iso);
}

/**
 * Cosine similarity (−1…1) shown as a 0–100 bar value. Negative scores clamp
 * to 0. This is a retrieval similarity, not a probability or an accuracy.
 */
export function similarityPercent(score: number): number {
  return Math.round(Math.min(1, Math.max(0, score)) * 100);
}

export function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function pluralize(count: number, word: string, plural = `${word}s`): string {
  return `${count} ${count === 1 ? word : plural}`;
}

export function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

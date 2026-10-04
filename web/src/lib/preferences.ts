/**
 * Browser-side preferences: theme and motion. No credentials are stored in the
 * browser: visitors are identified by an HttpOnly cookie, and the
 * administrator token lives only in memory (see lib/api.ts).
 */

export type ThemePreference = "dark" | "light" | "system";
export type MotionPreference = "system" | "reduced" | "full";

const THEME_KEY = "docmind.theme";
const MOTION_KEY = "docmind.motion";
const LEGACY_TOKEN_KEY = "docmind.token";

function read(storage: Storage | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function write(storage: Storage | undefined, key: string, value: string | null) {
  try {
    if (value === null) storage?.removeItem(key);
    else storage?.setItem(key, value);
  } catch {
    /* storage unavailable (private mode): preferences just won't persist */
  }
}

const local = typeof window !== "undefined" ? window.localStorage : undefined;
const session = typeof window !== "undefined" ? window.sessionStorage : undefined;

export function getTheme(): ThemePreference {
  const value = read(local, THEME_KEY);
  return value === "light" || value === "system" ? value : "dark";
}

export function getMotion(): MotionPreference {
  const value = read(local, MOTION_KEY);
  return value === "reduced" || value === "full" ? value : "system";
}

export function resolvedTheme(pref: ThemePreference): "dark" | "light" {
  if (pref !== "system") return pref;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function prefersReducedMotion(pref: MotionPreference = getMotion()): boolean {
  if (pref === "reduced") return true;
  if (pref === "full") return false;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export function applyTheme(pref: ThemePreference) {
  write(local, THEME_KEY, pref);
  document.documentElement.dataset.theme = resolvedTheme(pref);
}

export function applyMotion(pref: MotionPreference) {
  write(local, MOTION_KEY, pref);
  if (pref === "system") delete document.documentElement.dataset.motion;
  else document.documentElement.dataset.motion = pref;
}

/** Remove access tokens that older versions kept in browser storage. */
export function clearLegacyToken() {
  write(local, LEGACY_TOKEN_KEY, null);
  write(session, LEGACY_TOKEN_KEY, null);
}

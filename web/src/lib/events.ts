/**
 * Tiny app-wide signals that don't belong in React state:
 *  - "scene-pulse": something happened (upload, search, answer) that the 3D
 *    hero scene reacts to. The scene reads it inside its render loop, so it
 *    never triggers React re-renders.
 */

type Listener = () => void;
const listeners = new Map<string, Set<Listener>>();

export function emit(event: "scene-pulse") {
  if (event === "scene-pulse") lastPulse.at = performance.now();
  listeners.get(event)?.forEach((fn) => fn());
}

export function on(event: "scene-pulse", fn: Listener): () => void {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event)!.add(fn);
  return () => listeners.get(event)?.delete(fn);
}

/** Timestamp of the most recent scene pulse (read by the render loop). */
export const lastPulse = { at: -Infinity };

"use client";

import { useCallback, useSyncExternalStore } from "react";

// Per-browser UI preferences (sidebar collapsed, guide seen, ...).
// localStorage can be unavailable (private mode, blocked storage), so an
// in-memory copy keeps the UI working for the session either way.
const memory = new Map<string, string>();
const listeners = new Set<() => void>();

function read(key: string, fallback: string): string {
  if (memory.has(key)) return memory.get(key)!;
  try {
    return window.localStorage.getItem(`cc:${key}`) ?? fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: string) {
  memory.set(key, value);
  try {
    window.localStorage.setItem(`cc:${key}`, value);
  } catch {
    /* storage blocked: the in-memory value still applies */
  }
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** `serverValue` is used while server-rendering and hydrating. */
export function usePref(key: string, fallback: string, serverValue = fallback): [string, (v: string) => void] {
  const value = useSyncExternalStore(subscribe, () => read(key, fallback), () => serverValue);
  const set = useCallback((v: string) => write(key, v), [key]);
  return [value, set];
}

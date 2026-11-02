"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

function partOfDay(): string {
  const h = new Date().getHours();
  return h < 5 ? "Working late?" : h < 12 ? "Good morning." : h < 17 ? "Good afternoon." : "Good evening.";
}

/** Time-of-day greeting. Rendered on the client only, so the server and the
 *  browser never disagree about the hour. */
export function Greeting() {
  const greeting = useSyncExternalStore(subscribe, partOfDay, () => "Hello.");
  return (
    <>
      {greeting} <span className="text-fg-2">Let&apos;s build something.</span>
    </>
  );
}

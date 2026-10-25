"use client";

import clsx from "clsx";
import { useEffect, useRef, useState } from "react";
import type { Activity } from "@/lib/api";
import { AGENT_TONE } from "@/lib/crew";

/** Live feed of what each agent is doing. "Simple" is readable for anyone;
 *  "Raw log" is the same stream in terminal form for developers. */
export function ActivityPanel({ activity, live, done }: { activity: Activity[]; live: boolean; done?: string | null }) {
  const [raw, setRaw] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [activity.length, raw]);

  const t0 = activity[0]?.ts ?? 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <div className="flex items-center gap-2 text-[13px] font-semibold text-white">
          {live && <span className="status-dot running" />}
          What the crew is doing
        </div>
        <div className="flex rounded-lg border border-line bg-panel p-0.5 text-[11px]" role="group" aria-label="Log style">
          {(["Simple", "Raw log"] as const).map((label, i) => {
            const on = raw === (i === 1);
            return (
              <button
                key={label}
                onClick={() => setRaw(i === 1)}
                aria-pressed={on}
                className={clsx("rounded-md px-2 py-0.5 transition-colors duration-200", on ? "bg-panel-3 text-white" : "text-muted hover:text-fg")}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <div
        ref={box}
        className="scroll-thin min-h-0 flex-1 overflow-y-auto"
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
      >
        {!activity.length ? (
          <div className="p-4 text-[13px] text-muted">Waiting for the first agent to start…</div>
        ) : raw ? (
          <div className="terminal">
            {activity.map((a, i) => (
              <div key={i} className="feed-item">
                <span className="text-muted">+{Math.round((a.ts ?? t0) - t0)}s </span>
                <span style={{ color: AGENT_TONE[a.agent] ?? "var(--fg-2)" }}>[{a.agent}]</span> <span>{a.message}</span>
              </div>
            ))}
            {live ? <span className="caret">▊</span> : done && <div className="mt-1 text-ok">✓ finished: {done}</div>}
          </div>
        ) : (
          <ol className="space-y-1 p-2">
            {activity.map((a, i) => (
              <li
                key={i}
                className="feed-item rounded-lg px-2.5 py-2 transition-colors hover:bg-panel"
                style={{ ["--tone" as string]: AGENT_TONE[a.agent] ?? "var(--fg-2)" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="agent-chip">{a.agent === "Code Generation" ? "Coder" : a.agent}</span>
                  <span className="font-mono text-[10.5px] text-muted tabular-nums">+{Math.round((a.ts ?? t0) - t0)}s</span>
                </div>
                <p className="mt-1 text-[12.5px] leading-relaxed break-words text-fg-2">{a.message}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

"use client";

import clsx from "clsx";
import { Check } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { BUILD_STEPS, GLYPH, ITERATE_STEPS, STEP } from "@/lib/crew";
import { compact, duration } from "@/lib/format";
import type { RunView } from "@/lib/use-run-stream";

function useCountUp(target: number) {
  const [shown, setShown] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / 600);
      setShown(Math.round(a + (target - a) * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(tick);
      else from.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return shown;
}

export function Meter({ view, elapsed, running }: { view: RunView; elapsed: number; running: boolean }) {
  const latest = view.verifications[view.verifications.length - 1];
  const tokens = useCountUp((view.usage?.input_tokens ?? 0) + (view.usage?.output_tokens ?? 0));
  return (
    <div className="meter" aria-live="off">
      <span className={clsx("live-pill", running && "on")}>{running ? "Live" : view.done ? "Finished" : "Idle"}</span>
      <span>
        Time <b>{duration(elapsed)}</b>
      </span>
      <span>
        AI calls <b>{view.usage?.calls ?? 0}</b>
      </span>
      <span title="Text read and written by the AI">
        Tokens <b>{compact(tokens)}</b>
      </span>
      <span>
        Tests <b className={clsx(latest?.passed && "text-ok")}>{latest?.tests_total ? `${latest.tests_passed}/${latest.tests_total}` : "–"}</b>
      </span>
    </div>
  );
}

interface AgentStats {
  calls: number;
  seconds: number;
  model: string;
}

function useAgentStats(view: RunView, now: number): Record<string, AgentStats> {
  return useMemo(() => {
    const out: Record<string, AgentStats> = {};
    const get = (step: string) => (out[step] ??= { calls: 0, seconds: 0, model: "–" });
    for (const c of Object.values(view.calls)) {
      const s = get(c.step);
      if (c.endTs !== undefined) {
        if (c.ok) s.calls++;
        s.seconds += c.seconds ?? 0;
        if (c.model) s.model = c.model;
      } else {
        s.seconds += Math.max(0, now - c.startTs);
      }
    }
    const v = get("verifying");
    v.model = "none (real tools)";
    for (const t of Object.values(view.tools)) v.seconds += Math.max(0, (t.endTs ?? now) - t.startTs);
    return out;
  }, [view.calls, view.tools, now]);
}

export function Crew({ view, mode, running, now, minimal }: { view: RunView; mode: "build" | "iterate"; running: boolean; now: number; minimal: boolean }) {
  const steps = mode === "iterate" ? ITERATE_STEPS : BUILD_STEPS;
  const stats = useAgentStats(view, now);
  const latest = view.verifications[view.verifications.length - 1];
  const finished = !!view.done;
  const activeIdx = running ? steps.indexOf(view.phase) : -1;
  const waiting = Object.values(view.questions).some((q) => !q.answer);
  const doneCount = steps.filter((id) => view.phasesSeen.includes(id) && (finished || id !== view.phase)).length;
  const progress = finished ? 1 : activeIdx >= 0 ? activeIdx / (steps.length - 1) : Math.max(0, doneCount - 1) / (steps.length - 1);

  return (
    <div className={clsx("crew", minimal && "minimal")}>
      <div className="crew-track" aria-hidden>
        <div className="crew-fill" style={{ width: `${progress * 100}%` }} />
        <div className="baton" style={{ left: `${(Math.max(activeIdx, 0) / (steps.length - 1)) * 100}%`, opacity: activeIdx >= 0 ? 1 : 0 }} />
      </div>
      {steps.map((id, i) => {
        const s = STEP[id];
        const st = stats[id];
        const seen = view.phasesSeen.includes(id);
        const active = i === activeIdx;
        const done = seen && !active;
        const sad = id === "verifying" && !!latest && !latest.passed && (view.phase === "debugging" || (finished && view.status === "failed"));
        const isWaiting = active && waiting && id === "planning";
        const skipped = finished && !seen;
        const status = isWaiting ? "Waiting for you" : active ? "Working" : sad ? "Found a failure" : done ? "Done" : skipped ? "Not needed" : "Waiting";
        const edge = i === 0 ? "first" : i === steps.length - 1 ? "last" : "";
        return (
          <div key={id} className={clsx("agent", active && "active", isWaiting && "waiting", done && "done", sad && "sad", skipped && "skipped", edge)} style={{ ["--tone" as string]: s.tone }}>
            <button type="button" className="face" aria-label={`${s.agent}: ${status}`}>
              <span className="eyes" aria-hidden>
                <i />
                <i />
              </span>
              <span className="mouth" aria-hidden />
              <span className="glyph" aria-hidden>
                {GLYPH[id]}
              </span>
              <span className="face-badge" aria-hidden>
                <Check />
              </span>
            </button>
            <div className="agent-name">
              <b>{s.label}</b>
              <small>{s.agent}</small>
            </div>
            <div className="profile" role="tooltip">
              <h4>{s.agent}</h4>
              <p>{s.plain}</p>
              <dl>
                <dt>Model</dt>
                <dd title={st?.model}>{id === "verifying" ? "none (real tools)" : st?.model ?? "–"}</dd>
                <dt>AI calls</dt>
                <dd>{id === "verifying" ? "0" : st?.calls ?? 0}</dd>
                <dt>Time this run</dt>
                <dd>{duration(st?.seconds ?? 0)}</dd>
                <dt>Status</dt>
                <dd>{status}</dd>
              </dl>
            </div>
          </div>
        );
      })}
    </div>
  );
}

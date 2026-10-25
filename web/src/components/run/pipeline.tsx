"use client";

import clsx from "clsx";
import { AlertTriangle, ArrowUpRight, Ban, Check, CheckCircle2, Loader2, RotateCcw, XCircle } from "lucide-react";
import Link from "next/link";
import { BUILD_STEPS, ITERATE_STEPS, STEP } from "@/lib/crew";
import { duration } from "@/lib/format";
import type { RunView } from "@/lib/use-run-stream";

function stepsFor(mode: "build" | "iterate") {
  return mode === "iterate" ? ITERATE_STEPS : BUILD_STEPS;
}

export function Pipeline({ view, mode }: { view: RunView; mode: "build" | "iterate" }) {
  const finished = !!view.done;
  const latest = view.verifications[view.verifications.length - 1];

  return (
    <ol className="stepper" aria-label="Progress">
      {stepsFor(mode).map((id) => {
        const s = STEP[id];
        const Icon = s.icon;
        const seen = view.phasesSeen.includes(id);
        const active = view.phase === id && !finished;
        const done = seen && !active;
        const skipped = finished && !seen;
        const failedCheck = id === "verifying" && finished && latest && !latest.passed;
        let note = "";
        if (id === "verifying" && latest) note = latest.tests_total ? `${latest.tests_passed}/${latest.tests_total} tests` : latest.passed ? "passed" : "issues found";
        if (id === "debugging") {
          if (view.debugRounds.length) note = `${view.debugRounds.length} round${view.debugRounds.length > 1 ? "s" : ""}`;
          else if (finished && !seen) note = "not needed";
        }
        const reverted = id === "debugging" && view.debugRounds.some((r) => !r.kept);
        return (
          <li
            key={id}
            className={clsx("step", done && "done", active && "active", skipped && "skipped", failedCheck && "fail")}
            style={{ ["--tone" as string]: s.tone }}
            title={`${s.agent}: ${s.plain}`}
          >
            <span className="step-node">
              {active ? <Loader2 className="animate-spin" /> : <Icon />}
              {done && !failedCheck && (
                <span className="step-check">
                  <Check />
                </span>
              )}
            </span>
            <span className="step-label">{s.label}</span>
            {note && (
              <span className="step-note">
                {note}
                {reverted && <RotateCcw className="ml-1 inline size-3 text-warn" aria-label="a fix was undone" />}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** "What is happening right now", written for a first-time user. */
export function NowCard({ view, mode, elapsed }: { view: RunView; mode: "build" | "iterate"; elapsed: number }) {
  const steps = stepsFor(mode);
  const idx = steps.indexOf(view.phase);
  const s = STEP[view.phase];

  if (!s) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-line bg-panel px-4 py-3 animate-[fade-in_.3s_ease-out]">
        <Loader2 className="size-5 animate-spin text-accent" />
        <div>
          <div className="text-sm font-medium text-fg">Getting the crew ready…</div>
          <div className="text-xs text-muted">The first step usually starts within a few seconds.</div>
        </div>
      </div>
    );
  }

  const Icon = s.icon;
  return (
    <div
      key={view.phase}
      className="flex items-start gap-3 rounded-xl border bg-panel px-4 py-3 animate-[rise-in_.35s_cubic-bezier(.22,1,.36,1)_both]"
      style={{ borderColor: `${s.tone}55`, boxShadow: `0 10px 30px -22px ${s.tone}` }}
    >
      <span className="grid size-9 shrink-0 place-items-center rounded-xl" style={{ background: `${s.tone}22`, color: s.tone }}>
        <Icon className="size-[18px]" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-medium text-muted">
          Step {idx + 1} of {steps.length} · {s.agent}
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-sm font-semibold text-white">
          {s.doing}
          <span className="thinking" aria-hidden>
            <span />
            <span />
            <span />
          </span>
        </div>
        <p className="mt-1 text-[13px] leading-relaxed text-fg-2">{s.plain}</p>
        {view.phaseDetail && <p className="mt-1 text-xs text-muted">Now: {view.phaseDetail}</p>}
      </div>
      <div className="shrink-0 text-right text-xs text-muted tabular-nums">
        {duration(elapsed)}
        <div className="hidden text-[11px] sm:block">A step can take a few minutes</div>
      </div>
    </div>
  );
}

export function ResultBanner({ view, onShowChecks }: { view: RunView; onShowChecks: () => void }) {
  const done = view.done;
  if (!done) return null;
  const latest = view.verifications[view.verifications.length - 1];

  const variants = {
    succeeded: {
      icon: CheckCircle2,
      cls: "border-ok/40 bg-ok-soft text-ok",
      title: "Done! Every check passed.",
      body: latest?.tests_total
        ? `All ${latest.tests_total} tests ran and passed. Your project is saved and ready to use.`
        : "All checks passed. Your project is saved and ready to use.",
    },
    failed: {
      icon: AlertTriangle,
      cls: "border-warn/40 bg-warn-soft text-warn",
      title: "Finished, but some checks still fail",
      body: "The crew used all of its fix attempts. The best version is saved. Look at the test results, or open the project and ask for a change.",
    },
    error: {
      icon: XCircle,
      cls: "border-bad/40 bg-bad-soft text-bad",
      title: "The run stopped because of an error",
      body:
        done.error && /No LLM provider/i.test(done.error)
          ? "No AI key is set up. Add one to the .env file in the project folder, then restart the backend."
          : done.error ?? "Unknown error.",
    },
    cancelled: { icon: Ban, cls: "border-line bg-panel text-muted", title: "Run cancelled", body: "You stopped this run. Anything finished so far is still visible below." },
  } as const;

  const v = variants[done.status as keyof typeof variants] ?? variants.error;
  const Icon = v.icon;
  return (
    <div className={clsx("flex flex-wrap items-start gap-3 rounded-xl border px-4 py-3 animate-[rise-in_.4s_cubic-bezier(.22,1,.36,1)_both]", v.cls)}>
      <Icon className="mt-0.5 size-5 shrink-0" />
      <div className="min-w-0 flex-1 basis-[220px]">
        <div className="text-sm font-semibold">{v.title}</div>
        <p className="mt-0.5 text-[13px] leading-relaxed text-fg-2">{v.body}</p>
      </div>
      <div className="flex gap-2">
        {latest && (
          <button className="btn btn-ghost btn-sm" onClick={onShowChecks}>
            Test results
          </button>
        )}
        {done.project_id && (
          <Link href={`/projects/${done.project_id}`} className="btn btn-primary btn-sm">
            Open project <ArrowUpRight />
          </Link>
        )}
      </div>
    </div>
  );
}

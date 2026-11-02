"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Check, ChevronDown, Loader2, Send, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, imageUrl } from "@/lib/api";
import { STEP, agentStep, speaker } from "@/lib/crew";
import { parseLiveFiles } from "@/lib/live-files";
import { OUTCOME } from "@/lib/sessions";
import { sounds } from "@/lib/sound";
import { isFresh, type Note, type Question, type RunView, type TimelineItem } from "@/lib/use-run-stream";

// ---------------------------------------------------------------- plan checklist

type Todo = { label: string; state: "todo" | "doing" | "done" | "failed" };

function useChecklist(view: RunView, mode: "build" | "iterate", running: boolean): Todo[] {
  return useMemo(() => {
    if (!view.spec) return [];
    const finished = !!view.done;
    // Stopped early (error or Stop): the step the run was on did not finish.
    const stopped = finished && (view.done?.status === "error" || view.done?.status === "cancelled");
    const seen = (p: string) => view.phasesSeen.includes(p);
    const at = (p: string) => running && view.phase === p;
    const lastPhase = view.phasesSeen[view.phasesSeen.length - 1];
    const stateOf = (p: string, after: string[]): Todo["state"] =>
      at(p)
        ? "doing"
        : !seen(p)
          ? "todo"
          : after.some(seen)
            ? "done"
            : stopped
              ? p === lastPhase ? "failed" : "todo"
              : finished
                ? "done"
                : "todo";
    const latest = view.verifications[view.verifications.length - 1];
    const items: Todo[] = [];
    const qs = Object.values(view.questions);
    if (qs.length) items.push({ label: "Agree the details with you", state: qs.every((q) => q.answer) ? "done" : "doing" });
    if (mode === "iterate") items.push({ label: "Work out the smallest change", state: stateOf("triage", ["testing", "coding"]) });
    const tested = view.spec.acceptance_criteria.filter((a) => a.verification === "automated_test").length;
    if (tested) items.push({ label: `Write tests for ${tested} acceptance criteria`, state: stateOf("testing", ["coding"]) });
    const files = mode === "iterate" && view.triage ? view.triage.files.map((f) => f.path) : view.spec.files.map((f) => f.path);
    items.push({ label: `Write ${files.slice(0, 3).join(", ")}${files.length > 3 ? ` and ${files.length - 3} more` : ""}`, state: stateOf("coding", ["verifying"]) });
    items.push({
      label: "Run every test for real",
      state: at("verifying") ? "doing" : latest?.passed ? "done" : finished && latest ? "failed" : latest ? "done" : "todo",
    });
    const fixed = view.debugRounds.length;
    items.push({
      label: fixed ? `Fix what failed (${fixed} attempt${fixed > 1 ? "s" : ""})` : "Fix anything that fails",
      state: at("debugging")
        ? "doing"
        : view.status === "succeeded" || latest?.passed
          ? "done"
          : finished && (fixed > 0 || (!stopped && !!latest))
            ? "failed"
            : "todo",
    });
    items.push({ label: "Write the README", state: at("documenting") ? "doing" : finished && seen("documenting") ? "done" : "todo" });
    return items;
  }, [view.spec, view.triage, view.phasesSeen, view.phase, view.done, view.status, view.verifications, view.debugRounds, view.questions, mode, running]);
}

function Checklist({ items }: { items: Todo[] }) {
  const done = items.filter((i) => i.state === "done").length;
  return (
    <div className="todo">
      <div className="todo-h">
        <span>Plan</span>
        {items.length > 0 && <span className="tabular-nums">{done}/{items.length}</span>}
      </div>
      {items.length === 0 ? (
        <p className="mt-1 text-[12.5px] text-muted">The Planner writes a checklist here, and the crew ticks it off as they go.</p>
      ) : (
        <ul className="stagger">
          {items.map((t) => (
            <li key={t.label} className={`td-${t.state}`}>
              <span className="bx">{t.state === "failed" ? <X /> : <Check />}</span>
              <span className="min-w-0 truncate" title={t.label}>{t.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- feed items

function Avatar({ step }: { step: string }) {
  const sp = speaker(step);
  return (
    <span className="av" style={{ ["--tone" as string]: sp.tone }} aria-hidden>
      {sp.glyph}
    </span>
  );
}

function Words({ text, animate }: { text: string; animate: boolean }) {
  if (!animate) return <>{text}</>;
  return (
    <>
      {text.split(" ").map((w, i) => (
        <span key={i} className="w" style={{ animationDelay: `${Math.min(i, 60) * 35}ms` }}>
          {w}{" "}
        </span>
      ))}
    </>
  );
}

function Message({ item }: { item: Extract<TimelineItem, { kind: "message" }> }) {
  const step = agentStep(item.agent);
  const sp = speaker(step);
  if (step === "system")
    return <div className="feed-system">{item.text}</div>;
  return (
    <div className="row" style={{ ["--tone" as string]: sp.tone }}>
      <Avatar step={step} />
      <div className="body">
        <span className="who">{sp.name}</span>
        <span className="text">
          <Words text={item.text} animate={isFresh(item.ts)} />
        </span>
      </div>
    </div>
  );
}

function Think({ view, callId, now }: { view: RunView; callId: number; now: number }) {
  const c = view.calls[callId];
  if (!c) return null;
  const sp = speaker(c.step);
  let body: React.ReactNode;
  const writing = c.endTs === undefined && c.live ? parseLiveFiles(c.live.text) : [];
  const current = writing[writing.length - 1];
  if (current) {
    const lines = current.content.split("\n").length;
    body = (
      <span className="shimmer">
        Writing <code className="font-mono text-[12px]">{current.path}</code> · {lines} line{lines === 1 ? "" : "s"}
        {writing.length > 1 ? ` · ${writing.length - 1} file(s) done` : ""} · {Math.max(0, Math.round(now - c.startTs))}s
      </span>
    );
  } else if (c.endTs === undefined) {
    body = (
      <span className="shimmer">
        {c.role === "clarifier" ? "Checking if anything is unclear…" : "Thinking…"} {Math.max(0, Math.round(now - c.startTs))}s
      </span>
    );
  } else if (c.abandoned) {
    body = <span className="think-done">Stopped while thinking (the run was interrupted)</span>;
  } else if (!c.ok) {
    body = <span className="text-[12.5px] text-bad">No AI model could answer ({Math.round(c.seconds ?? 0)}s)</span>;
  } else if (c.points?.length) {
    body = (
      <details className="think">
        <summary>Thought for {Math.max(1, Math.round(c.seconds ?? 0))}s</summary>
        <ul>
          {c.points.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ul>
      </details>
    );
  } else {
    body = <span className="think-done">Thought for {Math.max(1, Math.round(c.seconds ?? 0))}s</span>;
  }
  return (
    <div className="row" style={{ ["--tone" as string]: sp.tone }} title={c.model ? `Model: ${c.model}` : undefined}>
      <Avatar step={c.step} />
      <div className="body">{body}</div>
    </div>
  );
}

function Handoff({ from, to }: { from: string; to: string }) {
  const a = STEP[from];
  const b = STEP[to];
  if (!a || !b) return null;
  return (
    <div className="handoff">
      <span className="pill" style={{ ["--tone" as string]: a.tone }}>{a.agent}</span>
      handed over to
      <span className="pill" style={{ ["--tone" as string]: b.tone }}>{b.agent}</span>
    </div>
  );
}

function Tool({ view, toolId }: { view: RunView; toolId: string }) {
  const t = view.tools[toolId];
  if (!t) return null;
  return (
    <details className={clsx("tool", t.status)} open={t.status === "bad" && !!t.output ? true : undefined}>
      <summary>
        <span className="st-ic">{t.status === "ok" ? <Check /> : t.status === "bad" ? <X /> : null}</span>
        <span className="shrink-0">{t.label}</span>
        <code className="hidden min-w-0 truncate sm:inline">{t.cmd}</code>
        <span className="res">{t.status === "running" ? "running…" : t.result}</span>
      </summary>
      {t.output && <pre className="scroll-thin">{t.output}</pre>}
    </details>
  );
}

function Edit({ item }: { item: Extract<TimelineItem, { kind: "edit" }> }) {
  return (
    <span className="edit-chip" title={`${item.isNew ? "Created" : "Changed"} by ${item.by}`}>
      {item.path} <span className="add">+{item.added}</span>
      {item.removed > 0 && <span className="del">−{item.removed}</span>}
    </span>
  );
}

function Ask({ q, runId, now, running }: { q: Question; runId: string; now: number; running: boolean }) {
  const [picked, setPicked] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sp = speaker(agentStep(q.agent));
  const left = Math.max(0, q.timeoutSec - (now - q.ts));
  const open = !q.answer && running && left > 0;
  const chosen = q.answer?.choice ?? picked;

  async function pick(i: number) {
    if (!open || picked !== null) return;
    setPicked(i);
    setError(null);
    try {
      await api.answer(runId, q.id, i);
    } catch (e) {
      setPicked(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="grid gap-2">
      <div className="row" style={{ ["--tone" as string]: sp.tone }}>
        <Avatar step={agentStep(q.agent)} />
        <div className="body">
          <span className="who">{sp.name} asks</span>
        </div>
      </div>
      <div className="ask">
        <p>{q.question}</p>
        {q.why && <p className="ask-why">{q.why}</p>}
        <div className="opts">
          {q.options.map((o, i) => (
            <button key={i} type="button" disabled={!open || picked !== null} className={clsx(chosen === i && "picked")} onClick={() => pick(i)}>
              <span>{o}</span>
              {i === q.recommended && <small>Recommended</small>}
            </button>
          ))}
        </div>
        {open && picked === null && (
          <>
            <div className="ask-timer" style={{ transform: `scaleX(${q.timeoutSec ? left / q.timeoutSec : 0})` }} />
            <p className="ask-note">No answer in {Math.ceil(left)}s? The crew goes with the recommended option.</p>
          </>
        )}
        {q.answer && (
          <p className="ask-note">{q.answer.auto ? "No answer, so the crew went with the recommended option." : "Thanks. The Planner added this to the plan."}</p>
        )}
        {error && <p className="ask-note text-bad">{error}</p>}
      </div>
    </div>
  );
}

function NoteBubble({ note, running }: { note: Note; running: boolean }) {
  return (
    <div className="grid justify-items-end gap-1">
      <div className="you">{note.text}</div>
      <span className="text-[11px] text-muted">
        {note.deliveredTo ? (
          <span className="text-ok">✓ Received by the {note.deliveredTo}</span>
        ) : running ? (
          "Waiting for the next agent to pick this up…"
        ) : (
          "The run ended before another agent started."
        )}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------- screenshots

function Shots({ runId, item }: { runId: string; item: Extract<TimelineItem, { kind: "images" }> }) {
  const step = agentStep(item.agent);
  return (
    <div className="row" style={{ ["--tone" as string]: speaker(step).tone }}>
      <Avatar step={step} />
      <div className="body">
        <span className="who">{speaker(step).name}</span>
        <span className="text text-muted">{item.caption}</span>
        <div className="mt-1.5 flex flex-wrap gap-2">
          {item.ids.map((id) => (
            <a key={id} href={imageUrl(runId, id)} target="_blank" rel="noreferrer" title="Open full size" className="block">
              {/* eslint-disable-next-line @next/next/no-img-element -- served by the API */}
              <img
                src={imageUrl(runId, id)}
                alt="Screenshot of the page the crew built"
                loading="lazy"
                className="h-28 w-auto max-w-[160px] rounded-md border border-line-strong object-cover object-top transition-transform hover:scale-[1.02]"
              />
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- the conversation so far

/** Earlier prompts in this session (same project) and how each went, then the prompt
 *  this run is working on, so the transcript reads like one continuing chat. */
function SessionHistory({ view, runId }: { view: RunView; runId: string }) {
  const run = view.run;
  const projectId = run?.project_id ?? view.done?.project_id ?? null;
  const { data } = useQuery({
    queryKey: ["runs", projectId],
    queryFn: () => api.runs(projectId!),
    enabled: !!projectId,
    staleTime: 10_000,
  });
  const [showAll, setShowAll] = useState(false);
  if (!run) return null;
  const earlier = (data?.runs ?? []).filter((r) => r.id !== runId && r.created_at < (run.created_at ?? Infinity)).sort((a, b) => a.created_at - b.created_at);
  const hidden = showAll ? 0 : Math.max(0, earlier.length - 3);
  return (
    <>
      {hidden > 0 && (
        <button type="button" className="history-more" onClick={() => setShowAll(true)}>
          <ChevronDown className="size-3.5" /> Show {hidden} earlier prompt{hidden > 1 ? "s" : ""}
        </button>
      )}
      {earlier.slice(hidden).map((r) => (
        <div key={r.id} className="history-turn">
          <div className="grid justify-items-end">
            <div className="you">{r.requirement}</div>
          </div>
          <div className="row" style={{ ["--tone" as string]: "#9d8dfa" }}>
            <Avatar step="orchestrator" />
            <div className="body">
              <span className="who">Orchestrator</span>
              <span className="text">
                <span className={clsx(r.status === "succeeded" ? "text-ok" : r.status === "failed" ? "text-warn" : "text-muted")}>
                  {OUTCOME[r.status] ?? r.status}
                </span>{" "}
                ·{" "}
                <Link href={`/runs/${r.id}`} className="text-muted underline-offset-2 hover:text-fg hover:underline">
                  see what the crew did
                </Link>
              </span>
            </div>
          </div>
        </div>
      ))}
      {earlier.length > 0 && <div className="history-now">Now</div>}
      <div className="grid justify-items-end">
        <div className="you">{run.requirement}</div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- steer box

function Steer({ runId, running, projectId }: { runId: string; running: boolean; projectId: string | null }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // While the crew works, messages steer this run. Once it has saved a project,
  // a message is a change request: it starts a new run on top of the project.
  const changing = !running && !!projectId;
  const open = running || changing;

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const v = text.trim();
    if (!v || busy || !open) return;
    if (changing && v.length < 3) return setError("Describe the change in a few words.");
    setBusy(true);
    setError(null);
    try {
      if (changing && projectId) {
        const run = await api.iterate(projectId, v);
        router.push(`/runs/${run.id}`);
      } else {
        await api.sendMessage(runId, v);
      }
      setText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="steer" onSubmit={send}>
      <label htmlFor="steer-in" className="sr-only">
        {changing ? "Ask for a change" : "Message the crew"}
      </label>
      <input
        id="steer-in"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={!open}
        maxLength={changing ? 8000 : 1000}
        autoComplete="off"
        placeholder={
          running
            ? "Add an instruction while they work…"
            : changing
              ? "Want a change? e.g. \"make the header blue\""
              : "This run saved no project, so there is nothing to change."
        }
      />
      <button className="btn btn-primary btn-sm h-9" type="submit" disabled={!open || busy || !text.trim()} aria-label={changing ? "Request change" : "Send"} title={changing ? "Start a new run that changes this project" : "Send"}>
        {busy ? <Loader2 className="animate-spin" /> : <Send />}
      </button>
      {error && <p className="steer-error">{error}</p>}
    </form>
  );
}

// ---------------------------------------------------------------- transcript

export function Transcript({ view, runId, mode, running, now }: { view: RunView; runId: string; mode: "build" | "iterate"; running: boolean; now: number }) {
  const [raw, setRaw] = useState(false);
  const feed = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const autoScrolledAt = useRef(0);
  const checklist = useChecklist(view, mode, running);
  const t0 = view.activity[0]?.ts ?? 0;

  useEffect(() => {
    const el = feed.current;
    if (!el || !stick.current) return;
    autoScrolledAt.current = Date.now();
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [view.timeline.length, view.tools, view.calls, raw]);

  // Small sounds for live events (only when the user switched sound on).
  const lastSeq = useRef(0);
  useEffect(() => {
    const fresh = view.timeline.filter((i) => i.seq > lastSeq.current && isFresh(i.ts));
    lastSeq.current = view.timeline[view.timeline.length - 1]?.seq ?? 0;
    for (const i of fresh) {
      if (i.kind === "message") sounds.message();
      if (i.kind === "question") sounds.question();
    }
  }, [view.timeline]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="tx-head">
        <div className="flex items-center gap-2">
          <strong>Crew transcript</strong>
          <span className={clsx("live-pill", running && "on")}>{running ? "Live" : view.done ? "Finished" : "Idle"}</span>
        </div>
        <div className="flex rounded-lg border border-line bg-panel p-0.5 text-[11px]" role="group" aria-label="Transcript style">
          {(["Story", "Raw log"] as const).map((label, i) => {
            const on = raw === (i === 1);
            return (
              <button
                key={label}
                type="button"
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

      <Checklist items={checklist} />

      <div
        ref={feed}
        className="feed scroll-thin"
        onScroll={(e) => {
          // Ignore the scroll events our own smooth auto-scroll produces; only a user
          // scrolling up should stop the feed from following new messages.
          if (Date.now() - autoScrolledAt.current < 900) return;
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        onWheel={() => (autoScrolledAt.current = 0)}
        onTouchMove={() => (autoScrolledAt.current = 0)}
      >
        {!raw && <SessionHistory view={view} runId={runId} />}
        {raw ? (
          <div className="terminal">
            {view.activity.map((a, i) => (
              <div key={i}>
                <span className="text-muted">+{Math.round((a.ts ?? t0) - t0)}s </span>
                <span style={{ color: speaker(agentStep(a.agent)).tone }}>[{a.agent}]</span> <span>{a.message}</span>
              </div>
            ))}
            {running && <span className="caret">▊</span>}
          </div>
        ) : view.timeline.length === 0 ? (
          <div className="row" style={{ ["--tone" as string]: "#9d8dfa" }}>
            <Avatar step="orchestrator" />
            <div className="body">
              <span className="who">Orchestrator</span>
              <span className="text">{running || !view.loaded ? "Getting the crew ready…" : "Nothing happened in this run."}</span>
            </div>
          </div>
        ) : (
          view.timeline.map((item) => (
            <div key={`${item.kind}-${item.seq}`} className="feed-item">
              {item.kind === "message" && <Message item={item} />}
              {item.kind === "think" && <Think view={view} callId={item.callId} now={now} />}
              {item.kind === "handoff" && <Handoff from={item.from} to={item.to} />}
              {item.kind === "tool" && <Tool view={view} toolId={item.toolId} />}
              {item.kind === "edit" && <Edit item={item} />}
              {item.kind === "question" && view.questions[item.questionId] && (
                <Ask q={view.questions[item.questionId]} runId={runId} now={now} running={running} />
              )}
              {item.kind === "note" && view.notes[item.noteId] && <NoteBubble note={view.notes[item.noteId]} running={running} />}
              {item.kind === "images" && <Shots runId={runId} item={item} />}
              {item.kind === "resumed" && (
                <div className="handoff">
                  <span className="pill" style={{ ["--tone" as string]: "#8bd49d" }}>Resumed</span>
                  {[item.hasSpec ? "plan kept" : "", item.tests ? `${item.tests} test file(s) kept` : "", item.files ? `${item.files} file(s) kept` : ""]
                    .filter(Boolean)
                    .join(" · ") || "starting over"}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <Steer runId={runId} running={running} projectId={view.done?.project_id ?? null} />
    </div>
  );
}

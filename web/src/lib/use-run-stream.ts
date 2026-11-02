"use client";

import { useEffect, useReducer } from "react";
import {
  api,
  eventsUrl,
  type Activity,
  type DebugRound,
  type DesignReview,
  type Reference,
  type RunState,
  type RunStatus,
  type Spec,
  type Triage,
  type Usage,
  type Verification,
} from "./api";
import { ROLE_STEP, STEP, agentStep } from "./crew";

export interface FileVersion {
  content: string;
  by: string;
  seq: number;
  ts: number;
}

export interface TrackedFile {
  path: string;
  kind: "source" | "test";
  versions: FileVersion[];
}

export interface Dispute {
  test_id: string;
  reason: string;
  upheld: boolean;
  explanation: string;
}

/** One AI call: shown as "Thinking…" until it ends, then "Thought for Ns". */
export interface LlmCall {
  id: number;
  role: string;
  step: string;
  startTs: number;
  endTs?: number;
  seconds?: number;
  ok?: boolean;
  model?: string | null;
  points?: string[];
  /** The run stopped (crash, restart, Stop) while this call was waiting. */
  abandoned?: boolean;
  /** The answer so far, streamed while the model writes it (live viewers only). */
  live?: { attempt: number; text: string };
}

/** One real check run by the Verifier (syntax, lint, tests...). */
export interface ToolCall {
  id: string;
  round: number;
  key: string;
  label: string;
  cmd: string;
  status: "running" | "ok" | "bad";
  result?: string;
  output?: string;
  startTs: number;
  endTs?: number;
}

export interface Question {
  id: string;
  agent: string;
  question: string;
  why: string;
  options: string[];
  recommended: number;
  timeoutSec: number;
  ts: number;
  answer?: { choice: number; label: string; auto: boolean };
}

export interface Note {
  id: string;
  text: string;
  ts: number;
  deliveredTo?: string;
}

export type TimelineItem =
  | { kind: "message"; seq: number; ts: number; agent: string; text: string }
  | { kind: "think"; seq: number; ts: number; callId: number }
  | { kind: "handoff"; seq: number; ts: number; from: string; to: string }
  | { kind: "tool"; seq: number; ts: number; toolId: string }
  | { kind: "edit"; seq: number; ts: number; path: string; by: string; added: number; removed: number; isNew: boolean }
  | { kind: "question"; seq: number; ts: number; questionId: string }
  | { kind: "note"; seq: number; ts: number; noteId: string }
  | { kind: "resumed"; seq: number; ts: number; files: number; tests: number; hasSpec: boolean }
  | { kind: "images"; seq: number; ts: number; ids: number[]; caption: string; agent: string };

export interface RunView {
  loaded: boolean;
  connection: "connecting" | "live" | "closed" | "error";
  error: string | null;
  run: RunState | null;
  status: RunStatus;
  phase: string;
  phaseDetail: string;
  phasesSeen: string[];
  spec: Spec | null;
  triage: Triage | null;
  files: Record<string, TrackedFile>;
  verifications: (Verification & { round: number; ts: number })[];
  debugRounds: DebugRound[];
  disputes: Dispute[];
  activity: Activity[];
  usage: Usage | null;
  readme: string;
  references: Reference[];
  designReviews: DesignReview[];
  done: { status: RunStatus; error: string | null; project_id: string | null; summary: string | null; ts: number } | null;
  calls: Record<number, LlmCall>;
  tools: Record<string, ToolCall>;
  questions: Record<string, Question>;
  notes: Record<string, Note>;
  timeline: TimelineItem[];
  lastFileTs: number;
  lastSeq: number;
}

const initial: RunView = {
  loaded: false,
  connection: "connecting",
  error: null,
  run: null,
  status: "queued",
  phase: "queued",
  phaseDetail: "",
  phasesSeen: [],
  spec: null,
  triage: null,
  files: {},
  verifications: [],
  debugRounds: [],
  disputes: [],
  activity: [],
  usage: null,
  readme: "",
  references: [],
  designReviews: [],
  done: null,
  calls: {},
  tools: {},
  questions: {},
  notes: {},
  timeline: [],
  lastFileTs: 0,
  lastSeq: 0,
};

type Action =
  | { type: "loaded"; run: RunState }
  | { type: "connection"; connection: RunView["connection"]; error?: string }
  | { type: "event"; name: string; data: EventData };

interface EventData {
  seq: number;
  ts: number;
  [key: string]: unknown;
}

/** Lines added / removed between two versions (multiset of lines; good enough for a chip). */
function lineDelta(before: string | undefined, after: string): { added: number; removed: number } {
  const a = (before ?? "").split("\n");
  const b = after.split("\n");
  const count = new Map<string, number>();
  for (const l of a) count.set(l, (count.get(l) ?? 0) + 1);
  let added = 0;
  for (const l of b) {
    const n = count.get(l) ?? 0;
    if (n > 0) count.set(l, n - 1);
    else added++;
  }
  let removed = 0;
  for (const n of count.values()) removed += n;
  if (before === undefined) removed = 0;
  return { added, removed };
}

function reduceEvent(s: RunView, name: string, d: EventData): RunView {
  const at = { seq: d.seq, ts: d.ts };
  switch (name) {
    case "status":
      return { ...s, status: (d.status as RunStatus) ?? s.status };
    case "phase": {
      const phase = (d.phase as string) ?? s.phase;
      const prev = s.phase;
      const timeline =
        phase !== prev && STEP[prev] && STEP[phase]
          ? [...s.timeline, { kind: "handoff" as const, ...at, from: prev, to: phase }]
          : s.timeline;
      return {
        ...s,
        phase,
        phaseDetail: (d.detail as string) ?? "",
        phasesSeen: s.phasesSeen.includes(phase) ? s.phasesSeen : [...s.phasesSeen, phase],
        timeline,
      };
    }
    case "activity": {
      const a = d as unknown as Activity;
      return { ...s, activity: [...s.activity, a], timeline: [...s.timeline, { kind: "message", ...at, agent: a.agent, text: a.message }] };
    }
    case "usage":
      return { ...s, usage: d as unknown as Usage };
    case "spec":
      return { ...s, spec: d as unknown as Spec };
    case "triage":
      return { ...s, triage: d as unknown as Triage };
    case "file": {
      const path = d.path as string | undefined;
      const content = d.content as string | undefined;
      if (!path || content === undefined) return s;
      const prev = s.files[path];
      const last = prev?.versions[prev.versions.length - 1];
      if (last && last.content === content) return s;
      const by = (d.by as string) ?? "";
      const version = { content, by, seq: d.seq, ts: d.ts };
      const delta = lineDelta(last?.content, content);
      return {
        ...s,
        lastFileTs: d.ts,
        files: { ...s.files, [path]: { path, kind: (d.kind as "source" | "test") ?? "source", versions: [...(prev?.versions ?? []), version] } },
        timeline: [...s.timeline, { kind: "edit", ...at, path, by, ...delta, isNew: !last }],
      };
    }
    case "verification":
      return { ...s, verifications: [...s.verifications, { ...(d as unknown as Verification & { round: number }), ts: d.ts }] };
    case "debug_round": {
      const r = d as unknown as DebugRound;
      const others = s.debugRounds.filter((x) => x.round !== r.round);
      return { ...s, debugRounds: [...others, r].sort((a, b) => a.round - b.round) };
    }
    case "dispute":
      return { ...s, disputes: [...s.disputes, d as unknown as Dispute] };
    case "readme":
      return { ...s, readme: (d.content as string) ?? "" };
    case "llm_start": {
      const id = d.id as number;
      const role = d.role as string;
      return {
        ...s,
        calls: { ...s.calls, [id]: { id, role, step: ROLE_STEP.get(role) ?? "planning", startTs: d.ts } },
        timeline: [...s.timeline, { kind: "think", ...at, callId: id }],
      };
    }
    case "llm_delta": {
      const id = d.id as number;
      const c = s.calls[id];
      if (!c) return s;
      const attempt = d.attempt as number;
      const prev = c.live && c.live.attempt === attempt ? c.live.text : "";
      // Pieces arrive in order; one that does not fit (missed while reconnecting) is skipped,
      // and the finished file arrives as a normal "file" event anyway.
      if (!d.reset && (d.offset as number) !== prev.length) return s;
      return { ...s, calls: { ...s.calls, [id]: { ...c, live: { attempt, text: d.reset ? "" : prev + (d.text as string) } } } };
    }
    case "llm_end": {
      const id = d.id as number;
      const c = s.calls[id];
      if (!c) return s;
      return { ...s, calls: { ...s.calls, [id]: { ...c, endTs: d.ts, seconds: d.seconds as number, ok: d.ok as boolean, model: d.model as string | null } } };
    }
    case "thought": {
      // Attach the notes to that agent's most recent finished AI call.
      const step = agentStep(d.agent as string);
      const target = Object.values(s.calls)
        .filter((c) => c.step === step && c.endTs !== undefined)
        .sort((a, b) => b.id - a.id)[0];
      if (!target) return s;
      return { ...s, calls: { ...s.calls, [target.id]: { ...target, points: d.points as string[] } } };
    }
    case "tool": {
      const id = d.id as string;
      const prev = s.tools[id];
      const status = d.status as ToolCall["status"];
      const tool: ToolCall = {
        id,
        round: d.round as number,
        key: d.key as string,
        label: d.label as string,
        cmd: d.cmd as string,
        status,
        result: d.result as string | undefined,
        output: d.output as string | undefined,
        startTs: prev?.startTs ?? d.ts,
        endTs: status === "running" ? undefined : d.ts,
      };
      return { ...s, tools: { ...s.tools, [id]: tool }, timeline: prev ? s.timeline : [...s.timeline, { kind: "tool", ...at, toolId: id }] };
    }
    case "question": {
      const q: Question = {
        id: d.id as string,
        agent: d.agent as string,
        question: d.question as string,
        why: (d.why as string) ?? "",
        options: d.options as string[],
        recommended: d.recommended as number,
        timeoutSec: d.timeout_sec as number,
        ts: d.ts,
      };
      return { ...s, questions: { ...s.questions, [q.id]: q }, timeline: [...s.timeline, { kind: "question", ...at, questionId: q.id }] };
    }
    case "answer": {
      const q = s.questions[d.id as string];
      if (!q) return s;
      return { ...s, questions: { ...s.questions, [q.id]: { ...q, answer: { choice: d.choice as number, label: d.label as string, auto: d.auto as boolean } } } };
    }
    case "steer": {
      const n: Note = { id: d.id as string, text: d.text as string, ts: d.ts };
      return { ...s, notes: { ...s.notes, [n.id]: n }, timeline: [...s.timeline, { kind: "note", ...at, noteId: n.id }] };
    }
    case "steer_delivered": {
      const notes = { ...s.notes };
      for (const id of (d.ids as string[]) ?? []) if (notes[id]) notes[id] = { ...notes[id], deliveredTo: d.agent as string };
      return { ...s, notes };
    }
    case "resumed": {
      // Calls and checks left open by the stopped attempt will never finish.
      const calls = { ...s.calls };
      for (const c of Object.values(calls)) if (c.endTs === undefined) calls[c.id] = { ...c, endTs: d.ts, ok: false, abandoned: true };
      const tools = { ...s.tools };
      for (const t of Object.values(tools)) if (t.status === "running") tools[t.id] = { ...t, status: "bad", result: "stopped", endTs: d.ts };
      // Only reopen the run if this resume is newer than the run's last finish.
      const reopened = !s.run?.finished_at || d.ts > s.run.finished_at;
      return {
        ...s,
        calls,
        tools,
        done: reopened ? null : s.done,
        status: reopened ? "queued" : s.status,
        timeline: [
          ...s.timeline,
          { kind: "resumed", ...at, files: ((d.files as string[]) ?? []).length, tests: ((d.tests as string[]) ?? []).length, hasSpec: !!d.has_spec },
        ],
      };
    }
    case "references":
      return { ...s, references: (d.references as Reference[]) ?? [] };
    case "design_review": {
      const review = d as unknown as DesignReview;
      return { ...s, designReviews: [...s.designReviews.filter((r) => r.round !== review.round), review] };
    }
    case "image":
      return {
        ...s,
        timeline: [...s.timeline, { kind: "images", ...at, ids: (d.ids as number[]) ?? [], caption: (d.caption as string) ?? "", agent: (d.agent as string) ?? "" }],
      };
    case "done":
      return {
        ...s,
        done: { ...(d as unknown as Omit<NonNullable<RunView["done"]>, "ts">), ts: d.ts },
        status: (d.status as RunStatus) ?? s.status,
        phase: "done",
      };
    default:
      return s;
  }
}

function reducer(s: RunView, a: Action): RunView {
  switch (a.type) {
    case "loaded": {
      // A run stopped by a server restart has no "done" event; take the ending from the saved run.
      const terminal = ["succeeded", "failed", "cancelled", "error"].includes(a.run.status);
      const done =
        s.done ??
        (terminal
          ? { status: a.run.status, error: a.run.error ?? null, project_id: a.run.project_id ?? null, summary: a.run.verification?.summary ?? null, ts: a.run.finished_at ?? 0 }
          : null);
      return { ...s, loaded: true, run: a.run, done: terminal ? done : s.done, status: s.done && !terminal ? s.status : a.run.status };
    }
    case "connection":
      return { ...s, connection: a.connection, error: a.error ?? s.error };
    case "event":
      if (a.data.seq <= s.lastSeq) return s; // replayed duplicate after a reconnect
      return { ...reduceEvent(s, a.name, a.data), lastSeq: a.data.seq };
  }
}

const EVENT_NAMES = [
  "status", "phase", "activity", "usage", "spec", "triage", "file", "verification", "debug_round", "dispute", "readme",
  "llm_start", "llm_delta", "llm_end", "thought", "tool", "question", "answer", "steer", "steer_delivered", "resumed", "references", "design_review", "image", "done",
];

/** True when an event happened in the last few seconds, i.e. the user is watching it live
 *  (as opposed to the stored history being replayed when a page opens). */
export function isFresh(ts: number | undefined, windowSec = 4): boolean {
  return ts !== undefined && Date.now() / 1000 - ts < windowSec;
}

/** Subscribes to a run's event stream. The server replays every stored event
 *  first, so opening a finished run reconstructs its full history. */
export function useRunStream(runId: string, connection = 0): RunView {
  const [state, dispatch] = useReducer(reducer, initial);

  useEffect(() => {
    let cancelled = false;
    api
      .run(runId)
      .then((run) => !cancelled && dispatch({ type: "loaded", run }))
      .catch((e) => !cancelled && dispatch({ type: "connection", connection: "error", error: e.message }));

    const source = new EventSource(eventsUrl(runId));
    source.onopen = () => dispatch({ type: "connection", connection: "live" });
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) dispatch({ type: "connection", connection: "closed" });
      else dispatch({ type: "connection", connection: "connecting" });
    };
    for (const name of EVENT_NAMES) {
      source.addEventListener(name, (e) => {
        const data = JSON.parse((e as MessageEvent).data);
        dispatch({ type: "event", name, data });
        if (name === "done") api.run(runId).then((run) => !cancelled && dispatch({ type: "loaded", run })).catch(() => {});
      });
    }
    // The server sends "end" when there is nothing more to stream; without it the
    // browser would keep reconnecting. (A resumed run streams on past its old "done".)
    source.addEventListener("end", () => {
      source.close();
      dispatch({ type: "connection", connection: "closed" });
    });
    return () => {
      cancelled = true;
      source.close();
    };
  }, [runId, connection]);

  return state;
}

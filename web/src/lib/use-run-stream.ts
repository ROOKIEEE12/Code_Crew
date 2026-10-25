"use client";

import { useEffect, useReducer } from "react";
import { api, eventsUrl, type Activity, type DebugRound, type RunState, type RunStatus, type Spec, type Triage, type Usage, type Verification } from "./api";

export interface FileVersion {
  content: string;
  by: string;
  seq: number;
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
  verifications: (Verification & { round: number })[];
  debugRounds: DebugRound[];
  disputes: Dispute[];
  activity: Activity[];
  usage: Usage | null;
  readme: string;
  done: { status: RunStatus; error: string | null; project_id: string | null; summary: string | null } | null;
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
  done: null,
  lastSeq: 0,
};

type Action =
  | { type: "loaded"; run: RunState }
  | { type: "connection"; connection: RunView["connection"]; error?: string }
  | { type: "event"; name: string; data: EventData };

interface EventData {
  seq: number;
  status?: RunStatus;
  phase?: string;
  detail?: string;
  path?: string;
  content?: string;
  kind?: "source" | "test";
  by?: string;
  [key: string]: unknown;
}

function reduceEvent(s: RunView, name: string, d: EventData): RunView {
  switch (name) {
    case "status":
      return { ...s, status: d.status ?? s.status };
    case "phase": {
      const phase = d.phase ?? s.phase;
      return {
        ...s,
        phase,
        phaseDetail: d.detail ?? "",
        phasesSeen: s.phasesSeen.includes(phase) ? s.phasesSeen : [...s.phasesSeen, phase],
      };
    }
    case "activity":
      return { ...s, activity: [...s.activity, d as unknown as Activity] };
    case "usage":
      return { ...s, usage: d as unknown as Usage };
    case "spec":
      return { ...s, spec: d as unknown as Spec };
    case "triage":
      return { ...s, triage: d as unknown as Triage };
    case "file": {
      if (!d.path || d.content === undefined) return s;
      const prev = s.files[d.path];
      const version = { content: d.content, by: d.by ?? "", seq: d.seq };
      if (prev && prev.versions[prev.versions.length - 1].content === d.content) return s;
      return {
        ...s,
        files: { ...s.files, [d.path]: { path: d.path, kind: d.kind ?? "source", versions: [...(prev?.versions ?? []), version] } },
      };
    }
    case "verification":
      return { ...s, verifications: [...s.verifications, d as unknown as Verification & { round: number }] };
    case "debug_round": {
      const r = d as unknown as DebugRound;
      const others = s.debugRounds.filter((x) => x.round !== r.round);
      return { ...s, debugRounds: [...others, r].sort((a, b) => a.round - b.round) };
    }
    case "dispute":
      return { ...s, disputes: [...s.disputes, d as unknown as Dispute] };
    case "readme":
      return { ...s, readme: d.content ?? "" };
    case "done":
      return { ...s, done: d as unknown as RunView["done"], status: d.status ?? s.status, phase: "done" };
    default:
      return s;
  }
}

function reducer(s: RunView, a: Action): RunView {
  switch (a.type) {
    case "loaded":
      return { ...s, loaded: true, run: a.run, status: s.done ? s.status : a.run.status };
    case "connection":
      return { ...s, connection: a.connection, error: a.error ?? s.error };
    case "event":
      if (a.data.seq <= s.lastSeq) return s; // replayed duplicate after a reconnect
      return { ...reduceEvent(s, a.name, a.data), lastSeq: a.data.seq };
  }
}

const EVENT_NAMES = ["status", "phase", "activity", "usage", "spec", "triage", "file", "verification", "debug_round", "dispute", "readme", "done"];

/** Subscribes to a run's event stream. The server replays every stored event
 *  first, so opening a finished run reconstructs its full history. */
export function useRunStream(runId: string): RunView {
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
        if (name === "done") {
          source.close();
          dispatch({ type: "connection", connection: "closed" });
          api.run(runId).then((run) => !cancelled && dispatch({ type: "loaded", run })).catch(() => {});
        }
      });
    }
    return () => {
      cancelled = true;
      source.close();
    };
  }, [runId]);

  return state;
}

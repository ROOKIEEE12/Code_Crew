import type { RunSummary } from "./api";

/** A conversation about one project: the build that created it and every change
 *  asked for since. Shown as one entry, like a chat, until the user starts a new build. */
export interface Session {
  key: string;
  /** what the user first asked for */
  title: string;
  /** oldest first */
  runs: RunSummary[];
  latest: RunSummary;
}

export function groupSessions(runs: RunSummary[]): Session[] {
  const byKey = new Map<string, RunSummary[]>();
  for (const r of runs) {
    const key = r.project_id ?? r.id; // a build that has not saved a project yet is its own session
    byKey.set(key, [...(byKey.get(key) ?? []), r]);
  }
  return [...byKey.entries()]
    .map(([key, list]) => {
      const ordered = [...list].sort((a, b) => a.created_at - b.created_at);
      return { key, title: ordered[0].requirement, runs: ordered, latest: ordered[ordered.length - 1] };
    })
    .sort((a, b) => b.latest.created_at - a.latest.created_at);
}

export const OUTCOME: Record<string, string> = {
  succeeded: "Done, every check passed",
  failed: "Finished, some checks still fail",
  cancelled: "Stopped",
  error: "Stopped by an error",
  running: "Working on it…",
  queued: "Waiting to start…",
};

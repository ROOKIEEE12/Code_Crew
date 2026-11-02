"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

/** Deletes a run after asking. A run still working is stopped first. */
export function useDeleteRun(onDeleted?: (runId: string) => void) {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: async (runIds: string | string[]) => {
      for (const id of Array.isArray(runIds) ? runIds : [runIds]) await api.deleteRun(id);
    },
    onSuccess: (_, runIds) => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["recent-runs"] });
      for (const id of Array.isArray(runIds) ? runIds : [runIds]) onDeleted?.(id);
    },
  });
  const ask = (run: { id: string; requirement: string; status: string }) => {
    const working = run.status === "running" || run.status === "queued";
    const what = run.requirement.length > 80 ? `${run.requirement.slice(0, 80)}…` : run.requirement;
    if (confirm(`${working ? "Stop and delete" : "Delete"} this run?\n\n"${what}"\n\nIts history is removed. Any project it saved is kept.`))
      mutation.mutate(run.id);
  };
  /** Deletes every run in a session (the project itself is kept). */
  const askSession = (title: string, runs: { id: string }[]) => {
    const what = title.length > 80 ? `${title.slice(0, 80)}…` : title;
    if (confirm(`Delete this session (${runs.length} prompt${runs.length > 1 ? "s" : ""})?\n\n"${what}"\n\nIts history is removed. The project it built is kept.`))
      mutation.mutate(runs.map((r) => r.id));
  };
  return { ...mutation, ask, askSession };
}

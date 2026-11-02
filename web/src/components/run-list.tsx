"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, History, MessagesSquare, Trash2 } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { groupSessions } from "@/lib/sessions";
import { useDeleteRun } from "@/lib/use-delete-run";
import { Empty, ErrorNote, StatusBadge } from "./ui";

/** Runs, newest first. With `sessions`, the build of a project and every change asked
 *  for since are one entry, like a chat (a project's own history lists each run). */
export function RunList({ limit, projectId, sessions = false }: { limit?: number; projectId?: string; sessions?: boolean }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["runs", projectId ?? null],
    queryFn: () => api.runs(projectId),
    refetchInterval: 5_000,
  });
  const remove = useDeleteRun();
  if (error) return <ErrorNote error={error} />;
  if (isLoading)
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skeleton h-14" />
        ))}
      </div>
    );
  const all = data?.runs ?? [];
  if (!all.length)
    return (
      <Empty title="No runs yet" icon={<History className="size-5" />}>
        Describe something to build and it will show up here.
      </Empty>
    );

  if (sessions) {
    return (
      <ul className="stagger space-y-2">
        <ErrorNote error={remove.error} />
        {groupSessions(all)
          .slice(0, limit)
          .map((s) => (
            <li key={s.key} className="group/run relative">
              <Link href={`/runs/${s.latest.id}`} className="card-hover group flex items-center gap-3 rounded-xl border border-line bg-panel px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13.5px] text-fg">{s.title}</p>
                  <p className="mt-0.5 truncate text-xs text-muted">
                    {s.runs.length > 1 ? (
                      <>
                        <MessagesSquare className="mr-1 inline size-3" />
                        {s.runs.length} prompts · latest: {s.latest.requirement}
                      </>
                    ) : (
                      "New build"
                    )}{" "}
                    · {timeAgo(s.latest.created_at)}
                  </p>
                </div>
                <StatusBadge status={s.latest.status} />
                <span className="w-7" aria-hidden />
                <ChevronRight className="size-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-fg" />
              </Link>
              <button
                type="button"
                className="icon-btn absolute top-1/2 right-9 -translate-y-1/2 opacity-0 transition-opacity group-hover/run:opacity-100 focus-visible:opacity-100"
                title="Delete this session"
                aria-label={`Delete session: ${s.title}`}
                disabled={remove.isPending}
                onClick={() => (s.runs.length > 1 ? remove.askSession(s.title, s.runs) : remove.ask(s.latest))}
              >
                <Trash2 />
              </button>
            </li>
          ))}
      </ul>
    );
  }

  const runs = all.slice(0, limit);
  return (
    <ul className="stagger space-y-2">
      <ErrorNote error={remove.error} />
      {runs.map((r) => (
        <li key={r.id} className="group/run relative">
          <Link href={`/runs/${r.id}`} className="card-hover group flex items-center gap-3 rounded-xl border border-line bg-panel px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13.5px] text-fg">{r.requirement}</p>
              <p className="mt-0.5 text-xs text-muted">
                {r.mode === "iterate" ? `Change to ${r.project_id}` : "New build"} · {timeAgo(r.created_at)}
              </p>
            </div>
            <StatusBadge status={r.status} />
            <span className="w-7" aria-hidden />
            <ChevronRight className="size-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-fg" />
          </Link>
          <button
            type="button"
            className="icon-btn absolute top-1/2 right-9 -translate-y-1/2 opacity-0 transition-opacity group-hover/run:opacity-100 focus-visible:opacity-100"
            title="Delete this run"
            aria-label={`Delete run: ${r.requirement}`}
            disabled={remove.isPending && remove.variables === r.id}
            onClick={() => remove.ask(r)}
          >
            <Trash2 />
          </button>
        </li>
      ))}
    </ul>
  );
}

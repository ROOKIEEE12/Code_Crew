"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, History } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Empty, ErrorNote, StatusBadge } from "./ui";

export function RunList({ limit, projectId }: { limit?: number; projectId?: string }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["runs", projectId ?? null],
    queryFn: () => api.runs(projectId),
    refetchInterval: 5_000,
  });
  if (error) return <ErrorNote error={error} />;
  if (isLoading)
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skeleton h-14" />
        ))}
      </div>
    );
  const runs = (data?.runs ?? []).slice(0, limit);
  if (!runs.length)
    return (
      <Empty title="No runs yet" icon={<History className="size-5" />}>
        Describe something to build and it will show up here.
      </Empty>
    );
  return (
    <ul className="stagger space-y-2">
      {runs.map((r) => (
        <li key={r.id}>
          <Link href={`/runs/${r.id}`} className="card-hover group flex items-center gap-3 rounded-xl border border-line bg-panel px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13.5px] text-fg">{r.requirement}</p>
              <p className="mt-0.5 text-xs text-muted">
                {r.mode === "iterate" ? `Change to ${r.project_id}` : "New build"} · {timeAgo(r.created_at)}
              </p>
            </div>
            <StatusBadge status={r.status} />
            <ChevronRight className="size-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-fg" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

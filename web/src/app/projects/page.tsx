"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Archive, Boxes, CheckCircle2, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Empty, ErrorNote, Page, PageHeader } from "@/components/ui";

export default function ProjectsPage() {
  const { data, error, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: api.projects,
  });
  const projects = data?.projects ?? [];
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["recent-projects"] });
    },
  });

  return (
    <Page>
      <PageHeader
        title="Projects"
        description="Everything the crew has built. Open a project to read the code, try a live preview, download it, or ask for changes."
        actions={
          <Link href="/" className="btn btn-primary">
            <Plus /> New build
          </Link>
        }
      />
          <ErrorNote error={error ?? remove.error} />
          {isLoading && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-36" />
              ))}
            </div>
          )}
          {!isLoading && !error && !projects.length && (
            <Empty title="No projects yet" icon={<Boxes className="size-5" />}>When a build finishes, its project is saved here.</Empty>
          )}

          <ul className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <li key={p.id} className="group relative">
                <Link
                  href={`/projects/${p.id}`}
                  className="card-hover block h-full rounded-xl border border-line bg-panel p-4"
                >
                  <div className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate font-medium text-white">
                      {p.name}
                    </span>
                    {p.legacy ? (
                      <Archive className="size-4 text-[#757b8b]" aria-label="Legacy project" />
                    ) : p.passed ? (
                      <CheckCircle2 className="size-4 text-[#8bd49d]" aria-label="Verified" />
                    ) : (
                      <AlertTriangle className="size-4 text-[#e8ae79]" aria-label="Some checks failed" />
                    )}
                  </div>
                  <p className="mt-2 line-clamp-2 min-h-10 text-xs leading-relaxed text-[#8a91a3]">
                    {p.summary ||
                      (p.legacy
                        ? "Made by an older CodeCrew version. You can read it, but not request changes."
                        : "")}
                  </p>
                  <div className="mt-4 flex items-center gap-3 border-t border-[#232633] pt-2 text-[11px] text-[#717787]">
                    <span>{p.file_count} files</span>
                    {p.tests_total ? (
                      <span>
                        {p.tests_passed}/{p.tests_total} tests passed
                      </span>
                    ) : null}
                    <span className="ml-auto">{timeAgo(p.updated_at)}</span>
                  </div>
                </Link>
                <button
                  type="button"
                  className="icon-btn absolute top-2.5 right-10 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 hover:text-bad"
                  title={`Delete ${p.name}`}
                  aria-label={`Delete ${p.name}`}
                  disabled={remove.isPending && remove.variables === p.id}
                  onClick={() => confirm(`Delete project "${p.name}" from disk? This cannot be undone.`) && remove.mutate(p.id)}
                >
                  <Trash2 />
                </button>
              </li>
            ))}
          </ul>
    </Page>
  );
}

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowLeft,
  BookOpen,
  ClipboardList,
  Download,
  FileCode2,
  Globe,
  History,
  Loader2,
  Pencil,
  Play,
  RotateCcw,
  Save,
  Send,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, downloadUrl } from "@/lib/api";
import { CodeView } from "./code-view";
import { Markdown } from "./markdown";
import { RunList } from "./run-list";
import { SpecPanel } from "./spec-panel";
import { TryIt, htmlEntry, runnableFiles } from "./try-it";
import { Button, ErrorNote, StatusBadge, Tabs } from "./ui";

type Tab = "code" | "try" | "readme" | "spec" | "history";

export function ProjectView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();

  const { data: p, error, isLoading } = useQuery({
    queryKey: ["project", id],
    queryFn: () => api.project(id),
  });

  const [activeTab, setActiveTab] = useState<Tab>("code");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const params = useSearchParams();
  const [change, setChange] = useState(() => params.get("change") ?? "");
  // Unsaved hand edits, by file path.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [newName, setNewName] = useState<string | null>(null);
  const dirty = Object.keys(drafts);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["project", id] });
    qc.invalidateQueries({ queryKey: ["projects"] });
    qc.invalidateQueries({ queryKey: ["recent-projects"] });
  };

  const iterate = useMutation({
    mutationFn: () => api.iterate(id, change.trim()),
    onSuccess: (run) => router.push(`/runs/${run.id}`),
  });

  const save = useMutation({
    mutationFn: async () => {
      for (const [path, content] of Object.entries(drafts)) await api.saveFile(id, path, content);
    },
    onSuccess: () => {
      setDrafts({});
      refresh();
    },
  });

  const rename = useMutation({
    mutationFn: (name: string) => api.renameProject(id, name),
    onSuccess: () => {
      setNewName(null);
      refresh();
    },
  });

  // Warn before closing the tab with unsaved edits.
  useEffect(() => {
    if (!dirty.length) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty.length]);

  const remove = useMutation({
    mutationFn: () => api.deleteProject(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["recent-projects"] });
      router.push("/projects");
    },
  });

  if (isLoading)
    return (
      <div className="space-y-3 p-6">
        <div className="skeleton h-20" />
        <div className="skeleton h-[60vh]" />
      </div>
    );

  if (error || !p)
    return (
      <div className="p-8">
        <ErrorNote error={error ?? "Project not found"} />
      </div>
    );

  const allFiles = { ...p.files, ...p.tests };
  const paths = Object.keys(allFiles).sort();
  const activePath =
    selectedFile && allFiles[selectedFile] !== undefined
      ? selectedFile
      : paths.find((x) => p.files[x] !== undefined) ?? paths[0];

  const canTry = !!htmlEntry(p.files) || runnableFiles(p.files).length > 0;
  const tryLabel = htmlEntry(p.files) ? "Live preview" : "Run";
  const v = p.verification;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* 1. PROJECT HEADER */}
      <div className="border-b border-line bg-[#121317] px-4 pt-3 pb-4 sm:px-6">
        <Link href="/projects" className="mb-1.5 inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-xs text-muted transition-colors hover:bg-panel-2 hover:text-fg">
          <ArrowLeft className="size-3.5" /> Projects
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              {newName === null ? (
                <>
                  <h1 className="truncate text-base font-semibold text-white">{p.name}</h1>
                  <button className="icon-btn" onClick={() => setNewName(p.name)} title="Rename project" aria-label="Rename project">
                    <Pencil />
                  </button>
                </>
              ) : (
                <form
                  className="flex items-center gap-1.5"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (newName.trim()) rename.mutate(newName.trim());
                  }}
                >
                  <input
                    autoFocus
                    value={newName}
                    maxLength={120}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => e.key === "Escape" && setNewName(null)}
                    aria-label="Project name"
                    className="h-8 w-64 max-w-full rounded-lg border border-accent-strong bg-panel px-2.5 text-sm text-fg outline-none"
                  />
                  <Button size="sm" type="submit" disabled={rename.isPending || !newName.trim()}>
                    {rename.isPending ? <Loader2 className="animate-spin" /> : "Save"}
                  </Button>
                  <Button size="sm" variant="quiet" type="button" onClick={() => setNewName(null)}>
                    Cancel
                  </Button>
                </form>
              )}
              {v ? (
                <StatusBadge status={v.passed ? "succeeded" : "failed"} />
              ) : (
                <span className="text-xs text-muted">older version</span>
              )}
            </div>
            <p className="mt-0.5 truncate text-xs text-[#8c92a2]">
              {p.spec?.summary ?? p.id}
            </p>
            {v && <p className="mt-0.5 text-[11px] text-[#787f90]">{v.summary}</p>}
            {p.verification_stale && (
              <p className="mt-1 text-[11px] text-warn">You edited files by hand after the last check, so the test results above may be out of date.</p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <a href={downloadUrl(p.id)} download>
              <Button variant="ghost" size="sm">
                <Download /> Download zip
              </Button>
            </a>
            <Button
              variant="danger"
              size="sm"
              title="Delete this project from disk"
              disabled={remove.isPending}
              onClick={() =>
                confirm(`Delete project "${p.name}" from disk? This cannot be undone.`) &&
                remove.mutate()
              }
            >
              <Trash2 /> Delete
            </Button>
          </div>
        </div>

        {/* Change Request Bar */}
        {p.spec && (
          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (change.trim().length < 3) return;
              if (dirty.length && !confirm("You have unsaved edits. The crew works from the saved files, so save first or your edits will be lost. Continue anyway?")) return;
              iterate.mutate();
            }}
          >
            <div className="relative flex-1">
              <input
                value={change}
                onChange={(e) => setChange(e.target.value)}
                placeholder="Want something different? Describe the change, e.g. 'Add a dark mode button'"
                className="h-[34px] w-full rounded-lg border border-line-strong bg-panel px-3 text-[13px] text-fg outline-none transition-[border-color,box-shadow] duration-200 placeholder:text-muted focus:border-accent-strong focus:shadow-[0_0_0_3px_#7c66dc22]"
              />
            </div>
            <Button
              type="submit"
              disabled={iterate.isPending || change.trim().length < 3}
            >
              {iterate.isPending ? <Loader2 className="animate-spin" /> : <Send />}
              Request change
            </Button>
          </form>
        )}
        <ErrorNote error={iterate.error ?? remove.error ?? rename.error} />
      </div>

      <Tabs
        value={activeTab}
        onChange={setActiveTab}
        className="bg-[#121317]"
        tabs={[
          { id: "code" as Tab, label: "Code", icon: FileCode2, count: paths.length },
          ...(canTry ? [{ id: "try" as Tab, label: tryLabel, icon: htmlEntry(p.files) ? Globe : Play }] : []),
          ...(p.readme ? [{ id: "readme" as Tab, label: "README", icon: BookOpen }] : []),
          ...(p.spec ? [{ id: "spec" as Tab, label: "Plan", icon: ClipboardList }] : []),
          { id: "history" as Tab, label: "History", icon: History },
        ]}
      />

      {/* 4. WORKSPACE CONTENT */}
      <div key={activeTab} className="tab-panel flex min-h-0 flex-1 overflow-hidden">
        {activeTab === "code" && (
          <>
            {/* Project File Tree */}
            <div className="scroll-thin w-40 shrink-0 overflow-y-auto border-r border-line bg-[#121317] py-2 sm:w-56">
              <div className="px-4 py-1 text-[10.5px] font-semibold tracking-wider text-muted uppercase">Files</div>
              <div className="stagger flex flex-col gap-0.5 px-2">
                {paths.map((filePath) => {
                  const isTest = p.tests[filePath] !== undefined;
                  return (
                    <button
                      key={filePath}
                      onClick={() => setSelectedFile(filePath)}
                      className={clsx(
                        "file-row truncate",
                        activePath === filePath && "active"
                      )}
                      title={filePath}
                    >
                      <FileCode2
                        className={clsx(
                          "file-icon",
                          isTest ? "text-[#e8ae79]" : "text-[#72a9ee]"
                        )}
                      />
                      <span className="truncate">{filePath}</span>
                      {drafts[filePath] !== undefined && (
                        <span className="ml-auto size-2 shrink-0 rounded-full bg-warn" title="Unsaved changes" aria-label="Unsaved changes" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Monaco Editor View */}
            <div
              className="relative flex min-w-0 flex-1 flex-col overflow-hidden bg-[#101114]"
              onKeyDown={(e) => {
                if (e.key.toLowerCase() === "s" && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  if (dirty.length && !save.isPending) save.mutate();
                }
              }}
            >
              {activePath && allFiles[activePath] !== undefined ? (
                <>
                  <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-1.5 text-xs text-muted">
                    <span className="truncate font-mono text-fg">{activePath}</span>
                    {dirty.length ? (
                      <span className="text-warn">
                        · {dirty.length} unsaved file{dirty.length > 1 ? "s" : ""}
                      </span>
                    ) : (
                      <span className="hidden sm:inline">· Click in the code to edit it yourself</span>
                    )}
                    <div className="ml-auto flex items-center gap-2">
                      {save.error ? <span className="text-bad">{save.error instanceof Error ? save.error.message : String(save.error)}</span> : null}
                      <Button size="sm" variant="quiet" disabled={!dirty.length || save.isPending} onClick={() => setDrafts({})} title="Throw away unsaved edits">
                        <RotateCcw /> Discard
                      </Button>
                      <Button size="sm" disabled={!dirty.length || save.isPending} onClick={() => save.mutate()} title="Save (Ctrl+S)">
                        {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save
                      </Button>
                    </div>
                  </div>
                  <div className="min-h-0 flex-1">
                    <CodeView
                      path={activePath}
                      content={drafts[activePath] ?? allFiles[activePath]}
                      onChange={(value) =>
                        setDrafts((d) => {
                          const next = { ...d };
                          if (value === allFiles[activePath]) delete next[activePath];
                          else next[activePath] = value;
                          return next;
                        })
                      }
                    />
                  </div>
                </>
              ) : (
                <div className="grid flex-1 place-items-center text-xs text-[#717787]">
                  No file selected.
                </div>
              )}
            </div>
          </>
        )}

        {activeTab === "try" && <TryIt projectId={p.id} files={p.files} />}

        {/* README Tab */}
        {activeTab === "readme" && p.readme && (
          <div className="scroll-thin flex-1 overflow-y-auto p-8">
            <div className="mx-auto max-w-3xl rounded-xl border border-[#262934] bg-[#15171e] p-8 shadow-xl">
              <Markdown>{p.readme}</Markdown>
            </div>
          </div>
        )}

        {/* Spec Tab */}
        {activeTab === "spec" && p.spec && (
          <div className="scroll-thin flex-1 overflow-y-auto p-6">
            <div className="mx-auto max-w-4xl">
              <SpecPanel spec={p.spec} />
            </div>
          </div>
        )}

        {/* History Tab */}
        {activeTab === "history" && (
          <div className="scroll-thin flex-1 overflow-y-auto p-6">
            <div className="mx-auto max-w-3xl">
              <h2 className="mb-3 text-sm font-semibold text-white">
                Every run that built or changed this project
              </h2>
              <RunList projectId={p.id} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

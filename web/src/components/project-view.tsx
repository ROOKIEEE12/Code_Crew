"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowLeft,
  BookOpen,
  ClipboardList,
  Download,
  ExternalLink,
  FileCode2,
  Globe,
  History,
  Loader2,
  RefreshCw,
  Send,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api, downloadUrl, previewUrl } from "@/lib/api";
import { CodeView } from "./code-view";
import { Markdown } from "./markdown";
import { RunList } from "./run-list";
import { SpecPanel } from "./spec-panel";
import { Button, ErrorNote, StatusBadge, Tabs } from "./ui";

type Tab = "code" | "preview" | "readme" | "spec" | "history";

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
  const [change, setChange] = useState("");
  const [previewKey, setPreviewKey] = useState(0);

  const iterate = useMutation({
    mutationFn: () => api.iterate(id, change.trim()),
    onSuccess: (run) => router.push(`/runs/${run.id}`),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteProject(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
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

  const hasPreview = Object.keys(p.files).some((f) => f.endsWith(".html"));
  const entry =
    p.files["index.html"] !== undefined
      ? "index.html"
      : Object.keys(p.files).find((f) => f.endsWith(".html"));
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
              <h1 className="truncate text-base font-semibold text-white">{p.name}</h1>
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
              title="Delete project"
              aria-label="Delete project"
              disabled={remove.isPending}
              onClick={() =>
                confirm(`Delete project "${p.name}" from disk? This cannot be undone.`) &&
                remove.mutate()
              }
            >
              <Trash2 />
            </Button>
          </div>
        </div>

        {/* Change Request Bar */}
        {p.spec && (
          <form
            className="mt-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (change.trim().length >= 3) iterate.mutate();
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
        <ErrorNote error={iterate.error ?? remove.error} />
      </div>

      <Tabs
        value={activeTab}
        onChange={setActiveTab}
        className="bg-[#121317]"
        tabs={[
          { id: "code" as Tab, label: "Code", icon: FileCode2, count: paths.length },
          ...(hasPreview ? [{ id: "preview" as Tab, label: "Live preview", icon: Globe }] : []),
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
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Monaco Editor View */}
            <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden bg-[#101114]">
              {activePath && allFiles[activePath] !== undefined ? (
                <CodeView path={activePath} content={allFiles[activePath]} />
              ) : (
                <div className="grid flex-1 place-items-center text-xs text-[#717787]">
                  No file selected.
                </div>
              )}
            </div>
          </>
        )}

        {/* Live Preview Tab with Browser Frame */}
        {activeTab === "preview" && entry && (
          <div className="flex flex-1 flex-col overflow-hidden bg-[#0d0e11]">
            {/* Mock Browser URL Bar */}
            <div className="flex items-center gap-2 border-b border-[#252834] bg-[#171920] px-3 py-1.5 text-xs text-[#8c92a2]">
              <button
                onClick={() => setPreviewKey((k) => k + 1)}
                className="rounded p-1 hover:bg-[#252936] hover:text-white"
                title="Reload Preview"
              >
                <RefreshCw className="size-3.5" />
              </button>
              <div className="flex flex-1 items-center rounded border border-[#2b2f3d] bg-[#101217] px-2.5 py-1 font-mono text-[11px] text-[#c0c5d4]">
                <span>preview://{p.id}/{entry}</span>
              </div>
              <a
                href={previewUrl(p.id, entry)}
                target="_blank"
                rel="noreferrer"
                className="rounded p-1 text-[#8c92a2] hover:bg-[#252936] hover:text-white"
                title="Open in new window"
              >
                <ExternalLink className="size-3.5" />
              </a>
            </div>

            <iframe
              key={previewKey}
              src={previewUrl(p.id, entry)}
              className="h-full w-full border-0 bg-white"
              title="Sandboxed Live Preview"
            />
          </div>
        )}

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

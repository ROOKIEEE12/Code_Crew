"use client";

import { ArrowLeft, BookOpen, ClipboardList, Code2, GitCompare, MessagesSquare, ShieldCheck, Sparkles, Square } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { compact, duration } from "@/lib/format";
import { useRunStream } from "@/lib/use-run-stream";
import { CodeView } from "../code-view";
import { Markdown } from "../markdown";
import { SpecPanel } from "../spec-panel";
import { Button, ErrorNote, StatusBadge, Tabs, type TabDef } from "../ui";
import { ActivityPanel } from "./activity-panel";
import { ChecksPanel } from "./checks-panel";
import { FileExplorer } from "./file-explorer";
import { NowCard, Pipeline, ResultBanner } from "./pipeline";

type Tab = "code" | "checks" | "plan" | "readme" | "activity";

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

export function RunView() {
  const { id } = useParams<{ id: string }>();
  const view = useRunStream(id);

  const [tab, setTab] = useState<Tab>("code");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [versionIdx, setVersionIdx] = useState<number | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [cancelError, setCancelError] = useState<unknown>(null);
  const [cancelling, setCancelling] = useState(false);

  const running = !view.done && (view.status === "running" || view.status === "queued");
  const now = useNow(running);
  const run = view.run;
  const mode = run?.mode ?? "build";
  const files = Object.values(view.files);
  const sources = files.filter((f) => f.kind === "source").length;

  const current = selectedFile ? view.files[selectedFile] : files.find((f) => f.kind === "source") ?? files[0];
  const versions = current?.versions ?? [];
  const vIdx = versionIdx !== null && versionIdx < versions.length ? versionIdx : versions.length - 1;
  const version = versions[vIdx];
  const previous = vIdx > 0 ? versions[vIdx - 1] : undefined;
  const latest = view.verifications[view.verifications.length - 1];
  const finishedAt = run?.finished_at ?? (view.done ? now : null);
  const elapsed = run ? (finishedAt ?? now) - (run.created_at ?? now) : 0;
  const shownError = cancelError ?? (view.done ? null : view.error);

  function pick(path: string) {
    setSelectedFile(path);
    setVersionIdx(null);
    setShowDiff(false);
  }

  async function cancel() {
    setCancelling(true);
    try {
      await api.cancelRun(id);
    } catch (e) {
      setCancelError(e);
      setCancelling(false);
    }
  }

  const tabs: TabDef<Tab>[] = [
    { id: "code", label: "Code", icon: Code2, count: files.length || undefined },
    {
      id: "checks",
      label: "Test results",
      icon: ShieldCheck,
      count: latest ? (latest.tests_total ? `${latest.tests_passed}/${latest.tests_total}` : latest.passed ? "ok" : "!") : undefined,
      tone: latest ? (latest.passed ? "ok" : "bad") : undefined,
    },
    { id: "plan", label: "Plan", icon: ClipboardList },
    { id: "readme", label: "README", icon: BookOpen },
    { id: "activity", label: "Activity", icon: MessagesSquare, count: view.activity.length || undefined, className: "lg:hidden" },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* header: what was asked, where it stands */}
      <div className="border-b border-line bg-[#121317] px-4 pt-3 pb-4 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <Link href="/runs" className="inline-flex items-center gap-1 rounded-md px-1 py-0.5 transition-colors hover:bg-panel-2 hover:text-fg">
                <ArrowLeft className="size-3.5" /> Runs
              </Link>
              <span>·</span>
              <StatusBadge status={view.status} />
              <span>{mode === "iterate" ? `Change to ${run?.project_id}` : "New build"}</span>
              {!running && <span>· took {duration(elapsed)}</span>}
              {view.usage && (
                <span title="How many times the AI was called, and how much text it wrote">
                  · {view.usage.calls} AI calls · {compact(view.usage.output_tokens)} tokens
                </span>
              )}
              {view.connection === "connecting" && running && <span className="text-warn">· reconnecting…</span>}
            </div>
            <h1 className="mt-1.5 line-clamp-2 text-[15px] font-semibold text-white">{run?.requirement ?? "Loading…"}</h1>
          </div>
          {running && (
            <Button variant="danger" size="sm" onClick={cancel} disabled={cancelling}>
              <Square /> {cancelling ? "Stopping…" : "Stop"}
            </Button>
          )}
        </div>

        <div className="mt-4">
          <Pipeline view={view} mode={mode} />
        </div>

        <div className="mt-4 space-y-2">
          {shownError ? <ErrorNote error={shownError} /> : null}
          {running ? <NowCard view={view} mode={mode} elapsed={elapsed} /> : <ResultBanner view={view} onShowChecks={() => setTab("checks")} />}
        </div>
      </div>

      {/* body: tabbed workspace + always-visible activity feed */}
      <div className="flex min-h-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col">
          <Tabs tabs={tabs} value={tab} onChange={setTab} className="bg-[#121317]" />

          <div key={tab} className="tab-panel min-h-0 flex-1">
            {tab === "code" &&
              (files.length === 0 ? (
                <div className="grid h-full place-items-center p-8 text-center">
                  <div>
                    <Sparkles className="mx-auto mb-3 size-7 animate-pulse text-accent" />
                    <p className="text-sm text-fg">{running ? "No files yet. The crew is still planning." : "This run produced no files."}</p>
                    {running && <p className="mt-1 text-xs text-muted">Tests appear first, then the code. You can follow along on the right.</p>}
                  </div>
                </div>
              ) : (
                <div className="flex h-full min-h-0">
                  <div className="scroll-thin w-40 shrink-0 overflow-y-auto border-r border-line bg-[#121317] sm:w-56">
                    <FileExplorer files={files} selected={current?.path ?? null} onSelect={pick} verification={latest} />
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col">
                    {current && version && (
                      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-1.5 text-xs text-muted">
                        <span className="truncate font-mono text-fg">{current.path}</span>
                        <span>· by {version.by || "agent"}</span>
                        <div className="ml-auto flex items-center gap-2">
                          {versions.length > 1 && (
                            <>
                              <select
                                value={vIdx}
                                onChange={(e) => setVersionIdx(Number(e.target.value))}
                                className="rounded-md border border-line-strong bg-panel px-1.5 py-0.5 text-xs text-fg"
                                aria-label="Version"
                              >
                                {versions.map((v, i) => (
                                  <option key={i} value={i}>
                                    Version {i + 1} of {versions.length} ({v.by})
                                  </option>
                                ))}
                              </select>
                              <button
                                className={showDiff ? "btn btn-ghost btn-sm" : "btn btn-quiet btn-sm"}
                                onClick={() => setShowDiff((d) => !d)}
                                disabled={!previous}
                                title="Highlight what changed from the previous version"
                              >
                                <GitCompare /> {showDiff ? "Hide changes" : "Show changes"}
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    )}
                    <div className="min-h-0 flex-1">
                      {current && version && <CodeView path={current.path} content={version.content} original={showDiff && previous ? previous.content : undefined} />}
                    </div>
                  </div>
                </div>
              ))}

            {tab === "checks" && (
              <div className="scroll-thin h-full overflow-y-auto">
                <div className="mx-auto max-w-4xl">
                  <ChecksPanel verification={latest} rounds={view.debugRounds} disputes={view.disputes} />
                </div>
              </div>
            )}

            {tab === "plan" && (
              <div className="scroll-thin h-full overflow-y-auto">
                <div className="mx-auto max-w-4xl">
                  <SpecPanel spec={view.spec} />
                </div>
              </div>
            )}

            {tab === "readme" && (
              <div className="scroll-thin h-full overflow-y-auto p-6">
                <div className="mx-auto max-w-3xl">
                  {view.readme ? (
                    <Markdown>{view.readme}</Markdown>
                  ) : (
                    <p className="text-sm text-muted">The Reviewer writes the README at the end, after the checks.</p>
                  )}
                </div>
              </div>
            )}

            {tab === "activity" && <ActivityPanel activity={view.activity} live={running} done={view.done?.status} />}
          </div>
        </section>

        <aside className="hidden w-[340px] shrink-0 border-l border-line bg-[#121317] lg:block">
          <ActivityPanel activity={view.activity} live={running} done={view.done?.status} />
        </aside>
      </div>

      {sources === 0 && files.length > 0 && running && (
        <p className="sr-only" aria-live="polite">
          Tests written. The Coder is writing the code now.
        </p>
      )}
    </div>
  );
}

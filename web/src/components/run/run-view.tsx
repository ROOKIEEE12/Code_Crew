"use client";

import clsx from "clsx";
import { ArrowLeft, BookOpen, ClipboardList, Code2, GitCompare, MessagesSquare, MonitorPlay, Pencil, Play, ShieldCheck, Sparkles, Square, Trash2, Volume2, VolumeX } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { BUILD_STEPS, ITERATE_STEPS } from "@/lib/crew";
import { usePref } from "@/lib/prefs";
import { useDeleteRun } from "@/lib/use-delete-run";
import { setSound, sounds } from "@/lib/sound";
import { useRunStream } from "@/lib/use-run-stream";
import { CodeView } from "../code-view";
import { Markdown } from "../markdown";
import { DesignInputs, DesignReviews } from "../design-panel";
import { SpecPanel } from "../spec-panel";
import { TryIt } from "../try-it";
import { Button, ErrorNote, StatusBadge, Tabs, type TabDef } from "../ui";
import { Celebrate } from "./celebrate";
import { ChecksPanel } from "./checks-panel";
import { Crew, Meter } from "./crew-board";
import { FileExplorer } from "./file-explorer";
import { LiveWork } from "./live-work";
import { NowCard, ResultBanner } from "./pipeline";
import { Transcript } from "./transcript";

type Tab = "live" | "try" | "code" | "checks" | "plan" | "readme" | "transcript";

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
  const router = useRouter();
  const remove = useDeleteRun(() => router.push("/runs"));
  const [connection, setConnection] = useState(0);
  const view = useRunStream(id, connection);
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);

  const [tab, setTab] = useState<Tab>("live");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [versionIdx, setVersionIdx] = useState<number | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [cancelError, setCancelError] = useState<unknown>(null);
  const [cancelling, setCancelling] = useState(false);
  const [crewStyle, setCrewStyle] = usePref("crew-style", "faces");
  const [soundPref, setSoundPref] = usePref("sound", "0");

  const running = !view.done && (view.status === "running" || view.status === "queued");
  const now = useNow(running);
  const run = view.run;
  const mode = run?.mode ?? "build";
  const files = Object.values(view.files);

  const current = selectedFile ? view.files[selectedFile] : files.find((f) => f.kind === "source") ?? files[0];
  const versions = current?.versions ?? [];
  const vIdx = versionIdx !== null && versionIdx < versions.length ? versionIdx : versions.length - 1;
  const version = versions[vIdx];
  const previous = vIdx > 0 ? versions[vIdx - 1] : undefined;
  const latest = view.verifications[view.verifications.length - 1];
  const finishedAt = run?.finished_at ?? (view.done ? now : null);
  const elapsed = run ? (finishedAt ?? now) - (run.created_at ?? now) : 0;
  const shownError = cancelError ?? (view.done ? null : view.error);
  const savedProject = view.done?.project_id ?? null;

  // Sound: the pref survives reloads, but audio can only start after a click,
  // so a saved "on" becomes active on the first interaction with the page.
  useEffect(() => {
    if (soundPref !== "1") return;
    const enable = () => setSound(true);
    window.addEventListener("pointerdown", enable, { once: true });
    return () => window.removeEventListener("pointerdown", enable);
  }, [soundPref]);

  // A blip each time the baton moves to a new agent.
  const steps = mode === "iterate" ? ITERATE_STEPS : BUILD_STEPS;
  const lastPhase = useRef(view.phase);
  useEffect(() => {
    if (running && view.phase !== lastPhase.current) sounds.step(Math.max(0, steps.indexOf(view.phase)));
    lastPhase.current = view.phase;
  }, [view.phase, running, steps]);

  function toggleSound() {
    const on = soundPref !== "1";
    setSoundPref(on ? "1" : "0");
    setSound(on);
    if (on) sounds.pass();
  }

  function pick(path: string) {
    setSelectedFile(path);
    setVersionIdx(null);
    setShowDiff(false);
  }

  async function resume() {
    setResuming(true);
    setResumeError(null);
    try {
      await api.resumeRun(id);
      setConnection((c) => c + 1); // reconnect to follow the resumed run live
      setCancelling(false);
    } catch (e) {
      setResumeError(e instanceof Error ? e.message : String(e));
    } finally {
      setResuming(false);
    }
  }

  // Fix a wrong prompt: open it again for editing. A new build replaces this run;
  // a change request goes back to its project.
  function editPrompt() {
    if (!run) return;
    const prompt = encodeURIComponent(run.requirement);
    router.push(mode === "iterate" && run.project_id ? `/projects/${run.project_id}?change=${prompt}` : `/?prompt=${prompt}&replace=${id}`);
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
    { id: "live", label: "Live", icon: MonitorPlay },
    ...(savedProject ? [{ id: "try" as Tab, label: "Try it", icon: Play }] : []),
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
    { id: "transcript", label: "Transcript", icon: MessagesSquare, count: view.timeline.length || undefined, className: "lg:hidden" },
  ];

  const minimal = crewStyle === "minimal";

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* header: what was asked + controls */}
      <div className="border-b border-line bg-[#121317] px-4 py-3 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1 basis-[260px]">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <Link href="/runs" className="inline-flex items-center gap-1 rounded-md px-1 py-0.5 transition-colors hover:bg-panel-2 hover:text-fg">
                <ArrowLeft className="size-3.5" /> Runs
              </Link>
              <span>·</span>
              <StatusBadge status={view.status} />
              <span>{mode === "iterate" ? `Change to ${run?.project_id}` : "New build"}</span>
              {view.connection === "connecting" && running && <span className="text-warn">· reconnecting…</span>}
            </div>
            <h1 className="mt-1.5 line-clamp-2 text-[15px] font-semibold text-white">{run?.requirement ?? "Loading…"}</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="seg hidden sm:inline-flex" role="group" aria-label="Crew style">
              <button type="button" aria-pressed={!minimal} onClick={() => setCrewStyle("faces")}>
                Faces
              </button>
              <button type="button" aria-pressed={minimal} onClick={() => setCrewStyle("minimal")}>
                Minimal
              </button>
            </div>
            <button type="button" className={clsx("icon-btn", soundPref === "1" && "on")} onClick={toggleSound} aria-pressed={soundPref === "1"} title={soundPref === "1" ? "Sound on" : "Sound off"}>
              {soundPref === "1" ? <Volume2 /> : <VolumeX />}
            </button>
            {running && (
              <Button variant="danger" size="sm" onClick={cancel} disabled={cancelling}>
                <Square /> {cancelling ? "Stopping…" : "Stop"}
              </Button>
            )}
            {!running && run && (
              <Button variant="ghost" size="sm" onClick={editPrompt} title="Fix the prompt and start again">
                <Pencil /> Edit prompt
              </Button>
            )}
            {run && (
              <Button
                variant="danger"
                size="sm"
                onClick={() => remove.ask({ id, requirement: run.requirement, status: running ? "running" : view.status })}
                disabled={remove.isPending}
                title={running ? "Stop this run and delete it" : "Delete this run"}
                aria-label="Delete run"
              >
                <Trash2 />
              </Button>
            )}
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* left: the board and the work */}
        <section className="board relative flex min-w-0 flex-1 flex-col">
          <div className="border-b border-line bg-[#121317]/60 pb-3">
            <Meter view={view} elapsed={elapsed} running={running} />
            <Crew view={view} mode={mode} running={running} now={now} minimal={minimal} />
            <div className="space-y-2 px-4 sm:px-5">
              {shownError ? <ErrorNote error={shownError} /> : null}
              <ErrorNote error={remove.error} />
              {running ? <NowCard view={view} mode={mode} elapsed={elapsed} onAnswer={() => setTab("transcript")} /> : <ResultBanner view={view} onShowChecks={() => setTab("checks")} onTryIt={savedProject ? () => setTab("try") : undefined} onResume={resume} resuming={resuming} resumeError={resumeError} />}
            </div>
          </div>

          <Tabs tabs={tabs} value={tab} onChange={setTab} className="bg-[#121317]" />

          <div key={tab} className="tab-panel min-h-0 flex-1">
            {tab === "live" && <LiveWork view={view} running={running} />}

            {tab === "try" && savedProject && <TryIt projectId={savedProject} />}

            {tab === "code" &&
              (files.length === 0 ? (
                <div className="grid h-full place-items-center p-8 text-center">
                  <div>
                    <Sparkles className="mx-auto mb-3 size-7 animate-pulse text-accent" />
                    <p className="text-sm text-fg">{running ? "No files yet. The crew is still planning." : "This run produced no files."}</p>
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
                  <DesignReviews runId={id} reviews={view.designReviews.length ? view.designReviews : run?.design_reviews ?? []} />
                  <ChecksPanel verification={latest} rounds={view.debugRounds} disputes={view.disputes} />
                </div>
              </div>
            )}

            {tab === "plan" && (
              <div className="scroll-thin h-full overflow-y-auto">
                <div className="mx-auto max-w-4xl">
                  <DesignInputs runId={id} references={view.references.length ? view.references : run?.references ?? []} images={run?.images ?? []} />
                  {view.run?.clarifications?.length ? (
                    <div className="px-4 pt-4 sm:px-6">
                      <h3 className="mb-1 text-xs font-medium text-muted">Agreed with you before planning</h3>
                      <ul className="space-y-1 text-[13px]">
                        {view.run.clarifications.map((c, i) => (
                          <li key={i} className="rounded-lg border border-line bg-panel px-3 py-2">
                            <span className="text-muted">{c.question}</span> <span className="text-fg">{c.answer}</span>
                            {c.auto && <span className="ml-1 text-xs text-muted">(recommended default)</span>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  <SpecPanel spec={view.spec} />
                </div>
              </div>
            )}

            {tab === "readme" && (
              <div className="scroll-thin h-full overflow-y-auto p-6">
                <div className="mx-auto max-w-3xl">
                  {view.readme ? <Markdown>{view.readme}</Markdown> : <p className="text-sm text-muted">The Reviewer writes the README at the end, after the checks.</p>}
                </div>
              </div>
            )}

            {tab === "transcript" && <Transcript view={view} runId={id} mode={mode} running={running} now={now} />}
          </div>

          <Celebrate view={view} />
        </section>

        {/* right: the crew transcript */}
        <aside className="hidden w-[400px] shrink-0 border-l border-line bg-[#121317] lg:block">
          <Transcript view={view} runId={id} mode={mode} running={running} now={now} />
        </aside>
      </div>
    </div>
  );
}

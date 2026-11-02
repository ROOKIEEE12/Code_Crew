"use client";

import clsx from "clsx";
import { Check, FileCode2, FlaskConical, Loader2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { highlightLine, langOf, testNames } from "@/lib/highlight";
import { parseLiveFiles, type LiveFile } from "@/lib/live-files";
import { sounds } from "@/lib/sound";
import { isFresh, type RunView, type TrackedFile } from "@/lib/use-run-stream";

// ---------------------------------------------------------------- code pane

function useTyping(text: string, animate: boolean) {
  const [progress, setProgress] = useState({ text: "", shown: 0 });
  useEffect(() => {
    if (!animate) return;
    const total = Math.min(2600, Math.max(500, text.length * 5));
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / total);
      setProgress({ text, shown: Math.round(text.length * p) });
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [text, animate]);
  if (!animate) return text.length;
  return progress.text === text ? progress.shown : 0;
}

function CodePane({ view, file, running }: { view: RunView; file: TrackedFile | undefined; running: boolean }) {
  const version = file?.versions[file.versions.length - 1];
  const previous = file && file.versions.length > 1 ? file.versions[file.versions.length - 2] : undefined;
  const content = version?.content ?? "";
  const fresh = running && isFresh(version?.ts);
  // The user already watched it stream in when the model could stream; only type out files that appeared all at once.
  const streamed = useMemo(() => Object.values(view.calls).some((c) => c.live?.text.includes(`<<<FILE path="${file?.path}">>>`)), [view.calls, file?.path]);
  const shown = useTyping(content, fresh && !previous && !streamed);
  const lang = langOf(file?.path ?? "");
  const box = useRef<HTMLPreElement>(null);

  // Lines the latest failed check blamed on this file (only if that check ran on this version).
  const latest = view.verifications[view.verifications.length - 1];
  const bugLines = useMemo(() => {
    if (!file || !latest || latest.passed || !version || latest.ts < version.ts) return new Set<number>();
    return new Set(latest.issues.filter((i) => i.file === file.path && i.severity === "error" && i.line).map((i) => i.line!));
  }, [file, latest, version]);

  // Lines that changed in a fix, flashed briefly when it arrives live.
  const changed = useMemo(() => {
    if (!previous || !fresh) return new Set<number>();
    const before = new Set(previous.content.split("\n"));
    return new Set(content.split("\n").flatMap((l, i) => (before.has(l) ? [] : [i + 1])));
  }, [previous, content, fresh]);

  const visible = content.slice(0, shown);
  const lines = visible.split("\n");
  const typing = shown < content.length;

  useEffect(() => {
    if (typing && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [typing, lines.length]);

  if (!file)
    return <div className="grid h-full place-items-center p-6 text-center text-[13px] text-muted">{running ? "The Coder hasn't started yet." : "No code was written."}</div>;

  return (
    <pre ref={box} className="live-code scroll-thin" aria-label={`Code of ${file.path}`}>
      {lines.map((l, i) => (
        <span
          key={i}
          className={clsx("ln", bugLines.has(i + 1) && "bug", changed.has(i + 1) && "flash")}
          data-n={i + 1}
          dangerouslySetInnerHTML={{ __html: (highlightLine(l, lang) || " ") + (typing && i === lines.length - 1 ? '<span class="type-caret"></span>' : "") }}
        />
      ))}
    </pre>
  );
}

// ---------------------------------------------------------------- live stream pane

/** Files the models are writing right now, across every call still in progress
 *  (the Coder can write several files in parallel). */
function useLiveFiles(view: RunView): { files: (LiveFile & { by: string })[]; agent: string } {
  return useMemo(() => {
    const active = Object.values(view.calls)
      .filter((c) => c.endTs === undefined && c.live?.text)
      .sort((a, b) => a.id - b.id);
    const files = active.flatMap((c) => parseLiveFiles(c.live!.text).map((f) => ({ ...f, by: STEP_AGENT[c.step] ?? "Coder" })));
    return { files, agent: active.length ? STEP_AGENT[active[active.length - 1].step] ?? "Coder" : "" };
  }, [view.calls]);
}

const STEP_AGENT: Record<string, string> = { coding: "Coder", debugging: "Debugger", testing: "Test Author", documenting: "Reviewer" };

/** Models send their answer in bursts (often several lines every few seconds). This
 *  types the received text out character by character at a pace that adapts to the
 *  backlog, so code flows onto the screen steadily and never falls more than about
 *  two seconds behind. A file that was already finished when opened is shown whole. */
function useSmoothLength(text: string, finishedAtOpen: boolean): number {
  const [shown, setShown] = useState(() => (finishedAtOpen ? text.length : 0));
  const target = useRef(text.length);
  useEffect(() => {
    target.current = text.length;
  }, [text.length]);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setShown(target.current);
      return;
    }
    let raf = 0;
    let last = performance.now();
    let pos = finishedAtOpen ? target.current : 0;
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const backlog = target.current - pos;
      if (backlog > 0) {
        // Spread each burst over ~2s so the gaps between bursts stay filled with typing.
        const speed = Math.max(30, backlog / 2); // characters per second
        pos = Math.min(target.current, pos + Math.max(1, speed * dt));
        setShown(Math.floor(pos));
      } else if (backlog < 0) {
        pos = target.current; // the attempt restarted with less text
        setShown(pos);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [finishedAtOpen]);
  return Math.min(shown, text.length);
}

function LivePane({ file }: { file: LiveFile }) {
  const box = useRef<HTMLPreElement>(null);
  const follow = useRef(true);
  const [finishedAtOpen] = useState(file.done);
  const shownLength = useSmoothLength(file.content, finishedAtOpen);
  const typing = shownLength < file.content.length || !file.done;
  const lang = langOf(file.path);
  const lines = file.content.slice(0, shownLength).split("\n");

  // Keep the newest line in view while it is being written, unless the user scrolled up to read.
  useEffect(() => {
    if (follow.current && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [shownLength]);

  return (
    <pre
      ref={box}
      className="live-code scroll-thin"
      aria-label={`${file.path}, being written`}
      aria-busy={typing}
      onScroll={(e) => {
        const el = e.currentTarget;
        follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
      }}
    >
      {lines.map((l, i) => (
        <span
          key={i}
          className="ln"
          data-n={i + 1}
          dangerouslySetInnerHTML={{ __html: (highlightLine(l, lang) || " ") + (typing && i === lines.length - 1 ? '<span class="type-caret"></span>' : "") }}
        />
      ))}
    </pre>
  );
}

// ---------------------------------------------------------------- tests pane

type Row = { name: string; outcome: "pending" | "run" | "passed" | "failed" | "skipped" };

function TestsPane({ view, running }: { view: RunView; running: boolean }) {
  const latest = view.verifications[view.verifications.length - 1];
  const testsRunning = Object.values(view.tools).some((t) => (t.key === "pytest" || t.key === "node") && t.status === "running");
  const declared = useMemo(
    () => Object.values(view.files).filter((f) => f.kind === "test").flatMap((f) => testNames(f.versions[f.versions.length - 1].content)),
    [view.files],
  );

  const results = useMemo<Row[] | null>(
    () =>
      latest
        ? latest.test_runs.flatMap((r) => r.cases).map((c) => ({ name: c.name, outcome: c.outcome === "error" ? "failed" : c.outcome }))
        : null,
    [latest],
  );

  // Reveal fresh results one by one, like a test runner printing them.
  const [revealed, setRevealed] = useState(Infinity);
  const lastAnimated = useRef(0);
  useEffect(() => {
    if (!latest || !results || !isFresh(latest.ts) || lastAnimated.current === latest.ts) return;
    lastAnimated.current = latest.ts;
    setRevealed(0);
    let i = 0;
    const t = setInterval(() => {
      i++;
      setRevealed(i);
      const r = results[i - 1];
      if (r) (r.outcome === "passed" ? sounds.pass : r.outcome === "failed" ? sounds.fail : () => {})();
      if (i >= results.length) clearInterval(t);
    }, 160);
    return () => clearInterval(t);
  }, [latest, results]);

  // While the suite runs, a spinner walks down the declared tests.
  const [walker, setWalker] = useState(0);
  useEffect(() => {
    if (!testsRunning) return;
    const t = setInterval(() => setWalker((w) => w + 1), 380);
    return () => clearInterval(t);
  }, [testsRunning]);

  let rows: Row[];
  if (results && !testsRunning) {
    rows = results.map((r, i) => (i < revealed ? r : i === revealed ? { ...r, outcome: "run" } : { ...r, outcome: "pending" }));
  } else {
    const names = declared.length ? declared : results?.map((r) => r.name) ?? [];
    rows = names.map((name, i) => ({ name, outcome: testsRunning && i === walker % Math.max(names.length, 1) ? "run" : "pending" }));
  }
  const shownRows = rows.slice(0, 200);
  const passed = rows.filter((r) => r.outcome === "passed").length;
  const total = results && !testsRunning ? results.filter((r) => r.outcome !== "skipped").length : rows.length;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="pane-head">
        <span className="flex items-center gap-1.5">
          <FlaskConical className="size-3.5" /> <b>Tests</b>
        </span>
        <span className={clsx("font-mono tabular-nums", results && !testsRunning && passed === total && total > 0 ? "text-ok" : "text-fg")}>
          {results && !testsRunning ? `${passed}/${total}` : total ? `0/${total}` : "–"}
        </span>
      </div>
      {shownRows.length === 0 ? (
        <p className="p-4 text-[13px] text-muted">
          {running ? "The Test Author writes the tests before any code exists. They'll appear here." : "This project has no runnable tests."}
        </p>
      ) : (
        <ul className="tests scroll-thin">
          {shownRows.map((r, i) => (
            <li key={`${r.name}-${i}`} className={clsx("test", r.outcome)}>
              <span className="ic">{r.outcome === "passed" ? <Check /> : r.outcome === "failed" ? <X /> : null}</span>
              <span className="min-w-0 flex-1 truncate" title={r.name}>
                {r.name.replace(/^test_/, "").replace(/_/g, " ")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- the work area

export function LiveWork({ view, running }: { view: RunView; running: boolean }) {
  const sources = Object.values(view.files).filter((f) => f.kind === "source");
  const [picked, setPicked] = useState<string | null>(null);
  const live = useLiveFiles(view);
  const [livePicked, setLivePicked] = useState<string | null>(null);

  if (running && live.files.length) {
    // Follow the file being written now, unless the user picked one from this answer.
    const writingNow = [...live.files].reverse().find((f) => !f.done) ?? live.files[live.files.length - 1];
    const shown = live.files.find((f) => f.path === livePicked) ?? writingNow;
    const lines = shown.content.split("\n").length;
    return (
      <div className="work">
        <div className="pane">
          <div className="pane-head">
            <div className="file-chips scroll-thin">
              {live.files.map((f) => (
                <button
                  key={f.path}
                  type="button"
                  className={clsx("file-chip", f.path === shown.path && "on")}
                  onClick={() => setLivePicked(f.path === writingNow.path ? null : f.path)}
                  title={f.done ? "Finished" : "Being written now"}
                >
                  {f.done ? <Check className="size-3 text-ok" /> : <Loader2 className="size-3 animate-spin text-accent" />} {f.path}
                </button>
              ))}
            </div>
            <span className="live-tag shrink-0">
              <span className="dot" /> {shown.done ? `${shown.by} wrote ${lines} lines` : `${shown.by} is writing · ${lines} lines`}
            </span>
          </div>
          <LivePane key={shown.path} file={shown} />
        </div>
        <div className="pane">
          <TestsPane view={view} running={running} />
        </div>
      </div>
    );
  }

  // Follow whichever source file was written most recently, unless the user picked one.
  const newest = [...sources].sort((a, b) => b.versions[b.versions.length - 1].seq - a.versions[a.versions.length - 1].seq)[0];
  const file = (picked && view.files[picked]) || newest;
  const version = file?.versions[file.versions.length - 1];
  const typing = running && isFresh(version?.ts);

  return (
    <div className="work">
      <div className="pane">
        <div className="pane-head">
          <div className="file-chips scroll-thin">
            {sources.length === 0 ? (
              <b>code</b>
            ) : (
              [...sources]
                .sort((a, b) => a.path.localeCompare(b.path))
                .map((f) => (
                  <button key={f.path} type="button" className={clsx("file-chip", f.path === file?.path && "on")} onClick={() => setPicked(f.path)}>
                    <FileCode2 className="size-3" /> {f.path}
                  </button>
                ))
            )}
          </div>
          <span className="shrink-0">{version ? (typing ? `${version.by} is typing…` : `by ${version.by}`) : "waiting for the Coder"}</span>
        </div>
        <CodePane view={view} file={file} running={running} />
      </div>
      <div className="pane">
        <TestsPane view={view} running={running} />
      </div>
    </div>
  );
}

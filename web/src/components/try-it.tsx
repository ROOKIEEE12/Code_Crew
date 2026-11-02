"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ExternalLink, Globe, Loader2, Play, RefreshCw, TerminalSquare, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, previewUrl, type ExecResult } from "@/lib/api";
import { ErrorNote } from "./ui";

// ---------------------------------------------------------------- what can be tried

const PY = /\.py$/;
const JS = /\.(m|c)?js$/;
const NOT_PROGRAMS = new Set(["__init__.py", "conftest.py", "setup.py"]);
const ENTRY_NAMES = ["main.py", "app.py", "__main__.py", "run.py", "cli.py", "game.py", "index.js", "main.js", "app.js", "cli.js"];

/** Files the Run button can start, the likeliest entry point first. Plain .js
 *  files in a website are browser scripts, so they are only offered without HTML. */
export function runnableFiles(files: Record<string, string>): string[] {
  const hasHtml = Object.keys(files).some((f) => f.endsWith(".html"));
  const base = (f: string) => f.split("/").pop() ?? f;
  const score = (f: string) => {
    const named = ENTRY_NAMES.indexOf(base(f));
    if (named >= 0) return named;
    if (/__name__\s*==\s*["']__main__["']/.test(files[f])) return 20;
    return 40 + f.split("/").length;
  };
  return Object.keys(files)
    .filter((f) => (PY.test(f) || (!hasHtml && JS.test(f))) && !NOT_PROGRAMS.has(base(f)))
    .sort((a, b) => score(a) - score(b) || a.localeCompare(b));
}

export function htmlEntry(files: Record<string, string>): string | undefined {
  return files["index.html"] !== undefined ? "index.html" : Object.keys(files).find((f) => f.endsWith(".html"));
}

/** How many times the program looks like it asks the user for input. */
function inputPrompts(code: string, path: string): number {
  const re = PY.test(path) ? /\binput\s*\(/g : /\b(readline|question|prompt)\s*\(|process\.stdin/g;
  return code.match(re)?.length ?? 0;
}

/** Plain-language explanation for the common ways a run goes wrong. */
function explain(r: ExecResult, stdin: string): string | null {
  const out = r.output;
  if (r.timed_out)
    return `Stopped after ${r.timeout_sec}s. Programs that keep running (a web server, a game loop, an endless loop) cannot finish here. Download the zip to run it on your computer.`;
  if (/EOFError|ERR_USE_AFTER_CLOSE|readline was closed/.test(out))
    return stdin.trim()
      ? "The program asked for more input than you typed. Add another line in the Input box and run again."
      : "The program asked for input, but the Input box is empty. Type your answers there (one per line) and run again.";
  if (/ModuleNotFoundError|Cannot find module/.test(out))
    return "The program needs a package that is not installed on this computer. Install it (see the README) and run again.";
  if (/tkinter|pygame|_tkinter\.TclError|cannot connect to display/i.test(out))
    return "This program opens a window. Windows cannot be shown here, so run it on your computer.";
  if (r.exit_code === 0 && !out.trim()) return "The program finished without printing anything. This file may only define functions that other files use; try another file.";
  return null;
}

// ---------------------------------------------------------------- terminal

interface Session {
  id: number;
  path: string;
  stdin: string;
  result?: ExecResult;
  error?: string;
}

function Terminal({ projectId, files }: { projectId: string; files: Record<string, string> }) {
  const programs = useMemo(() => runnableFiles(files), [files]);
  const [path, setPath] = useState(programs[0]);
  const [stdin, setStdin] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [busy, setBusy] = useState(false);
  const screen = useRef<HTMLDivElement>(null);
  const prompts = path ? inputPrompts(files[path] ?? "", path) : 0;

  useEffect(() => {
    screen.current?.scrollTo({ top: screen.current.scrollHeight, behavior: "smooth" });
  }, [sessions]);

  async function run() {
    if (!path || busy) return;
    const id = Date.now();
    setSessions((s) => [...s.slice(-19), { id, path, stdin }]);
    setBusy(true);
    try {
      const result = await api.exec(projectId, path, stdin);
      setSessions((s) => s.map((x) => (x.id === id ? { ...x, result } : x)));
    } catch (e) {
      setSessions((s) => s.map((x) => (x.id === id ? { ...x, error: e instanceof Error ? e.message : String(e) } : x)));
    } finally {
      setBusy(false);
    }
  }

  const command = (p: string) => `${PY.test(p) ? "python" : "node"} ${p}`;

  return (
    <div
      className="flex min-h-0 flex-1 flex-col"
      onKeyDown={(e) => {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          run();
        }
      }}
    >
      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-[#252834] bg-[#171920] px-3 py-2 text-xs text-[#8c92a2]">
        <label htmlFor="run-file" className="sr-only">
          File to run
        </label>
        <select
          id="run-file"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          className="h-8 max-w-[220px] rounded-md border border-line-strong bg-panel px-2 font-mono text-xs text-fg"
        >
          {programs.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <button className="btn btn-primary btn-sm" onClick={run} disabled={busy || !path} title="Run (Ctrl+Enter)">
          {busy ? <Loader2 className="animate-spin" /> : <Play />} {busy ? "Running…" : "Run"}
        </button>
        <span className="hidden sm:inline">Ctrl+Enter</span>
        <button className="btn btn-quiet btn-sm ml-auto" onClick={() => setSessions([])} disabled={!sessions.length || busy} title="Clear the output">
          <Trash2 /> Clear
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* input */}
        <div className="flex shrink-0 flex-col gap-1.5 border-b border-[#252834] bg-[#121317] p-3 md:w-64 md:border-r md:border-b-0">
          <label htmlFor="run-stdin" className="text-xs font-medium text-fg">
            Input <span className="font-normal text-muted">(optional)</span>
          </label>
          <p className="text-[11.5px] leading-snug text-muted">
            {prompts > 0
              ? `This program asks you something about ${prompts} time${prompts > 1 ? "s" : ""}. Type one answer per line before you press Run.`
              : "If the program asks you questions, type the answers here, one per line."}
          </p>
          <textarea
            id="run-stdin"
            value={stdin}
            onChange={(e) => setStdin(e.target.value)}
            rows={4}
            spellCheck={false}
            placeholder={prompts > 0 ? "first answer\nsecond answer" : ""}
            className={clsx(
              "min-h-[72px] flex-1 resize-none rounded-lg border bg-panel-2 px-2.5 py-2 font-mono text-xs text-fg outline-none transition-[border-color,box-shadow] duration-200 focus:border-accent-strong focus:shadow-[0_0_0_3px_#7c66dc22]",
              prompts > 0 && !stdin.trim() ? "border-warn/50" : "border-line-strong",
            )}
          />
        </div>

        {/* output */}
        <div ref={screen} className="terminal scroll-thin min-h-[180px] flex-1 overflow-y-auto bg-[#0d0e11]" aria-live="polite">
          {sessions.length === 0 ? (
            <div className="grid h-full place-items-center text-center text-muted">
              <div>
                <TerminalSquare className="mx-auto mb-2 size-7 opacity-60" />
                <p>
                  Press <span className="text-fg">Run</span> to start <span className="font-mono text-fg">{path}</span>. What it prints shows up here.
                </p>
              </div>
            </div>
          ) : (
            sessions.map((s) => {
              const r = s.result;
              const hint = r ? explain(r, s.stdin) : null;
              return (
                <div key={s.id} className="mb-4 animate-[fade-in_.2s_ease-out]">
                  <div>
                    <span className="text-ok">$</span> <span className="text-white">{command(s.path)}</span>
                  </div>
                  {s.stdin.trim() && (
                    <div className="text-muted">
                      {s.stdin.replace(/\n$/, "").split("\n").map((line, i) => (
                        <div key={i}>&gt; {line}</div>
                      ))}
                    </div>
                  )}
                  {!r && !s.error && (
                    <div className="text-muted">
                      running<span className="caret">▊</span>
                    </div>
                  )}
                  {r && <pre className="m-0 whitespace-pre-wrap break-words font-[inherit]">{r.output}</pre>}
                  {r && (
                    <div className={clsx("mt-1 text-[11px]", r.exit_code === 0 && !r.timed_out ? "text-ok" : "text-bad")}>
                      {r.timed_out ? "■ stopped (took too long)" : r.exit_code === 0 ? "✓ finished" : `✗ exited with code ${r.exit_code}`} · {r.seconds}s
                    </div>
                  )}
                  {hint && <div className="mt-1.5 rounded-md border border-warn/30 bg-warn-soft px-2.5 py-1.5 font-sans text-[12px] text-fg-2">{hint}</div>}
                  {s.error && <div className="text-bad">{s.error}</div>}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- website preview

function Preview({ projectId, entry }: { projectId: string; entry: string }) {
  const [key, setKey] = useState(0);
  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[#0d0e11]">
      <div className="flex items-center gap-2 border-b border-[#252834] bg-[#171920] px-3 py-1.5 text-xs text-[#8c92a2]">
        <button onClick={() => setKey((k) => k + 1)} className="rounded p-1 hover:bg-[#252936] hover:text-white" title="Reload preview">
          <RefreshCw className="size-3.5" />
        </button>
        <div className="flex flex-1 items-center rounded border border-[#2b2f3d] bg-[#101217] px-2.5 py-1 font-mono text-[11px] text-[#c0c5d4]">
          <span className="truncate">preview://{projectId}/{entry}</span>
        </div>
        <a href={previewUrl(projectId, entry)} target="_blank" rel="noreferrer" className="rounded p-1 hover:bg-[#252936] hover:text-white" title="Open in new window">
          <ExternalLink className="size-3.5" />
        </a>
      </div>
      <iframe key={key} src={previewUrl(projectId, entry)} className="h-full w-full flex-1 border-0 bg-white" title="Sandboxed live preview" />
    </div>
  );
}

// ---------------------------------------------------------------- try it

/** Lets the user use what the crew built: a website opens in a live preview,
 *  a program runs in a terminal. Projects with both get a switch. */
export function TryIt({ projectId, files }: { projectId: string; files?: Record<string, string> }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.project(projectId),
    enabled: !files,
  });
  const source = files ?? data?.files;
  const entry = source ? htmlEntry(source) : undefined;
  const hasPrograms = source ? runnableFiles(source).length > 0 : false;
  const [mode, setMode] = useState<"site" | "run" | null>(null);
  const shown = mode ?? (entry ? "site" : "run");

  if (isLoading) return <div className="skeleton m-4 h-[50vh]" />;
  if (error) return <div className="p-6"><ErrorNote error={error} /></div>;
  if (!source || (!entry && !hasPrograms))
    return (
      <div className="grid h-full place-items-center p-8 text-center text-sm text-muted">
        This project has no web page or program to run here. Look at the Code tab, or download the zip.
      </div>
    );

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      {entry && hasPrograms && (
        <div className="border-b border-[#252834] bg-[#121317] px-3 py-1.5">
          <div className="seg" role="group" aria-label="How to try it">
            <button type="button" aria-pressed={shown === "site"} onClick={() => setMode("site")}>
              <Globe className="mr-1 inline size-3.5" /> Website
            </button>
            <button type="button" aria-pressed={shown === "run"} onClick={() => setMode("run")}>
              <TerminalSquare className="mr-1 inline size-3.5" /> Run program
            </button>
          </div>
        </div>
      )}
      {shown === "site" && entry ? <Preview projectId={projectId} entry={entry} /> : <Terminal projectId={projectId} files={source} />}
    </div>
  );
}

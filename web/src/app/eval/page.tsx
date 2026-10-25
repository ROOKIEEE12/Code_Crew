"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type EvalRow, type EvalSummaryMode } from "@/lib/api";
import { Card, Empty, ErrorNote, Page, PageHeader, Tabs } from "@/components/ui";

const MODES = [
  { id: "baseline", label: "Single-agent baseline", color: "bg-series-1" },
  { id: "codecrew", label: "CodeCrew (multi-agent)", color: "bg-series-2" },
] as const;

const pct = (x: number) => `${Math.round(x * 100)}%`;

function Tile({ label, values, format }: { label: string; values: Partial<Record<string, number>>; format: (n: number) => string }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-muted">{label}</div>
      <dl className="mt-2 space-y-1">
        {MODES.map((m) =>
          values[m.id] === undefined ? null : (
            <div key={m.id} className="flex items-center gap-2">
              <span className={`size-2.5 rounded-sm ${m.color}`} aria-hidden />
              <dt className="flex-1 truncate text-xs text-muted">{m.id === "baseline" ? "Baseline" : "CodeCrew"}</dt>
              <dd className="text-lg font-semibold tabular-nums">{format(values[m.id]!)}</dd>
            </div>
          ),
        )}
      </dl>
    </Card>
  );
}

function TaskChart({ rows }: { rows: EvalRow[] }) {
  const [hover, setHover] = useState<{ row: EvalRow; x: number; y: number } | null>(null);
  const tasks = [...new Set(rows.map((r) => r.task))];
  return (
    <div className="relative">
      <div className="mb-3 flex flex-wrap gap-4 text-xs text-muted" aria-label="Legend">
        {MODES.map((m) => (
          <span key={m.id} className="inline-flex items-center gap-1.5">
            <span className={`h-2 w-3 rounded-sm ${m.color}`} /> {m.label}
          </span>
        ))}
      </div>
      <div className="relative">
        {/* recessive gridlines at 0 / 50 / 100% */}
        <div className="pointer-events-none absolute inset-y-0 right-0 left-28 sm:left-36">
          {[0, 50, 100].map((g) => (
            <div key={g} className="absolute inset-y-0 border-l border-line" style={{ left: `${g}%` }}>
              <span className="absolute -bottom-5 -translate-x-1/2 text-[10px] text-muted">{g}%</span>
            </div>
          ))}
        </div>
        <ul className="space-y-3 pb-6">
          {tasks.map((task) => (
            <li key={task} className="flex items-center gap-2">
              <span className="w-26 shrink-0 truncate text-right font-mono text-xs text-muted sm:w-34">{task}</span>
              <div className="flex flex-1 flex-col gap-0.5">
                {MODES.map((m) => {
                  const row = rows.find((r) => r.task === task && r.mode === m.id);
                  if (!row) return null;
                  const frac = row.hidden_total ? row.hidden_passed / row.hidden_total : 0;
                  return (
                    <div
                      key={m.id}
                      className="relative h-2.5 cursor-default"
                      onMouseMove={(e) => setHover({ row, x: e.clientX, y: e.clientY })}
                      onMouseLeave={() => setHover(null)}
                    >
                      <div
                        className={`h-2 rounded-r-[4px] ${m.color} ${hover && hover.row !== row ? "opacity-60" : ""}`}
                        style={{ width: `max(${frac * 100}%, 2px)` }}
                      />
                    </div>
                  );
                })}
              </div>
            </li>
          ))}
        </ul>
      </div>
      {hover && (
        <div
          role="tooltip"
          className="pointer-events-none fixed z-50 rounded-md border border-line bg-panel px-3 py-2 text-xs shadow-lg"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          <div className="font-mono">{hover.row.task}</div>
          <div className="text-muted">{hover.row.mode === "baseline" ? "Baseline" : "CodeCrew"}</div>
          <div className="mt-1">
            Hidden tests: {hover.row.hidden_passed}/{hover.row.hidden_total} · {hover.row.solved ? "solved" : "not solved"}
          </div>
          <div className="text-muted">
            {hover.row.llm_calls} LLM calls · {hover.row.seconds}s{hover.row.debug_rounds ? ` · ${hover.row.debug_rounds} debug rounds` : ""}
          </div>
        </div>
      )}
    </div>
  );
}

function TaskTable({ rows }: { rows: EvalRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[13px]">
        <thead className="text-xs text-muted">
          <tr className="border-b border-line">
            {["Task", "Mode", "Solved", "Hidden tests", "Self-verified", "LLM calls", "Debug rounds", "Time"].map((h) => (
              <th key={h} className="px-2 py-2 font-medium whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.task}-${r.mode}`} className="border-b border-line">
              <td className="px-2 py-1.5 font-mono">{r.task}</td>
              <td className="px-2 py-1.5">{r.mode}</td>
              <td className={`px-2 py-1.5 ${r.solved ? "text-ok" : "text-bad"}`}>{r.solved ? "✓ yes" : "✗ no"}</td>
              <td className="px-2 py-1.5 tabular-nums">{r.hidden_passed}/{r.hidden_total}</td>
              <td className="px-2 py-1.5">{r.self_verified === null ? "n/a" : r.self_verified ? "yes" : "no"}</td>
              <td className="px-2 py-1.5 tabular-nums">{r.llm_calls}</td>
              <td className="px-2 py-1.5 tabular-nums">{r.debug_rounds}</td>
              <td className="px-2 py-1.5 tabular-nums">{r.seconds}s</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function EvalPage() {
  const list = useQuery({ queryKey: ["eval"], queryFn: api.evalResults });
  const [picked, setPicked] = useState<string | null>(null);
  const name = picked ?? list.data?.results[0]?.name ?? null;
  const detail = useQuery({ queryKey: ["eval", name], queryFn: () => api.evalResult(name!), enabled: !!name });
  const [view, setView] = useState<"chart" | "table">("chart");

  const s = detail.data?.summary ?? {};
  const pick = (k: keyof EvalSummaryMode) => Object.fromEntries(Object.entries(s).map(([m, v]) => [m, v[k] as number]));
  const cc = s.codecrew;

  return (
    <Page>
      <PageHeader
        title="Evaluation"
        description={
          <>
            Is a team of agents better than one AI on its own? Both solve the same tasks and are graded by hidden tests that neither one sees.
            Run <code className="font-mono text-xs text-fg">python -m eval.run</code> to add a result.
          </>
        }
      />
          <ErrorNote error={list.error ?? detail.error} />
          {list.data && !list.data.results.length && <Empty title="No results yet">Run the benchmark from the project folder, then refresh this page.</Empty>}

      {name && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
            <label htmlFor="result" className="text-muted">Result</label>
            <select id="result" value={name} onChange={(e) => setPicked(e.target.value)} className="rounded-lg border border-line-strong bg-panel px-2 py-1">
              {list.data?.results.map((r) => (
                <option key={r.name} value={r.name}>
                  {r.name} ({Object.values(r.summary)[0]?.tasks ?? 0} tasks)
                </option>
              ))}
            </select>
            {detail.data && <span className="text-xs text-muted">providers: {detail.data.providers.join(", ")}</span>}
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Tile label="Tasks fully solved" values={pick("solve_rate")} format={pct} />
            <Tile label="Hidden tests passed" values={pick("hidden_test_pass_rate")} format={pct} />
            <Tile label="Avg LLM calls per task" values={pick("avg_llm_calls")} format={(n) => n.toFixed(1)} />
            <Tile label="Avg time per task" values={pick("avg_seconds")} format={(n) => `${Math.round(n)}s`} />
          </div>

          {cc?.self_verified !== undefined && (
            <p className="mt-3 text-sm text-muted">
              Self-report accuracy: CodeCrew marked {cc.self_verified} task(s) as verified, and {cc.self_verified_and_solved} of those also passed every hidden test.
            </p>
          )}

          <Card className="mt-6">
            <Tabs value={view} onChange={setView} tabs={[{ id: "chart", label: "Hidden-test pass rate by task" }, { id: "table", label: "Table" }]} />
            <div className="p-4">
              {detail.data?.rows ? (view === "chart" ? <TaskChart rows={detail.data.rows} /> : <TaskTable rows={detail.data.rows} />) : <div className="h-40 animate-pulse" />}
            </div>
          </Card>
        </>
      )}
    </Page>
  );
}

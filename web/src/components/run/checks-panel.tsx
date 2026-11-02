"use client";

import clsx from "clsx";
import { CheckCircle2, ChevronRight, CircleSlash, RotateCcw, XCircle } from "lucide-react";
import { useState } from "react";
import type { DebugRound, Issue, TestCase, Verification } from "@/lib/api";
import type { Dispute } from "@/lib/use-run-stream";
import { Stat } from "../ui";

const SOURCE_LABEL: Record<Issue["source"], string> = {
  syntax: "Syntax",
  contract: "Cross-file contracts",
  spec: "Spec conformance",
  lint: "Lint",
  security: "Security",
  test: "Test suite",
  quality: "Web page quality",
  runtime: "In the browser",
};

function TestRow({ c }: { c: TestCase }) {
  const [open, setOpen] = useState(false);
  const failed = c.outcome === "failed" || c.outcome === "error";
  return (
    <li>
      <button
        onClick={() => failed && setOpen(!open)}
        className={clsx("flex w-full items-start gap-2 px-3 py-1.5 text-left text-[13px] transition-colors", failed && "hover:bg-panel-2")}
      >
        {c.outcome === "passed" ? (
          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-ok" />
        ) : c.outcome === "skipped" ? (
          <CircleSlash className="mt-0.5 size-3.5 shrink-0 text-muted" />
        ) : (
          <XCircle className="mt-0.5 size-3.5 shrink-0 text-bad" />
        )}
        <span className="min-w-0 flex-1 font-mono break-all">{c.name}</span>
        {failed && <ChevronRight className={clsx("mt-0.5 size-3.5 shrink-0 text-muted transition-transform", open && "rotate-90")} />}
      </button>
      {open && (
        <pre className="tab-panel scroll-thin mx-3 mb-2 max-h-64 overflow-auto rounded border border-line bg-panel-2 p-2 font-mono text-[11px] whitespace-pre-wrap text-muted">
          {[c.message, c.details].filter(Boolean).join("\n\n")}
        </pre>
      )}
    </li>
  );
}

export function ChecksPanel({
  verification,
  rounds,
  disputes,
}: {
  verification?: Verification & { round?: number };
  rounds: DebugRound[];
  disputes: Dispute[];
}) {
  if (!verification) return <p className="p-6 text-sm text-muted">Test results appear here once the code is written and the Verifier has run it.</p>;
  const cases = verification.test_runs.flatMap((r) => r.cases);
  const byFile = new Map<string, TestCase[]>();
  for (const c of cases) byFile.set(c.file, [...(byFile.get(c.file) ?? []), c]);
  const nonTest = verification.issues.filter((i) => i.source !== "test" || !i.test_id);
  const bySource = new Map<string, Issue[]>();
  for (const i of nonTest) bySource.set(i.source, [...(bySource.get(i.source) ?? []), i]);
  const errors = verification.issues.filter((i) => i.severity === "error").length;
  const unchecked = Object.entries(verification.syntax).filter(([, c]) => c.status === "unchecked");

  return (
    <div className="space-y-5 p-4 sm:p-6">
      <div className="grid grid-cols-3 gap-3">
        <Stat
          label="Tests passed"
          value={verification.tests_total ? `${verification.tests_passed}/${verification.tests_total}` : "none"}
          tone={verification.tests_total ? (verification.tests_passed === verification.tests_total ? "ok" : "bad") : undefined}
        />
        <Stat label="Problems found" value={errors} tone={errors ? "bad" : "ok"} />
        <Stat label="How it was checked" value={verification.level === "tested" ? "Tests ran" : "Code checks only"} tone={verification.level === "tested" ? undefined : "warn"} />
      </div>
      {verification.level === "static_only" && (
        <p className="rounded-md bg-warn-soft px-3 py-2 text-xs text-warn">
          This project has no runnable tests, so it was checked by reading the code: syntax, links between files and code quality.
        </p>
      )}

      {[...byFile.entries()].map(([file, list]) => (
        <section key={file}>
          <h3 className="mb-1 font-mono text-xs text-muted">{file}</h3>
          <ul className="stagger rounded-lg border border-line bg-panel">{list.map((c) => <TestRow key={c.id} c={c} />)}</ul>
        </section>
      ))}

      {[...bySource.entries()].map(([source, list]) => (
        <section key={source}>
          <h3 className="mb-1 text-xs font-medium text-muted">{SOURCE_LABEL[source as Issue["source"]]}</h3>
          <ul className="space-y-1">
            {list.map((i, k) => (
              <li key={k} className={clsx("rounded-md border px-3 py-2 text-[13px]", i.severity === "error" ? "border-bad/40 bg-bad-soft" : "border-line")}>
                <div className="font-mono text-[11px] text-muted">
                  {i.file ?? "project"}
                  {i.line ? `:${i.line}` : ""}
                </div>
                <div className="break-words whitespace-pre-wrap">{i.message.split("\n").slice(0, 6).join("\n")}</div>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {unchecked.length > 0 && (
        <p className="text-xs text-muted">Could not be checked automatically: {unchecked.map(([p]) => p).join(", ")}</p>
      )}

      {rounds.length > 0 && (
        <section>
          <h3 className="mb-1 text-xs font-medium text-muted">Fix attempts by the Debugger</h3>
          <ol className="space-y-1">
            {rounds.map((r) => (
              <li key={r.round} className="flex items-start gap-2 rounded-md border border-line px-3 py-2 text-[13px]">
                {r.kept ? <CheckCircle2 className="mt-0.5 size-3.5 text-ok" /> : <RotateCcw className="mt-0.5 size-3.5 text-warn" />}
                <div className="min-w-0">
                  <div>
                    Attempt {r.round}: {r.changed_files.length ? `changed ${r.changed_files.join(", ")}` : "no code changes"}
                  </div>
                  <div className="text-xs text-muted">
                    {r.score_after === null || r.score_after === undefined ? "verifying…" : r.kept ? "Kept: results improved or stayed the same" : "Undone: this attempt made results worse"}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {disputes.length > 0 && (
        <section>
          <h3 className="mb-1 text-xs font-medium text-muted">Tests the Debugger disagreed with</h3>
          <ul className="space-y-1">
            {disputes.map((d, k) => (
              <li key={k} className="rounded-md border border-line px-3 py-2 text-[13px]">
                <div className="font-mono text-[11px] text-muted">{d.test_id}</div>
                <div className={d.upheld ? "text-warn" : "text-muted"}>{d.upheld ? "The test was wrong and has been fixed to match the plan" : "The test was correct, so it stayed"}</div>
                {d.explanation && <div className="mt-1 text-xs text-muted">{d.explanation}</div>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

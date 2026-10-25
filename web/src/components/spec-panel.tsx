import type { Spec } from "@/lib/api";

const VERIFY_LABEL = { automated_test: "test", static_check: "static", manual: "manual" } as const;

export function SpecPanel({ spec }: { spec: Spec | null }) {
  if (!spec) return <p className="p-4 text-sm text-muted">The Planner has not written the plan yet. It is the first step of every build.</p>;
  return (
    <div className="space-y-5 p-4 text-[13px] sm:p-6">
      <section>
        <div className="flex items-baseline gap-2">
          <h3 className="font-semibold">{spec.project_name}</h3>
          <span className="text-xs text-muted">{spec.project_type}</span>
        </div>
        <p className="mt-1 text-muted">{spec.summary}</p>
        <p className="mt-2">
          <span className="text-xs text-muted">How to run it: </span>
          <code className="font-mono text-xs">{spec.run_instructions}</code>
        </p>
      </section>

      <section>
        <h3 className="mb-1 text-xs font-medium text-muted">What counts as done (acceptance criteria)</h3>
        <ul className="space-y-1">
          {spec.acceptance_criteria.map((ac) => (
            <li key={ac.id} className="flex gap-2">
              <span className="w-9 shrink-0 font-mono text-xs text-accent">{ac.id}</span>
              <span className="min-w-0 flex-1">{ac.description}</span>
              <span className="shrink-0 rounded bg-panel-2 px-1.5 text-[10px] text-muted">{VERIFY_LABEL[ac.verification]}</span>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="mb-1 text-xs font-medium text-muted">Files the plan asks for</h3>
        <ul className="space-y-3">
          {spec.files.map((f) => (
            <li key={f.path} className="rounded-lg border border-line bg-panel p-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs">{f.path}</span>
                {f.testable && <span className="rounded bg-accent-soft px-1.5 text-[10px] text-accent">testable</span>}
              </div>
              <p className="mt-1 text-muted">{f.purpose}</p>
              {f.functions.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {f.functions.map((fn) => (
                    <li key={fn.name}>
                      <code className="font-mono text-xs break-all">{fn.signature}</code>
                      {fn.edge_cases.length > 0 && <div className="text-xs text-muted">Edge cases: {fn.edge_cases.join("; ")}</div>}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </section>

      {spec.assumptions.length > 0 && (
        <section>
          <h3 className="mb-1 text-xs font-medium text-muted">Assumptions the Planner made</h3>
          <ul className="list-disc space-y-1 pl-4 text-muted">
            {spec.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

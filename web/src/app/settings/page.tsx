"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed } from "lucide-react";
import { api } from "@/lib/api";
import { Card, ErrorNote, Page, PageHeader, SectionTitle } from "@/components/ui";

export default function SettingsPage() {
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers, refetchInterval: 10_000 });
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.agents });
  const health = Object.entries(providers.data?.health ?? {});

  return (
    <Page width="max-w-4xl">
      <PageHeader
        title="Settings"
        description={
          <>
            Which AI services CodeCrew can use, and how they are doing. Keys live in the backend&apos;s{" "}
            <code className="font-mono text-xs text-fg">.env</code> file. Claude (<code className="font-mono text-xs text-fg">ANTHROPIC_API_KEY</code>)
            is the most accurate and fastest. Free OpenRouter and Gemini keys are tried next.
          </>
        }
      />
        <div className="space-y-8">
          <ErrorNote error={providers.error ?? agents.error} />

          <section>
            <SectionTitle>AI services, in the order they are tried</SectionTitle>
            <div className="stagger grid gap-3 sm:grid-cols-3">
              {(providers.data?.order ?? []).map((name, i) => {
                const p = providers.data!.providers[name];
                return (
                  <Card key={name} className="p-4">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[#717787]">{i + 1}.</span>
                      <span className="font-medium text-white capitalize">{name}</span>
                      {p?.configured ? (
                        <CheckCircle2 className="ml-auto size-4 text-[#8bd49d]" aria-label="configured" />
                      ) : (
                        <CircleDashed className="ml-auto size-4 text-[#717787]" aria-label="not configured" />
                      )}
                    </div>
                    <p className="mt-1.5 text-xs text-[#8c92a2]">{p?.configured ? p.models.join(", ") : "Not set up: no API key"}</p>
                  </Card>
                );
              })}
            </div>
          </section>

          <section>
            <SectionTitle>Model health since the backend started</SectionTitle>
            {health.length ? (
              <Card className="overflow-x-auto">
                <table className="w-full text-left text-[13px]">
                  <thead className="text-xs text-[#717787]">
                    <tr className="border-b border-[#252834]">
                      {["Model", "Successes", "Failures", "Cooldown", "Last error"].map((h) => (
                        <th key={h} className="px-3 py-2 font-medium">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {health.map(([model, h]) => (
                      <tr key={model} className="border-b border-[#252834] last:border-0">
                        <td className="px-3 py-2 font-mono text-xs text-white">{model}</td>
                        <td className="px-3 py-2 tabular-nums text-[#8bd49d]">{h.successes}</td>
                        <td className="px-3 py-2 tabular-nums text-[#f87171]">{h.failures}</td>
                        <td className="px-3 py-2 text-[#e8ae79]">{h.cooldown_remaining_sec ? `${Math.round(h.cooldown_remaining_sec)}s` : "none"}</td>
                        <td className="max-w-xs truncate px-3 py-2 text-xs text-[#8c92a2]" title={h.last_error ?? ""}>{h.last_error ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            ) : (
              <Card className="p-4 text-xs text-[#8c92a2]">No LLM calls made yet in this server session.</Card>
            )}
          </section>

          <section>
            <SectionTitle>The crew</SectionTitle>
            <ul className="stagger space-y-2">
              {(agents.data?.agents ?? []).map((a) => (
                <li key={a.id}>
                  <Card className="p-3">
                    <span className="font-medium text-white">{a.name}</span>
                    <p className="mt-1 text-xs text-[#8c92a2]">{a.role}</p>
                  </Card>
                </li>
              ))}
            </ul>
            {agents.data?.graph && (
              <details className="mt-4">
                <summary className="cursor-pointer text-xs text-[#8c92a2] hover:text-white">Orchestration graph (Mermaid)</summary>
                <pre className="scroll-thin mt-2 overflow-x-auto rounded-md border border-[#252834] bg-[#121419] p-3 font-mono text-xs text-[#ccd0de]">{agents.data.graph}</pre>
              </details>
            )}
          </section>
        </div>
    </Page>
  );
}

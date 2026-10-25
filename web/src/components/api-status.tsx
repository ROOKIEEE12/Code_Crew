"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function ApiStatus() {
  const { data, isError } = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15_000 });
  const ok = !!data && !isError;
  const providers = data?.providers_configured ?? [];
  return (
    <div className="rounded-md border border-line px-2.5 py-2 text-xs text-muted">
      <div className="flex items-center gap-1.5">
        <span className={`size-1.5 rounded-full ${ok ? "bg-ok" : "bg-bad"}`} />
        {ok ? `API v${data.version}` : "API offline"}
      </div>
      {ok && (
        <div className="mt-1 truncate" title={providers.join(", ")}>
          {providers.length ? `LLM: ${providers.join(", ")}` : "No LLM key configured"}
        </div>
      )}
    </div>
  );
}

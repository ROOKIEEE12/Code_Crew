import { Suspense } from "react";
import { RunView } from "@/components/run/run-view";

export default function RunPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted">Loading run…</div>}>
      <RunView />
    </Suspense>
  );
}

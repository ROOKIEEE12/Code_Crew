import { Suspense } from "react";
import { ProjectView } from "@/components/project-view";

export default function ProjectPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted">Loading project…</div>}>
      <ProjectView />
    </Suspense>
  );
}

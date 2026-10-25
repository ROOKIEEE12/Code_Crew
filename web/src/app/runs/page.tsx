import { Plus } from "lucide-react";
import Link from "next/link";
import { RunList } from "@/components/run-list";
import { Page, PageHeader } from "@/components/ui";

export default function RunsPage() {
  return (
    <Page width="max-w-4xl">
      <PageHeader
        title="Runs"
        description="Every build and every change you asked for. Open one to replay exactly what each agent did, step by step."
        actions={
          <Link href="/" className="btn btn-primary">
            <Plus /> New build
          </Link>
        }
      />
      <RunList />
    </Page>
  );
}

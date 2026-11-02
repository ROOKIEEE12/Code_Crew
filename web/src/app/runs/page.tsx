import { Plus } from "lucide-react";
import Link from "next/link";
import { RunList } from "@/components/run-list";
import { Page, PageHeader } from "@/components/ui";

export default function RunsPage() {
  return (
    <Page width="max-w-4xl">
      <PageHeader
        title="Runs"
        description="Each session is one project: the build and every change you asked for afterwards, like a chat. Open one to continue it or replay what each agent did."
        actions={
          <Link href="/" className="btn btn-primary">
            <Plus /> New build
          </Link>
        }
      />
      <RunList sessions />
    </Page>
  );
}

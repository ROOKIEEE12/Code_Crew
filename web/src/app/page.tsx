import { ChevronDown, MessageSquareText, MonitorPlay, PackageCheck } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";
import { NewRunForm } from "@/components/new-run-form";
import { RunList } from "@/components/run-list";
import { BUILD_STEPS, STEP } from "@/lib/crew";

const HOW = [
  { icon: MessageSquareText, title: "You describe it", body: "Plain English is fine. Be specific about what it should do." },
  { icon: MonitorPlay, title: "The crew builds it", body: "AI specialists plan, test, code and fix. You watch each step live." },
  { icon: PackageCheck, title: "You get working code", body: "Tests really run. Read, preview, download or ask for changes." },
];

export default function Home() {
  return (
    <div className="scroll-thin relative h-full overflow-x-hidden overflow-y-auto">
      <div className="glow -top-40 left-1/2 size-[520px] -translate-x-1/2 bg-[#6b58e6]/15" aria-hidden />
      <div className="glow top-40 -right-40 size-[360px] bg-[#4b73d7]/10" aria-hidden />

      <div className="relative mx-auto max-w-3xl px-4 pt-14 pb-16 sm:px-8 md:pt-20">
        <section className="stagger text-center">
          <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-line-strong bg-panel/70 px-3 py-1 text-xs text-fg-2">
            <span className="dot" /> A team of AI agents that tests its own work
          </div>
          <h1 className="mt-5 text-3xl font-semibold tracking-tight text-white md:text-4xl">What do you want to build?</h1>
          <p className="mx-auto mt-3 max-w-xl text-[15px] leading-relaxed text-fg-2">
            Describe it below. CodeCrew plans it, writes tests, writes the code and keeps fixing it until the tests really pass.
          </p>
        </section>

        <section className="mt-8 animate-[rise-in_.5s_.15s_cubic-bezier(.22,1,.36,1)_both]">
          <Suspense fallback={<div className="skeleton h-36" />}>
            <NewRunForm />
          </Suspense>
        </section>

        <section className="mt-14">
          <h2 className="mb-4 text-center text-xs font-semibold tracking-widest text-muted uppercase">How it works</h2>
          <ol className="stagger grid gap-3 sm:grid-cols-3">
            {HOW.map((h, i) => {
              const Icon = h.icon;
              return (
                <li key={h.title} className="card-hover rounded-xl border border-line bg-panel p-4">
                  <div className="flex items-center gap-2.5">
                    <span className="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent">
                      <Icon className="size-4" />
                    </span>
                    <span className="text-[11px] font-semibold text-muted">STEP {i + 1}</span>
                  </div>
                  <h3 className="mt-3 text-sm font-semibold text-white">{h.title}</h3>
                  <p className="mt-1 text-[13px] leading-relaxed text-muted">{h.body}</p>
                </li>
              );
            })}
          </ol>

          <details className="group mt-3 rounded-xl border border-line bg-panel/60 open:bg-panel">
            <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-[13px] text-fg-2 select-none hover:text-white">
              <span>Meet the crew: the six specialists and what each one does</span>
              <ChevronDown className="size-4 transition-transform duration-300 group-open:rotate-180" />
            </summary>
            <ol className="stagger grid gap-2 px-4 pb-4 sm:grid-cols-2">
              {BUILD_STEPS.map((id, i) => {
                const s = STEP[id];
                const Icon = s.icon;
                return (
                  <li key={id} className="flex gap-3 rounded-lg border border-line bg-panel-2/50 p-3">
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg" style={{ background: `${s.tone}22`, color: s.tone }}>
                      <Icon className="size-4" />
                    </span>
                    <div>
                      <div className="text-[13px] font-medium text-fg">
                        {i + 1}. {s.label} <span className="font-normal text-muted">· {s.agent}</span>
                      </div>
                      <p className="mt-0.5 text-xs leading-relaxed text-muted">{s.plain}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </details>
        </section>

        <section className="mt-14">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Your recent runs</h2>
            <Link href="/runs" className="text-xs text-muted transition-colors hover:text-white">
              See all →
            </Link>
          </div>
          <RunList limit={5} />
        </section>
      </div>
    </div>
  );
}

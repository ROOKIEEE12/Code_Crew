"use client";

import { ArrowRight, MessageSquareText, MonitorPlay, PackageCheck, X } from "lucide-react";
import { useState } from "react";
import { BUILD_STEPS, STEP } from "@/lib/crew";

const PAGES = [
  {
    icon: MessageSquareText,
    title: "1. Describe what you want",
    body: "Write your idea in plain English, like you would explain it to a friend. Mention file names, inputs and outputs if you know them. The more specific you are, the better the result.",
  },
  {
    icon: MonitorPlay,
    title: "2. Watch the crew work",
    body: "Six AI specialists take turns: plan, write tests, write code, check, fix and document. You see each step live. A build takes a few minutes, and you can leave the page and come back.",
  },
  {
    icon: PackageCheck,
    title: "3. Get code that really works",
    body: "Tests are actually run, so 'Verified' means it passed. Open the project to read the code, preview web pages, download a zip, or ask for changes.",
  },
];

const TERMS = [
  ["Spec / Plan", "The Planner's blueprint: files, functions and what counts as done."],
  ["Locked tests", "Tests written before the code. The Coder can't change them to hide bugs."],
  ["Verified", "Every real test and check passed."],
  ["Fix round", "One attempt by the Debugger. Bad attempts are undone automatically."],
];

export function Guide({ onClose }: { onClose: () => void }) {
  const [page, setPage] = useState(0);
  const last = page === PAGES.length;

  return (
    <div className="overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="How CodeCrew works">
      <div className="dialog max-w-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <div>
            <div className="text-[11px] font-semibold tracking-wider text-accent uppercase">Quick guide</div>
            <div className="text-[15px] font-semibold text-white">How CodeCrew works</div>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close guide">
            <X />
          </button>
        </div>

        <div className="scroll-thin min-h-[260px] overflow-y-auto px-5 py-5">
          {!last ? (
            <div key={page} className="tab-panel">
              {(() => {
                const P = PAGES[page];
                const Icon = P.icon;
                return (
                  <>
                    <div className="mb-4 grid size-12 place-items-center rounded-2xl bg-accent-soft text-accent">
                      <Icon className="size-6" />
                    </div>
                    <h3 className="text-lg font-semibold text-white">{P.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-fg-2">{P.body}</p>
                    {page === 1 && (
                      <ol className="stagger mt-5 grid grid-cols-2 gap-2 sm:grid-cols-3">
                        {BUILD_STEPS.map((id) => {
                          const s = STEP[id];
                          const Icon = s.icon;
                          return (
                            <li key={id} className="rounded-lg border border-line bg-panel-2/60 p-2.5" style={{ ["--tone" as string]: s.tone }}>
                              <div className="flex items-center gap-2 text-[12.5px] font-medium text-fg">
                                <Icon className="size-4" style={{ color: s.tone }} /> {s.label}
                              </div>
                              <div className="mt-0.5 text-[11px] text-muted">{s.agent}</div>
                            </li>
                          );
                        })}
                      </ol>
                    )}
                  </>
                );
              })()}
            </div>
          ) : (
            <div className="tab-panel">
              <h3 className="text-lg font-semibold text-white">Words you will see</h3>
              <dl className="stagger mt-4 space-y-3">
                {TERMS.map(([term, def]) => (
                  <div key={term} className="rounded-lg border border-line bg-panel-2/60 px-3 py-2.5">
                    <dt className="text-sm font-medium text-fg">{term}</dt>
                    <dd className="mt-0.5 text-[13px] text-muted">{def}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-4 text-[13px] text-muted">
                Tip: press <kbd>Ctrl</kbd> <kbd>K</kbd> anywhere to search, and <kbd>?</kbd> to open this guide again.
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-line px-5 py-3">
          <div className="flex gap-1.5" aria-label={`Page ${page + 1} of ${PAGES.length + 1}`}>
            {[...PAGES, null].map((_, i) => (
              <button
                key={i}
                onClick={() => setPage(i)}
                aria-label={`Go to page ${i + 1}`}
                className="h-1.5 rounded-full transition-all duration-300"
                style={{ width: i === page ? 22 : 8, background: i === page ? "var(--accent)" : "var(--line-strong)" }}
              />
            ))}
          </div>
          <div className="flex gap-2">
            {page > 0 && (
              <button className="btn btn-quiet btn-sm" onClick={() => setPage(page - 1)}>
                Back
              </button>
            )}
            {last ? (
              <button className="btn btn-primary btn-sm" onClick={onClose}>
                Start building
              </button>
            ) : (
              <button className="btn btn-primary btn-sm" onClick={() => setPage(page + 1)}>
                Next <ArrowRight />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

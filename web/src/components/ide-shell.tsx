"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Boxes,
  CircleHelp,
  FlaskConical,
  Folder,
  History,
  Home,
  Lightbulb,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Search,
  Send,
  Settings as SettingsIcon,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { EXAMPLES } from "@/lib/crew";
import { usePref } from "@/lib/prefs";
import { Guide } from "./guide";

const NAV = [
  { href: "/", label: "Home", icon: Home, match: (p: string) => p === "/" },
  { href: "/runs", label: "Runs", icon: History, match: (p: string) => p.startsWith("/runs") },
  { href: "/projects", label: "Projects", icon: Boxes, match: (p: string) => p.startsWith("/projects") },
  { href: "/eval", label: "Evaluation", icon: FlaskConical, match: (p: string) => p.startsWith("/eval") },
  { href: "/settings", label: "Settings", icon: SettingsIcon, match: (p: string) => p.startsWith("/settings") },
];

function isTyping(e: KeyboardEvent) {
  const t = e.target as HTMLElement | null;
  return !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
}

function IdeShellInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const search = useSearchParams()?.toString() ?? "";

  const [collapsedPref, setCollapsedPref] = usePref("sidebar-collapsed", "0");
  const [assistantPref, setAssistantPref] = usePref("assistant-open", "0");
  const [guideSeen, setGuideSeen] = usePref("guide-seen", "0", "1");
  const [guideOpen, setGuideOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const collapsed = collapsedPref === "1";
  const assistantOpen = assistantPref === "1";
  const showGuide = guideOpen || guideSeen !== "1";

  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 12_000 });
  const runs = useQuery({ queryKey: ["recent-runs"], queryFn: () => api.runs(), refetchInterval: 6_000 });
  const projects = useQuery({ queryKey: ["recent-projects"], queryFn: api.projects, refetchInterval: 15_000 });

  const online = !!health.data && !health.isError;
  const providers = health.data?.providers_configured ?? [];
  const allRuns = runs.data?.runs ?? [];
  const active = allRuns.filter((r) => r.status === "running" || r.status === "queued");
  const recentRuns = allRuns.slice(0, 5);
  const recentProjects = (projects.data?.projects ?? []).slice(0, 5);

  function toggleSidebar() {
    if (window.matchMedia("(max-width: 767px)").matches) setMobileOpen((v) => !v);
    else setCollapsedPref(collapsed ? "0" : "1");
  }

  function closeGuide() {
    setGuideOpen(false);
    setGuideSeen("1");
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      } else if (mod && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleSidebar();
      } else if (e.key === "?" && !isTyping(e)) {
        setGuideOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="app">
      <header className="topbar">
        <Link href="/" className="brand" aria-label="CodeCrew home">
          <span className="brand-glyph" aria-hidden>CC</span>
          <span className="hidden sm:inline">CodeCrew</span>
        </Link>

        <button className="search-pill" onClick={() => setPaletteOpen(true)}>
          <Search className="size-3.5 shrink-0" />
          <span className="flex-1 truncate text-left">Search or jump to…</span>
          <kbd className="hidden sm:inline">Ctrl K</kbd>
        </button>

        <div className="flex items-center gap-1.5">
          <span
            className="status-pill hidden md:inline-flex"
            title={online ? `Using: ${providers.join(", ") || "no AI key set"}` : "Start the backend with: python scripts/dev.py"}
          >
            <span className={clsx("dot", !online && "off")} />
            {online ? (providers.length ? "Ready" : "No AI key set") : "Engine offline"}
          </span>
          <button className="icon-btn" onClick={() => setGuideOpen(true)} title="How it works (?)" aria-label="How it works">
            <CircleHelp />
          </button>
          <button
            className={clsx("btn btn-sm", assistantOpen ? "btn-ghost" : "btn-quiet")}
            onClick={() => setAssistantPref(assistantOpen ? "0" : "1")}
            aria-pressed={assistantOpen}
          >
            <Sparkles className="text-accent" />
            <span className="hidden sm:inline">Ask the crew</span>
          </button>
        </div>
      </header>

      <div className="workspace">
        <aside
          className={clsx("sidebar", collapsed && "collapsed", mobileOpen && "mobile-open")}
          aria-label="Navigation"
          onClick={(e) => {
            if ((e.target as HTMLElement).closest("a")) setMobileOpen(false);
          }}
        >
          <Link href="/" className="new-build pressable" data-tip="New build">
            <Plus />
            <span className="label">New build</span>
          </Link>

          <nav className="nav">
            {NAV.map((n) => {
              const Icon = n.icon;
              const on = n.match(pathname);
              return (
                <Link key={n.href} href={n.href} className={clsx("nav-item", on && "active")} data-tip={n.label} aria-current={on ? "page" : undefined}>
                  <Icon />
                  <span className="label">{n.label}</span>
                  {n.href === "/runs" && active.length > 0 && (
                    <span className="nav-badge" title={`${active.length} running`}>
                      <span className="badge-text">{active.length} running</span>
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>

          <div className="side-scroll scroll-thin">
            <div className="side-section">
              <span>Recent runs</span>
              {allRuns.length > 5 && <Link href="/runs">See all</Link>}
            </div>
            <div className="side-list">
              {recentRuns.length === 0 ? (
                <span className="side-empty">Nothing yet</span>
              ) : (
                recentRuns.map((r) => (
                  <Link key={r.id} href={`/runs/${r.id}`} className={clsx("side-row", pathname === `/runs/${r.id}` && "active")} title={r.requirement}>
                    <span className={clsx("status-dot", r.status)} />
                    <span>{r.requirement}</span>
                  </Link>
                ))
              )}
            </div>

            <div className="side-section">
              <span>Projects</span>
              {(projects.data?.projects.length ?? 0) > 5 && <Link href="/projects">See all</Link>}
            </div>
            <div className="side-list">
              {recentProjects.length === 0 ? (
                <span className="side-empty">Finished builds appear here</span>
              ) : (
                recentProjects.map((p) => (
                  <Link key={p.id} href={`/projects/${p.id}`} className={clsx("side-row", pathname === `/projects/${p.id}` && "active")} title={p.name}>
                    <Folder className="size-3.5 shrink-0 text-[#72a9ee]" />
                    <span>{p.name}</span>
                  </Link>
                ))
              )}
            </div>
          </div>

          <div className="side-foot">
            <button className="nav-item" onClick={toggleSidebar} data-tip="Expand sidebar (Ctrl B)">
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
              <span className="label">{collapsed ? "Expand sidebar" : "Collapse sidebar"}</span>
            </button>
          </div>
        </aside>

        <main className="main">
          <div key={`${pathname}?${search}`} className="page-enter h-full min-h-0">
            {children}
          </div>
        </main>

        {assistantOpen && <Assistant pathname={pathname} onClose={() => setAssistantPref("0")} />}
      </div>

      <footer className="statusbar">
        <div>
          <span className="flex items-center gap-1.5">
            <span className={clsx("dot", !online && "off")} style={{ width: 6, height: 6 }} />
            {online ? `Engine online${providers.length ? ` · ${providers.join(", ")}` : ""}` : "Engine offline: run python scripts/dev.py"}
          </span>
          {active.length > 0 && <span className="text-accent">{active.length} build{active.length > 1 ? "s" : ""} running</span>}
        </div>
        <div className="hidden sm:flex">
          <span><kbd>Ctrl K</kbd> search</span>
          <span><kbd>Ctrl B</kbd> sidebar</span>
          <span><kbd>?</kbd> help</span>
        </div>
      </footer>

      {paletteOpen && <Palette onClose={() => setPaletteOpen(false)} onGuide={() => setGuideOpen(true)} />}
      {showGuide && <Guide onClose={closeGuide} />}
    </div>
  );
}

// ---------------------------------------------------------------- command palette

interface PaletteItem {
  group: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  run: () => void;
}

function Palette({ onClose, onGuide }: { onClose: () => void; onGuide: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const runs = useQuery({ queryKey: ["recent-runs"], queryFn: () => api.runs() });
  const projects = useQuery({ queryKey: ["recent-projects"], queryFn: api.projects });

  const items = useMemo<PaletteItem[]>(() => {
    const go = (href: string) => () => router.push(href);
    const needle = q.trim().toLowerCase();
    const has = (s: string) => !needle || s.toLowerCase().includes(needle);
    const out: PaletteItem[] = [];
    if (needle.length >= 3) {
      out.push({ group: "Build", label: `Build: "${q.trim()}"`, icon: Sparkles, run: go(`/?prompt=${encodeURIComponent(q.trim())}`) });
    }
    for (const n of NAV) if (has(n.label)) out.push({ group: "Go to", label: n.label, icon: n.icon, run: go(n.href) });
    if (has("how it works help guide")) out.push({ group: "Go to", label: "How it works (guide)", icon: CircleHelp, run: onGuide });
    for (const p of (projects.data?.projects ?? []).filter((p) => has(p.name)).slice(0, 5))
      out.push({ group: "Projects", label: p.name, icon: Folder, run: go(`/projects/${p.id}`) });
    for (const r of (runs.data?.runs ?? []).filter((r) => has(r.requirement)).slice(0, 5))
      out.push({ group: "Runs", label: r.requirement, icon: History, run: go(`/runs/${r.id}`) });
    return out;
  }, [q, runs.data, projects.data, router, onGuide]);

  const index = Math.min(sel, Math.max(items.length - 1, 0));

  useEffect(() => {
    listRef.current?.querySelector(`[data-i="${index}"]`)?.scrollIntoView({ block: "nearest" });
  }, [index]);

  function choose(i: number) {
    const item = items[i];
    if (!item) return;
    onClose();
    item.run();
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog max-w-xl" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Search">
        <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
          <Search className="size-4 text-muted" />
          <input
            autoFocus
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setSel(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setSel(Math.min(index + 1, items.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setSel(Math.max(index - 1, 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                choose(index);
              } else if (e.key === "Escape") {
                onClose();
              }
            }}
            placeholder="Search pages, projects and runs, or type an idea to build"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted"
          />
          <kbd>Esc</kbd>
        </div>
        <div ref={listRef} className="scroll-thin max-h-[22rem] overflow-y-auto p-2">
          {items.length === 0 && <p className="px-3 py-6 text-center text-sm text-muted">No matches.</p>}
          {items.map((it, i) => {
            const Icon = it.icon;
            const header = i === 0 || items[i - 1].group !== it.group;
            return (
              <div key={`${it.group}-${i}`}>
                {header && <div className="palette-group">{it.group}</div>}
                <button data-i={i} className={clsx("palette-item", i === index && "sel")} onMouseMove={() => setSel(i)} onClick={() => choose(i)}>
                  <Icon className="text-muted" />
                  <span className="truncate">{it.label}</span>
                </button>
              </div>
            );
          })}
        </div>
        <div className="flex gap-4 border-t border-line px-4 py-2 text-[11px] text-muted">
          <span><kbd>↑</kbd> <kbd>↓</kbd> move</span>
          <span><kbd>Enter</kbd> open</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- assistant drawer

function Assistant({ pathname, onClose }: { pathname: string; onClose: () => void }) {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<{ role: "user" | "bot"; text: string }[]>([]);
  const projectId = pathname.match(/^\/projects\/([^/]+)/)?.[1];

  async function submit() {
    const text = input.trim();
    if (text.length < 3 || busy) return;
    setBusy(true);
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    try {
      const run = projectId ? await api.iterate(projectId, text) : await api.createRun(text);
      setMessages((m) => [...m, { role: "bot", text: projectId ? "Change request sent. Opening the live view…" : "Build started. Opening the live view…" }]);
      router.push(`/runs/${run.id}`);
    } catch (e) {
      setMessages((m) => [...m, { role: "bot", text: `Couldn't start: ${e instanceof Error ? e.message : String(e)}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="drawer" aria-label="Ask the crew">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="flex items-center gap-2.5">
          <div className="grid size-8 place-items-center rounded-xl bg-gradient-to-br from-[#8370df] to-[#c18cec] text-white">
            <Sparkles className="size-4" />
          </div>
          <div>
            <div className="text-[13px] font-semibold text-white">Ask the crew</div>
            <div className="text-[11px] text-muted">{projectId ? "Changes go to this project" : "Starts a new build"}</div>
          </div>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          <X />
        </button>
      </div>

      <div className="scroll-thin flex flex-1 flex-col gap-3 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="my-auto">
            <p className="mb-3 text-center text-[13px] text-muted">
              {projectId ? "Describe what you'd like changed in this project." : "Pick an idea to start from, or write your own below."}
            </p>
            {!projectId && (
              <div className="stagger grid gap-2">
                {EXAMPLES.map((ex) => (
                  <button key={ex.title} onClick={() => setInput(ex.prompt)} className="card-hover flex items-start gap-2.5 rounded-lg border border-line bg-panel p-2.5 text-left">
                    <Lightbulb className="mt-0.5 size-4 shrink-0 text-accent" />
                    <span>
                      <span className="block text-[13px] font-medium text-fg">{ex.title}</span>
                      <span className="block text-[11px] text-muted">{ex.hint}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={clsx("bubble", m.role)}>
              {m.text}
            </div>
          ))
        )}
        {busy && (
          <div className="thinking text-xs text-muted">
            <span />
            <span />
            <span />
          </div>
        )}
      </div>

      <div className="composer m-3 p-2.5">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={3}
          placeholder={projectId ? "e.g. Add a dark mode button" : "e.g. A unit converter for km, miles and metres"}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          className="block w-full resize-none bg-transparent text-[13px] leading-relaxed outline-none placeholder:text-muted"
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[11px] text-muted">Enter to send · Shift+Enter new line</span>
          <button className="btn btn-primary btn-sm" disabled={busy || input.trim().length < 3} onClick={submit} aria-label="Send">
            <Send />
          </button>
        </div>
      </div>
    </aside>
  );
}

export function IdeShell({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<div className="app"><main className="main">{children}</main></div>}>
      <IdeShellInner>{children}</IdeShellInner>
    </Suspense>
  );
}

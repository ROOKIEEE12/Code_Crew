import clsx from "clsx";
import { AlertTriangle, Ban, CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";
import type { RunStatus } from "@/lib/api";

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={clsx("rounded-xl border border-line bg-panel", className)}>{children}</div>;
}

export function SectionTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold tracking-tight text-fg">{children}</h2>
      {right}
    </div>
  );
}

/** Scrolling page body with the standard width and entrance animation. */
export function Page({ children, width = "max-w-5xl" }: { children: React.ReactNode; width?: string }) {
  return (
    <div className="scroll-thin h-full overflow-y-auto px-4 py-8 sm:px-8 md:px-12">
      <div className={clsx("mx-auto", width)}>{children}</div>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <header className="page-head">
      <div className="min-w-0">
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

const STATUS: Record<RunStatus, { label: string; cls: string; icon: React.ComponentType<{ className?: string }> }> = {
  queued: { label: "Waiting to start", cls: "bg-panel-2 text-muted", icon: CircleDashed },
  running: { label: "Working", cls: "bg-accent-soft text-accent", icon: Loader2 },
  succeeded: { label: "Verified", cls: "bg-ok-soft text-ok", icon: CheckCircle2 },
  failed: { label: "Some checks failed", cls: "bg-warn-soft text-warn", icon: AlertTriangle },
  cancelled: { label: "Cancelled", cls: "bg-panel-2 text-muted", icon: Ban },
  error: { label: "Error", cls: "bg-bad-soft text-bad", icon: XCircle },
};

export function StatusBadge({ status }: { status: RunStatus }) {
  const s = STATUS[status] ?? STATUS.queued;
  const Icon = s.icon;
  return (
    <span className={clsx("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap", s.cls)}>
      <Icon className={clsx("size-3.5", status === "running" && "animate-spin")} />
      {s.label}
    </span>
  );
}

export function Button({
  variant = "primary",
  size,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "quiet" | "danger"; size?: "sm" }) {
  return <button {...props} className={clsx("btn", `btn-${variant}`, size === "sm" && "btn-sm", className)} />;
}

export function Empty({ title, children, icon }: { title: string; children?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong px-6 py-12 text-center animate-[fade-in_.3s_ease-out]">
      {icon && <div className="mx-auto mb-3 grid size-10 place-items-center rounded-xl bg-panel-2 text-muted">{icon}</div>}
      <p className="text-sm font-medium text-fg">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="rounded-lg border border-bad/40 bg-bad-soft px-3 py-2 text-sm text-bad animate-[fade-in_.2s_ease-out]">
      {error instanceof Error ? error.message : String(error)}
    </div>
  );
}

export interface TabDef<T extends string> {
  id: T;
  label: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  count?: React.ReactNode;
  tone?: "ok" | "bad";
  className?: string;
}

export function Tabs<T extends string>({ tabs, value, onChange, className }: { tabs: TabDef<T>[]; value: T; onChange: (v: T) => void; className?: string }) {
  return (
    <div className={clsx("tabs", className)} role="tablist">
      {tabs.map((t) => {
        const Icon = t.icon;
        return (
          <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)} className={clsx("tab", t.className)}>
            {Icon && <Icon />}
            {t.label}
            {t.count !== undefined && t.count !== null && <span className={clsx("count", t.tone)}>{t.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "ok" | "bad" | "warn" }) {
  return (
    <div className="min-w-0 rounded-lg border border-line bg-panel-2/50 px-3 py-2">
      <div className="text-xs text-muted">{label}</div>
      <div className={clsx("truncate text-lg font-semibold tabular-nums", tone === "ok" && "text-ok", tone === "bad" && "text-bad", tone === "warn" && "text-warn")}>
        {value}
      </div>
    </div>
  );
}

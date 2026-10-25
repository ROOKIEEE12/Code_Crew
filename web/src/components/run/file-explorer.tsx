import clsx from "clsx";
import { FileCode2, FlaskConical } from "lucide-react";
import type { Verification } from "@/lib/api";
import type { TrackedFile } from "@/lib/use-run-stream";

export function FileExplorer({
  files,
  selected,
  onSelect,
  verification,
}: {
  files: TrackedFile[];
  selected: string | null;
  onSelect: (path: string) => void;
  verification?: Verification;
}) {
  const errorsByFile = new Map<string, number>();
  for (const i of verification?.issues ?? []) {
    if (i.file && i.severity === "error") errorsByFile.set(i.file, (errorsByFile.get(i.file) ?? 0) + 1);
  }
  const groups: [string, string, TrackedFile[]][] = [
    ["Your code", "Written by the Coder", files.filter((f) => f.kind === "source")],
    ["Tests", "Written first, by the Test Author", files.filter((f) => f.kind === "test")],
  ];
  if (!files.length) return <p className="px-4 py-3 text-xs text-muted">Files appear here as the agents write them.</p>;
  return (
    <div className="space-y-3 p-2">
      {groups.map(([label, hint, list]) =>
        list.length ? (
          <div key={label}>
            <div className="px-2 pb-1" title={hint}>
              <span className="text-[10.5px] font-semibold tracking-wider text-muted uppercase">{label}</span>
            </div>
            <ul className="stagger space-y-0.5">
              {[...list]
                .sort((a, b) => a.path.localeCompare(b.path))
                .map((f) => {
                  const errors = errorsByFile.get(f.path) ?? 0;
                  const Icon = f.kind === "test" ? FlaskConical : FileCode2;
                  return (
                    <li key={f.path}>
                      <button onClick={() => onSelect(f.path)} className={clsx("file-row", selected === f.path && "active")} title={f.path}>
                        <Icon className={clsx("file-icon", f.kind === "test" ? "text-[#e8ae79]" : "text-[#72a9ee]")} />
                        <span className="min-w-0 flex-1 truncate">{f.path}</span>
                        {f.versions.length > 1 && (
                          <span className="text-[10px] text-muted" title={`Changed ${f.versions.length - 1} time(s)`}>
                            v{f.versions.length}
                          </span>
                        )}
                        {errors > 0 && (
                          <span className="rounded bg-bad-soft px-1.5 text-[10px] text-bad" title={`${errors} problem(s)`}>
                            {errors}
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
            </ul>
          </div>
        ) : null,
      )}
    </div>
  );
}

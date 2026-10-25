export function timeAgo(epochSec: number): string {
  const s = Math.max(0, Date.now() / 1000 - epochSec);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(epochSec * 1000).toLocaleDateString();
}

export function duration(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`;
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
}

export function compact(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : String(n);
}

export function languageFor(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return (
    { py: "python", js: "javascript", mjs: "javascript", cjs: "javascript", ts: "typescript", html: "html", htm: "html",
      css: "css", json: "json", md: "markdown", yaml: "yaml", yml: "yaml", toml: "ini", ini: "ini", txt: "plaintext" } as Record<string, string>
  )[ext] ?? "plaintext";
}

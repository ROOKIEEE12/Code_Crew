"use client";

import dynamic from "next/dynamic";
import { languageFor } from "@/lib/format";

const Editor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
  loading: () => <div className="skeleton h-full rounded-none" />,
});
const DiffEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.DiffEditor), {
  ssr: false,
  loading: () => <div className="skeleton h-full rounded-none" />,
});

const OPTIONS = {
  readOnly: true,
  minimap: { enabled: false },
  fontSize: 13,
  smoothScrolling: true,
  cursorSmoothCaretAnimation: "on" as const,
  padding: { top: 12 },
  scrollBeyondLastLine: false,
  renderLineHighlight: "none" as const,
  automaticLayout: true,
  wordWrap: "on" as const,
};

export function CodeView({ path, content, original }: { path: string; content: string; original?: string }) {
  const theme = "vs-dark"; // the app is dark-only, so the editor always matches it
  const language = languageFor(path);
  if (original !== undefined) {
    return (
      <DiffEditor
        height="100%"
        theme={theme}
        language={language}
        original={original}
        modified={content}
        options={{ ...OPTIONS, renderSideBySide: false }}
      />
    );
  }
  return <Editor height="100%" theme={theme} language={language} value={content} path={path} options={OPTIONS} />;
}

"use client";

import { ArrowUp, Loader2, Wand2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { EXAMPLES } from "@/lib/crew";
import { ErrorNote } from "./ui";

export function NewRunForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [text, setText] = useState(() => params.get("prompt") ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const ready = text.trim().length >= 3;

  async function submit() {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    try {
      const run = await api.createRun(text.trim());
      router.push(`/runs/${run.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="composer p-4">
        <label htmlFor="requirement" className="sr-only">
          Describe what you want built
        </label>
        <textarea
          id="requirement"
          ref={box}
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={3}
          placeholder="e.g. A Python function that checks if a password is strong, with tests"
          className="block w-full resize-none bg-transparent text-[15px] leading-relaxed text-fg outline-none placeholder:text-muted"
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <span className="text-xs text-muted">
            <kbd>Enter</kbd> to start · <kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line
          </span>
          <button onClick={submit} disabled={!ready || busy} className="btn btn-primary">
            {busy ? (
              <>
                <Loader2 className="animate-spin" /> Starting…
              </>
            ) : (
              <>
                Build it <ArrowUp />
              </>
            )}
          </button>
        </div>
      </div>

      <ErrorNote error={error} />

      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 inline-flex items-center gap-1.5 text-xs text-muted">
          <Wand2 className="size-3.5" /> Try an example:
        </span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.title}
            className="chip"
            title={ex.prompt}
            onClick={() => {
              setText(ex.prompt);
              box.current?.focus();
            }}
          >
            {ex.title}
          </button>
        ))}
      </div>
    </div>
  );
}

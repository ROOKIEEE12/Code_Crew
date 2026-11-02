"use client";

import clsx from "clsx";
import { ArrowUp, ImagePlus, Loader2, MessageCircleQuestion, Wand2, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { EXAMPLES } from "@/lib/crew";
import { MAX_IMAGES, imagesFrom, prepareImage, type PreparedImage } from "@/lib/images";
import { usePref } from "@/lib/prefs";
import { ErrorNote } from "./ui";

export function NewRunForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [text, setText] = useState(() => params.get("prompt") ?? "");
  // Set by "Edit prompt" on a run: the run this new one replaces.
  const replacing = params.get("replace");
  const [dropOld, setDropOld] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const [images, setImages] = useState<PreparedImage[]>([]);
  const [dragging, setDragging] = useState(false);
  const hasLink = /https?:\/\/\S+/i.test(text);

  // Free the thumbnails' memory when the form goes away.
  const imagesRef = useRef(images);
  useEffect(() => {
    imagesRef.current = images;
  }, [images]);
  useEffect(() => () => imagesRef.current.forEach((i) => URL.revokeObjectURL(i.preview)), []);

  async function addImages(files: File[]) {
    if (!files.length) return;
    const room = MAX_IMAGES - images.length;
    if (room <= 0) return setError(`You can attach up to ${MAX_IMAGES} images.`);
    setError(null);
    try {
      const prepared = await Promise.all(files.slice(0, room).map(prepareImage));
      setImages((cur) => [...cur, ...prepared].slice(0, MAX_IMAGES));
      if (files.length > room) setError(`Only the first ${room} image(s) were added (up to ${MAX_IMAGES}).`);
    } catch (e) {
      setError(e);
    }
  }

  function removeImage(i: number) {
    setImages((cur) => {
      URL.revokeObjectURL(cur[i].preview);
      return cur.filter((_, j) => j !== i);
    });
  }
  const [askPref, setAskPref] = usePref("ask-questions", "1");
  const ask = askPref === "1";
  const ready = text.trim().length >= 3;

  async function submit() {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    try {
      const run = await api.createRun(text.trim(), ask, images.map((i) => i.upload));
      if (replacing && dropOld) await api.deleteRun(replacing).catch(() => undefined);
      router.push(`/runs/${run.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div
        className={clsx("composer p-4 transition-[box-shadow,border-color]", dragging && "border-accent shadow-[0_0_0_3px_#7c66dc33]")}
        onDragOver={(e) => {
          if (!Array.from(e.dataTransfer.types).includes("Files")) return;
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          setDragging(false);
          const files = imagesFrom(e.dataTransfer.files);
          if (!files.length) return;
          e.preventDefault();
          addImages(files);
        }}
      >
        <label htmlFor="requirement" className="sr-only">
          Describe what you want built
        </label>
        <textarea
          id="requirement"
          ref={box}
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPaste={(e) => {
            const files = imagesFrom(e.clipboardData.items);
            if (files.length) {
              e.preventDefault();
              addImages(files);
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={3}
          placeholder="e.g. A website for my bakery with a menu and opening hours. Paste a link or a screenshot of a design you like."
          className="block w-full resize-none bg-transparent text-[15px] leading-relaxed text-fg outline-none placeholder:text-muted"
        />
        {images.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-2" aria-label="Attached images">
            {images.map((img, i) => (
              <li key={img.preview} className="group relative animate-[fade-in_.2s_ease-out]">
                {/* eslint-disable-next-line @next/next/no-img-element -- local object URL */}
                <img src={img.preview} alt={img.name} className="h-16 w-24 rounded-lg border border-line-strong object-cover" />
                <button
                  type="button"
                  onClick={() => removeImage(i)}
                  className="absolute -top-1.5 -right-1.5 grid size-5 place-items-center rounded-full border border-line-strong bg-panel text-muted hover:text-fg"
                  aria-label={`Remove ${img.name}`}
                  title="Remove"
                >
                  <X className="size-3" />
                </button>
              </li>
            ))}
          </ul>
        )}
        {(hasLink || images.length > 0) && (
          <p className="mt-2 text-xs text-muted">
            {[hasLink ? "The crew will open the link and study it" : "", images.length ? `the design will follow your ${images.length} image(s)` : ""]
              .filter(Boolean)
              .join("; ")
              .replace(/^./, (c) => c.toUpperCase())}
            .
          </p>
        )}
        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <input
              ref={picker}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              multiple
              hidden
              onChange={(e) => {
                addImages(imagesFrom(e.target.files));
                e.target.value = "";
              }}
            />
            <button
              type="button"
              className="btn btn-quiet btn-sm"
              onClick={() => picker.current?.click()}
              disabled={images.length >= MAX_IMAGES}
              title="Attach screenshots of a design you like (or paste / drop them here)"
            >
              <ImagePlus /> Add image
            </button>
            <label className="toggle" title="The Planner may ask up to 2 quick multiple-choice questions before planning. Unanswered questions use the recommended option.">
              <input type="checkbox" checked={ask} onChange={(e) => setAskPref(e.target.checked ? "1" : "0")} />
              <span className="toggle-track" aria-hidden />
              <MessageCircleQuestion className="size-3.5" />
              Let the crew ask me questions first
            </label>
            {replacing && (
              <label className="toggle">
                <input type="checkbox" checked={dropOld} onChange={(e) => setDropOld(e.target.checked)} />
                <span className="toggle-track" aria-hidden />
                Delete the old run when this one starts
              </label>
            )}
            <span className="hidden text-xs text-muted md:inline">
              <kbd>Enter</kbd> to start · <kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line
            </span>
          </div>
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

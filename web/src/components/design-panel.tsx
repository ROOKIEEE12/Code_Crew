import { CheckCircle2, ExternalLink, Link2, Palette, Sparkles, XCircle } from "lucide-react";
import { imageUrl, type DesignBrief, type DesignReview, type ImageRef, type Reference } from "@/lib/api";

/** The Planner's design brief: what the page should look like. */
export function DesignBriefView({ design }: { design: DesignBrief }) {
  return (
    <section>
      <h3 className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted">
        <Palette className="size-3.5" /> Design the Planner chose
      </h3>
      <div className="space-y-3 rounded-lg border border-line bg-panel p-3">
        <p>{design.style}</p>
        <ul className="flex flex-wrap gap-2" aria-label="Colour palette">
          {design.palette.map((c) => (
            <li key={c.name + c.hex} className="flex items-center gap-2 rounded-md border border-line bg-panel-2 py-1 pr-2 pl-1" title={c.usage}>
              <span className="size-5 rounded border border-white/10" style={{ background: c.hex }} aria-hidden />
              <span className="text-xs">{c.name}</span>
              <code className="font-mono text-[11px] text-muted">{c.hex}</code>
            </li>
          ))}
        </ul>
        <p className="text-xs text-muted">
          <span className="text-fg-2">Type:</span> {design.typography}
        </p>
        <ol className="space-y-1.5">
          {design.sections.map((sec, i) => (
            <li key={sec.page + sec.id} className="flex gap-2">
              <span className="w-5 shrink-0 text-right font-mono text-xs text-muted">{i + 1}</span>
              <div className="min-w-0">
                <span className="font-medium">{sec.name}</span>{" "}
                <code className="font-mono text-[11px] text-accent">
                  #{sec.id}
                  {sec.page !== "index.html" ? ` · ${sec.page}` : ""}
                </code>
                <p className="text-xs text-muted">{sec.content}</p>
              </div>
            </li>
          ))}
        </ol>
        {design.interactions.length > 0 && (
          <p className="text-xs text-muted">
            <span className="text-fg-2">Interactions:</span> {design.interactions.join("; ")}
          </p>
        )}
        <p className="text-xs text-muted">
          <span className="text-fg-2">On phones:</span> {design.responsive}
        </p>
        {design.reference_notes && (
          <p className="text-xs text-muted">
            <span className="text-fg-2">From your references:</span> {design.reference_notes}
          </p>
        )}
      </div>
    </section>
  );
}

/** Links the crew read and images it was given, with what it got out of them. */
export function DesignInputs({ runId, references, images }: { runId: string; references: Reference[]; images: ImageRef[] }) {
  const refImages = images.filter((i) => i.kind === "reference");
  if (!references.length && !refImages.length) return null;
  return (
    <section className="px-4 pt-4 sm:px-6">
      <h3 className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted">
        <Link2 className="size-3.5" /> What you showed the crew
      </h3>
      <ul className="space-y-2 text-[13px]">
        {references.map((r) => (
          <li key={r.url} className="rounded-lg border border-line bg-panel px-3 py-2">
            <div className="flex items-center gap-2">
              {r.ok ? <CheckCircle2 className="size-3.5 shrink-0 text-ok" /> : <XCircle className="size-3.5 shrink-0 text-bad" />}
              <a href={r.url} target="_blank" rel="noreferrer" className="min-w-0 truncate text-fg hover:underline">
                {r.title || r.url}
              </a>
              <ExternalLink className="size-3 shrink-0 text-muted" />
            </div>
            {r.ok ? (
              <p className="mt-1 text-xs text-muted">
                Read {r.outline.length} part(s) of the page
                {r.colors.length ? `, ${r.colors.length} colours` : ""}
                {r.fonts.length ? `, fonts: ${r.fonts.join(", ")}` : ""}.
              </p>
            ) : (
              <p className="mt-1 text-xs text-bad">
                Could not read it: {r.error}. Attach a screenshot of the page instead, so the crew can see it.
              </p>
            )}
          </li>
        ))}
      </ul>
      {refImages.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {refImages.map((img) => (
            <a key={img.id} href={imageUrl(runId, img.id)} target="_blank" rel="noreferrer" title={img.label}>
              {/* eslint-disable-next-line @next/next/no-img-element -- served by the API */}
              <img src={imageUrl(runId, img.id)} alt={img.label} loading="lazy" className="h-20 w-auto max-w-[180px] rounded-md border border-line-strong object-cover object-top" />
            </a>
          ))}
        </div>
      )}
    </section>
  );
}

/** The Reviewer's verdict on how the finished page looks. */
export function DesignReviews({ runId, reviews }: { runId: string; reviews: DesignReview[] }) {
  if (!reviews.length) return null;
  return (
    <section className="px-4 pt-4 sm:px-6">
      <h3 className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted">
        <Sparkles className="size-3.5" /> Design review (the Reviewer looked at screenshots)
      </h3>
      {reviews.map((r) => (
        <div key={r.round} className="rounded-lg border border-line bg-panel px-3 py-2 text-[13px]">
          <div className="flex flex-wrap items-center gap-2">
            <b className={r.score >= 8 ? "text-ok" : "text-warn"}>{r.score}/10</b>
            <span className="text-muted">
              {!r.fixes.length || !r.applied
                ? r.score >= 8
                  ? "Ready to ship."
                  : "Fixes suggested but not applied."
                : r.kept
                  ? "The Coder applied the fixes and every check still passed."
                  : "The Coder's fixes broke a check, so the version from before them was kept."}
            </span>
          </div>
          {r.fixes.length > 0 && (
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-fg-2">
              {r.fixes.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
          {r.screenshots.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {r.screenshots.map((id) => (
                <a key={id} href={imageUrl(runId, id)} target="_blank" rel="noreferrer">
                  {/* eslint-disable-next-line @next/next/no-img-element -- served by the API */}
                  <img src={imageUrl(runId, id)} alt="Screenshot the Reviewer looked at" loading="lazy" className="h-24 w-auto max-w-[150px] rounded-md border border-line-strong object-cover object-top" />
                </a>
              ))}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

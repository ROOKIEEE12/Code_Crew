"use client";

import { useEffect, useRef, useState } from "react";
import { BUILD_STEPS, STEP } from "@/lib/crew";
import { sounds } from "@/lib/sound";
import { isFresh, type RunView } from "@/lib/use-run-stream";

/** "Verified" stamp + confetti, only when the user watched the run finish green. */
export function Celebrate({ view }: { view: RunView }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!view.done || view.done.status !== "succeeded" || !isFresh(view.done.ts, 8)) return;
    const start = setTimeout(() => {
      setShow(true);
      sounds.win();
    }, 0);
    const hide = setTimeout(() => setShow(false), 4200);

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cv = canvas.current;
    const ctx = cv?.getContext("2d");
    if (reduce || !cv || !ctx)
      return () => {
        clearTimeout(start);
        clearTimeout(hide);
      };
    const r = cv.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    cv.width = r.width * dpr;
    cv.height = r.height * dpr;
    ctx.scale(dpr, dpr);
    const colors = BUILD_STEPS.map((id) => STEP[id].tone);
    const parts = Array.from({ length: 160 }, () => ({
      x: r.width / 2,
      y: r.height * 0.45,
      vx: (Math.random() - 0.5) * 14,
      vy: -Math.random() * 13 - 3,
      w: 5 + Math.random() * 6,
      h: 3 + Math.random() * 4,
      a: Math.random() * 3,
      va: (Math.random() - 0.5) * 0.3,
      c: colors[(Math.random() * colors.length) | 0],
    }));
    let t = 0;
    let raf = 0;
    const frame = () => {
      ctx.clearRect(0, 0, r.width, r.height);
      for (const p of parts) {
        p.vy += 0.32;
        p.vx *= 0.99;
        p.x += p.vx;
        p.y += p.vy;
        p.a += p.va;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.a);
        ctx.globalAlpha = Math.max(0, 1 - t / 150);
        ctx.fillStyle = p.c;
        ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      }
      if (++t < 150) raf = requestAnimationFrame(frame);
      else ctx.clearRect(0, 0, r.width, r.height);
    };
    raf = requestAnimationFrame(frame);
    return () => {
      clearTimeout(start);
      clearTimeout(hide);
      cancelAnimationFrame(raf);
    };
  }, [view.done]);

  return (
    <>
      <canvas ref={canvas} className="confetti" aria-hidden />
      {show && (
        <div className="stamp" role="status">
          Verified
        </div>
      )}
    </>
  );
}

"use client";

// Tiny Web Audio "blips" for crew events. Off unless the user turns sound on;
// the audio context is only created after that click (browsers require a gesture).
let ctx: AudioContext | null = null;
let enabled = false;

export function setSound(on: boolean): boolean {
  if (on && !ctx) {
    try {
      const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      ctx = AC ? new AC() : null;
    } catch {
      ctx = null;
    }
  }
  ctx?.resume?.().catch(() => {});
  enabled = on && !!ctx;
  return enabled;
}

export function beep(freq: number, dur = 0.05, gain = 0.06) {
  if (!enabled || !ctx) return;
  const o = ctx.createOscillator();
  const g = ctx.createGain();
  o.type = "sine";
  o.frequency.value = freq;
  g.gain.setValueAtTime(0.0001, ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(gain, ctx.currentTime + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + dur + 0.08);
  o.connect(g).connect(ctx.destination);
  o.start();
  o.stop(ctx.currentTime + dur + 0.1);
}

export const sounds = {
  step: (i: number) => beep(330 + i * 60, 0.05),
  message: () => beep(880, 0.02, 0.03),
  pass: () => beep(660, 0.04),
  fail: () => beep(180, 0.12),
  question: () => beep(740, 0.08),
  win: () => [523, 659, 784, 1047].forEach((f, i) => setTimeout(() => beep(f, 0.18), i * 110)),
};

"use client";
import { useEffect, useRef, useState } from "react";

export function useReducedMotion() {
  const [r, setR] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    setR(m.matches);
    const f = () => setR(m.matches);
    m.addEventListener?.("change", f);
    return () => m.removeEventListener?.("change", f);
  }, []);
  return r;
}

/** Current time, ticking every `ms`. */
export function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

/** Smoothly glides a number toward its target instead of jumping. */
export function useTween(target: number | null | undefined, ms = 900) {
  const [v, setV] = useState<number>(target ?? 0);
  const from = useRef(v);
  const raf = useRef(0);
  useEffect(() => {
    if (target == null || Number.isNaN(target)) return;
    const start = performance.now();
    const a = from.current;
    const b = target;
    if (a === b) return;
    cancelAnimationFrame(raf.current);
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / ms);
      const e = 1 - Math.pow(1 - k, 3);
      const x = a + (b - a) * e;
      from.current = x;
      setV(x);
      if (k < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [target, ms]);
  return v;
}

export const pad = (n: number, w = 2) => String(Math.max(0, Math.floor(n))).padStart(w, "0");

export function dur(ms: number) {
  if (!Number.isFinite(ms) || ms < 0) ms = 0;
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return d ? `${d}D ${pad(h)}:${pad(m)}:${pad(sec)}` : `${pad(h)}:${pad(m)}:${pad(sec)}`;
}

const TZ = "America/New_York";
export const fmtTime = (t: number | string | Date, sec = true) =>
  new Date(t).toLocaleTimeString("en-US", { timeZone: TZ, hour12: false, hour: "2-digit", minute: "2-digit", ...(sec ? { second: "2-digit" } : {}) });
export const fmtDate = (t: number | string | Date) =>
  new Date(t).toLocaleDateString("en-US", { timeZone: TZ, weekday: "short", month: "short", day: "2-digit", year: "numeric" }).toUpperCase();
export const fmtShortDate = (t: number | string | Date) =>
  new Date(t).toLocaleDateString("en-US", { timeZone: TZ, month: "short", day: "2-digit" }).toUpperCase();

export const money = (n: number | null | undefined, d = 2) => (n == null ? "--" : `$${n.toFixed(d)}`);
export const compact = (n: number | null | undefined) =>
  n == null ? "--" : n >= 1e6 ? `${(n / 1e6).toFixed(2)}M` : n >= 1e4 ? `${(n / 1e3).toFixed(1)}K` : Math.round(n).toLocaleString("en-US");

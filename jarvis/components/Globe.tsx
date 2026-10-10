"use client";
// Wireframe globe radar. Blips = where followers are (Instagram insights by country).
// Without that data (needs 100+ followers) it runs in AMBIENT mode: home base + sweep only.
import { useEffect, useRef } from "react";
import { geoOrthographic, geoPath, geoGraticule10, geoDistance } from "d3-geo";
import { feature } from "topojson-client";
import land110 from "world-atlas/land-110m.json";

// Rough country centroids [lon, lat] for the codes Instagram returns.
const CENTROIDS: Record<string, [number, number]> = {
  US: [-98, 39], CA: [-106, 56], MX: [-102, 23], BR: [-52, -10], AR: [-64, -34], CO: [-73, 4], PE: [-75, -9],
  CL: [-71, -33], GB: [-2, 54], IE: [-8, 53], FR: [2, 46], DE: [10, 51], ES: [-4, 40], PT: [-8, 39], IT: [12, 42],
  NL: [5, 52], BE: [4, 50], CH: [8, 47], SE: [16, 62], NO: [9, 61], PL: [19, 52], UA: [31, 49], RU: [60, 58],
  TR: [35, 39], EG: [30, 27], NG: [8, 9], KE: [38, 0], ZA: [24, -29], MA: [-7, 32], SA: [45, 24], AE: [54, 24],
  IL: [35, 31], IN: [79, 22], PK: [70, 30], BD: [90, 24], CN: [104, 35], JP: [138, 37], KR: [128, 36], PH: [122, 12],
  VN: [106, 16], TH: [101, 15], MY: [102, 4], SG: [104, 1.3], ID: [118, -2], AU: [134, -25], NZ: [172, -41],
  PR: [-66.5, 18.2], JM: [-77.3, 18.1], DO: [-70.5, 18.8], VE: [-66, 7],
};
const HOME: [number, number] = [-81.53, 28.49]; // Windermere, FL

const LAND: any = feature(land110 as any, (land110 as any).objects.land);
const GRAT = geoGraticule10();

export default function Globe({
  size,
  countries,
  still,
}: {
  size: number;
  countries: { code: string; value: number }[] | null;
  still: boolean;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const data = useRef(countries);
  data.current = countries;

  useEffect(() => {
    const c = ref.current!;
    const ctx = c.getContext("2d")!;
    const S = size;
    c.width = S * 2;
    c.height = S * 2;
    ctx.scale(2, 2);
    const R = S / 2 - 8;
    const proj = geoOrthographic().scale(R).translate([S / 2, S / 2]).clipAngle(90).precision(0.6);
    const path = geoPath(proj, ctx);
    let raf = 0;
    let lon = -60;
    let last = performance.now();
    const blipFade = new Map<string, number>();

    const draw = (t: number) => {
      const dt = Math.min(64, t - last);
      last = t;
      lon += dt * 0.006;
      proj.rotate([-lon, -18]);
      const sweep = ((t / 4000) % 1) * Math.PI * 2; // one turn every 4s
      ctx.clearRect(0, 0, S, S);

      // disc
      const g = ctx.createRadialGradient(S / 2, S / 2, R * 0.2, S / 2, S / 2, R);
      g.addColorStop(0, "rgba(27,157,217,0.05)");
      g.addColorStop(1, "rgba(27,157,217,0.16)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(S / 2, S / 2, R, 0, Math.PI * 2);
      ctx.fill();

      ctx.lineWidth = 0.5;
      ctx.strokeStyle = "rgba(27,157,217,0.28)";
      ctx.beginPath();
      path(GRAT);
      ctx.stroke();

      ctx.lineWidth = 0.9;
      ctx.strokeStyle = "rgba(57,199,255,0.85)";
      ctx.fillStyle = "rgba(57,199,255,0.08)";
      ctx.beginPath();
      path(LAND);
      ctx.fill();
      ctx.stroke();

      // sweep wedge
      const wedge = ctx.createConicGradient ? ctx.createConicGradient(sweep - 0.9, S / 2, S / 2) : null;
      if (wedge) {
        wedge.addColorStop(0, "rgba(57,199,255,0)");
        wedge.addColorStop(0.14, "rgba(57,199,255,0.28)");
        wedge.addColorStop(0.1433, "rgba(57,199,255,0)");
        wedge.addColorStop(1, "rgba(57,199,255,0)");
        ctx.fillStyle = wedge;
        ctx.beginPath();
        ctx.arc(S / 2, S / 2, R, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.strokeStyle = "rgba(139,233,255,0.9)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(S / 2, S / 2);
      ctx.lineTo(S / 2 + Math.cos(sweep) * R, S / 2 + Math.sin(sweep) * R);
      ctx.stroke();

      // blips
      const list = data.current?.length
        ? data.current.map((d) => ({ code: d.code, ll: CENTROIDS[d.code], v: d.value })).filter((d) => d.ll)
        : [];
      const max = Math.max(1, ...list.map((d) => d.v));
      const all = [{ code: "HOME", ll: HOME, v: max }, ...list];
      for (const b of all) {
        const p = proj(b.ll as [number, number]);
        if (!p) continue;
        // is it on the visible side?
        if (geoDistance(b.ll as [number, number], [lon, 18]) > Math.PI / 2 - 0.05) continue;
        const ang = Math.atan2(p[1] - S / 2, p[0] - S / 2);
        let diff = (sweep - ang) % (Math.PI * 2);
        if (diff < 0) diff += Math.PI * 2;
        if (diff < 0.12) blipFade.set(b.code, 1);
        const f = blipFade.get(b.code) ?? 0.25;
        blipFade.set(b.code, Math.max(0.25, f - dt / 2600));
        const size = 2 + 5 * Math.sqrt(b.v / max);
        const home = b.code === "HOME";
        ctx.fillStyle = `rgba(139,233,255,${0.35 + 0.65 * f})`;
        ctx.beginPath();
        ctx.arc(p[0], p[1], home ? 3 : size * 0.6, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = `rgba(139,233,255,${0.6 * f})`;
        ctx.beginPath();
        ctx.arc(p[0], p[1], (home ? 6 : size) + (1 - f) * 10, 0, Math.PI * 2);
        ctx.stroke();
      }

      // rim
      ctx.strokeStyle = "rgba(57,199,255,0.7)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(S / 2, S / 2, R, 0, Math.PI * 2);
      ctx.stroke();
      if (!still) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size, still]);

  return <canvas ref={ref} style={{ width: size, height: size }} />;
}

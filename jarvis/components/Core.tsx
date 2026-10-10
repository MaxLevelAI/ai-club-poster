"use client";
// The hero: nested rings around an original wireframe orb. The orb spins and pulses faster while
// the agent is working.
import { useEffect, useRef } from "react";

const CX = 300;
const CY = 300;

function ticks(r: number, n: number, len: number, majorEvery = 0, majorLen = 0) {
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const L = majorEvery && i % majorEvery === 0 ? majorLen : len;
    const c = Math.cos(a), s = Math.sin(a);
    out.push(`M${CX + c * r} ${CY + s * r}L${CX + c * (r - L)} ${CY + s * (r - L)}`);
  }
  return out.join("");
}

function arc(r: number, a0: number, a1: number) {
  const p = (a: number) => [CX + Math.cos(((a - 90) * Math.PI) / 180) * r, CY + Math.sin(((a - 90) * Math.PI) / 180) * r];
  const [x0, y0] = p(a0);
  const [x1, y1] = p(a1);
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M${x0} ${y0}A${r} ${r} 0 ${large} 1 ${x1} ${y1}`;
}

function segments(r: number, count: number, gapDeg: number) {
  const step = 360 / count;
  return Array.from({ length: count }, (_, i) => arc(r, i * step + gapDeg / 2, (i + 1) * step - gapDeg / 2)).join("");
}

function Orb({ speed, warn, still }: { speed: number; warn: boolean; still: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const sp = useRef(speed);
  sp.current = speed;
  useEffect(() => {
    const c = ref.current!;
    const ctx = c.getContext("2d")!;
    const S = 240;
    c.width = S * 2;
    c.height = S * 2;
    ctx.scale(2, 2);
    // Points on a sphere: a fibonacci lattice, then connect near neighbours = node graph.
    const N = 90;
    const pts: number[][] = [];
    for (let i = 0; i < N; i++) {
      const y = 1 - (i / (N - 1)) * 2;
      const rr = Math.sqrt(1 - y * y);
      const th = i * 2.399963;
      pts.push([Math.cos(th) * rr, y, Math.sin(th) * rr]);
    }
    const edges: [number, number][] = [];
    for (let i = 0; i < N; i++)
      for (let j = i + 1; j < N; j++) {
        const d = Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1], pts[i][2] - pts[j][2]);
        if (d < 0.36) edges.push([i, j]);
      }
    let raf = 0;
    let rot = 0;
    let t0 = performance.now();
    const col = warn ? "255,181,71" : "57,199,255";
    const draw = (t: number) => {
      const dt = Math.min(64, t - t0);
      t0 = t;
      rot += (dt / 1000) * 0.25 * sp.current;
      const pulse = 1 + Math.sin(t / (900 / sp.current)) * 0.045 * Math.min(2, sp.current);
      ctx.clearRect(0, 0, S, S);
      const R = 78 * pulse;
      const cr = Math.cos(rot), sr = Math.sin(rot);
      const tilt = 0.38, ct = Math.cos(tilt), st = Math.sin(tilt);
      const proj = pts.map(([x, y, z]) => {
        const x1 = x * cr + z * sr;
        const z1 = -x * sr + z * cr;
        const y2 = y * ct - z1 * st;
        const z2 = y * st + z1 * ct;
        return [S / 2 + x1 * R, S / 2 + y2 * R, z2];
      });
      // glow
      const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, R * 1.35);
      g.addColorStop(0, `rgba(${col},${0.22 + 0.08 * (pulse - 1) * 10})`);
      g.addColorStop(0.55, `rgba(${col},0.06)`);
      g.addColorStop(1, `rgba(${col},0)`);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(S / 2, S / 2, R * 1.35, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 0.7;
      for (const [i, j] of edges) {
        const a = proj[i], b = proj[j];
        const depth = (a[2] + b[2]) / 2;
        ctx.strokeStyle = `rgba(${col},${0.12 + 0.45 * (depth + 1) / 2})`;
        ctx.beginPath();
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(b[0], b[1]);
        ctx.stroke();
      }
      for (const p of proj) {
        const k = (p[2] + 1) / 2;
        ctx.fillStyle = `rgba(${warn ? "255,214,150" : "139,233,255"},${0.25 + 0.75 * k})`;
        ctx.beginPath();
        ctx.arc(p[0], p[1], 0.8 + 1.2 * k, 0, Math.PI * 2);
        ctx.fill();
      }
      if (!still) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [warn, still]);
  return <canvas ref={ref} className="orb" style={{ width: 240, height: 240 }} />;
}

export default function Core({
  status,
  uptime,
  progress,
  stepLabel,
  still,
}: {
  status: string;
  uptime: string;
  progress: number | null;
  stepLabel: string;
  still: boolean;
}) {
  const warn = status === "KILLED" || status === "OFFLINE";
  const working = status === "WORKING";
  const speed = working ? 3.2 : status === "PAUSED" ? 0.35 : warn ? 0.2 : 1;
  const cls = `core ${warn ? "warn" : ""} ${status === "PAUSED" ? "dim" : ""} ${working ? "busy" : ""}`;
  return (
    <div className={cls}>
      <svg width={600} height={600} viewBox="0 0 600 600" className="glow">
        <g className="spin-cw-slow">
          <circle cx={CX} cy={CY} r={286} className="s1 o25" />
          <path d={ticks(286, 180, 5, 15, 13)} className="s1 o60" />
          {[45, 135, 225, 315].map((a) => (
            <text
              key={a}
              className="ringlbl"
              transform={`rotate(${a} ${CX} ${CY}) translate(${CX} ${CY - 264})`}
              textAnchor="middle"
            >
              {["AGENT CORE", "JARVIS ∙ INSTAGRAM", "MAXLEVEL AI", "PLAN ∙ ACT ∙ OBSERVE"][(a - 45) / 90]}
            </text>
          ))}
        </g>
        <g className="spin-ccw">
          <path d={segments(258, 24, 4)} className="s2 o70" strokeWidth={3} />
        </g>
        <g className="spin-cw">
          <circle cx={CX} cy={CY} r={236} className="s1 o40" strokeDasharray="2 7" />
          <path d={arc(236, 20, 70) + arc(236, 200, 250)} className="s3 o90" strokeWidth={2} />
        </g>
        {/* progress ring for the current run */}
        <circle cx={CX} cy={CY} r={214} className="s1 o20" strokeWidth={6} />
        {progress != null && progress > 0 && (
          <path d={arc(214, 0, Math.max(2, Math.min(359.9, progress * 360)))} className="s3 o100 prog" strokeWidth={6} />
        )}
        <g className="spin-ccw-slow">
          <path d={segments(190, 3, 30)} className="s2 o50" strokeWidth={1.2} />
          <path d={ticks(190, 72, 6)} className="s1 o35" />
        </g>
        <g className="spin-cw-fast">
          <path d={arc(160, 0, 40) + arc(160, 120, 160) + arc(160, 240, 280)} className="s3 o80" strokeWidth={1.5} />
        </g>
        <circle cx={CX} cy={CY} r={146} className="s1 o30" />
        {/* crosshair */}
        <path d={`M${CX - 300} ${CY}h40M${CX + 260} ${CY}h40M${CX} ${CY - 300}v24M${CX} ${CY + 276}v24`} className="s1 o50" />
      </svg>
      <Orb speed={speed} warn={warn} still={still} />
      <div className="core-text">
        <div className="core-kicker">{working ? stepLabel : "AGENT STATUS"}</div>
        <div className={`core-status ${warn ? "amber" : ""}`}>{status}</div>
        <div className="core-up">
          <span className="lbl">UPTIME</span> {uptime}
        </div>
      </div>
    </div>
  );
}

"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Core from "./Core";
import Globe from "./Globe";
import Voice from "./Voice";
import { compact, dur, fmtDate, fmtShortDate, fmtTime, money, pad, useNow, useReducedMotion, useTween } from "./hooks";

type S = any;
const KEY = "jarvis-key";
const store = {
  get: () => {
    try {
      return localStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set: (v: string | null) => {
    try {
      v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY);
    } catch {}
  },
};

/* ───────────────────────── small building blocks ───────────────────────── */

function Panel({
  x, y, w, h, title, right, children, warn, pulse, className = "",
}: {
  x: number; y: number; w: number; h: number; title?: string; right?: React.ReactNode; children?: React.ReactNode;
  warn?: boolean; pulse?: any; className?: string;
}) {
  const c = 14;
  return (
    <section className={`panel ${warn ? "warn" : ""} ${className}`} style={{ left: x, top: y, width: w, height: h }}>
      <svg className="frame glow" width={w} height={h}>
        <path
          d={`M0.5 ${c}V0.5H${c}M${w - c} 0.5H${w - 0.5}V${c}M${w - 0.5} ${h - c}V${h - 0.5}H${w - c}M${c} ${h - 0.5}H0.5V${h - c}`}
          className="br"
        />
        <path d={`M${c + 8} 0.5H${Math.min(w * 0.35, w - c - 8)}`} className="br faint" />
        <path d={`M${w - c - 8} ${h - 0.5}H${Math.max(w * 0.7, c + 8)}`} className="br faint" />
      </svg>
      {title && (
        <div className="ph">
          <span>{title}</span>
          {right}
        </div>
      )}
      <div className="pb">{children}</div>
      <div key={String(pulse)} className="flick" />
    </section>
  );
}

function Num({ v, d = 0, prefix = "", suffix = "" }: { v: number | null | undefined; d?: number; prefix?: string; suffix?: string }) {
  const t = useTween(v ?? 0);
  if (v == null) return <span className="dim">--</span>;
  return (
    <span>
      {prefix}
      {t.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}
      {suffix}
    </span>
  );
}

/** Button that needs to be held down (kill switch). */
function HoldButton({ label, onDone, amber, ms = 1300, sub }: { label: string; onDone: () => void; amber?: boolean; ms?: number; sub?: string }) {
  const [p, setP] = useState(0);
  const t = useRef<any>(null);
  const start = () => {
    const s = performance.now();
    const step = () => {
      const k = Math.min(1, (performance.now() - s) / ms);
      setP(k);
      if (k >= 1) {
        stop(false);
        onDone();
      } else t.current = requestAnimationFrame(step);
    };
    t.current = requestAnimationFrame(step);
  };
  const stop = (reset = true) => {
    cancelAnimationFrame(t.current);
    if (reset) setP(0);
    else setTimeout(() => setP(0), 400);
  };
  return (
    <button
      className={`ctl hold ${amber ? "amber" : ""}`}
      onPointerDown={start}
      onPointerUp={() => stop()}
      onPointerLeave={() => stop()}
      onKeyDown={(e) => e.key === "Enter" && !e.repeat && start()}
      onKeyUp={() => stop()}
    >
      <span className="fill" style={{ width: `${p * 100}%` }} />
      <span className="lbl">{label}</span>
      {sub && <span className="sub">{p > 0 ? "KEEP HOLDING…" : sub}</span>}
    </button>
  );
}

/** Click once to arm, click again within 4s to fire. */
function ArmButton({ label, armed: armedLabel, onFire, className = "", disabled }: { label: string; armed: string; onFire: () => void; className?: string; disabled?: boolean }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const id = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(id);
  }, [armed]);
  return (
    <button
      disabled={disabled}
      className={`${className} ${armed ? "armed" : ""}`}
      onClick={() => {
        if (armed) {
          setArmed(false);
          onFire();
        } else setArmed(true);
      }}
    >
      {armed ? armedLabel : label}
    </button>
  );
}

/* ───────────────────────── the HUD ───────────────────────── */

export default function Hud() {
  const [scale, setScale] = useState(1);
  const [s, setS] = useState<S | null>(null);
  const [link, setLink] = useState<"connecting" | "live" | "lost">("connecting");
  const [lastSync, setLastSync] = useState<number | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [unlockOpen, setUnlockOpen] = useState(false);
  const [toast, setToast] = useState<{ text: string; warn?: boolean; at: number } | null>(null);
  const [sel, setSel] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const fastUntil = useRef(0);
  const still = useReducedMotion();
  const now = useNow(1000);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // Fit the fixed 1920x1080 stage to any screen.
  useEffect(() => {
    const f = () => setScale(Math.min(window.innerWidth / 1920, window.innerHeight / 1080));
    f();
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, []);

  useEffect(() => setKey(store.get()), []);

  // Live data: poll the server every 3s (1.5s right after you press something).
  const poll = useCallback(async () => {
    try {
      const r = await fetch("/api/state", { cache: "no-store" });
      const j = await r.json();
      if (j.fatal) throw new Error(j.error);
      setS(j);
      setLink("live");
      setLastSync(Date.now());
    } catch {
      setLink("lost");
    }
  }, []);
  useEffect(() => {
    let alive = true;
    let id: any;
    const loop = async () => {
      if (!alive) return;
      if (document.visibilityState !== "hidden") await poll();
      id = setTimeout(loop, Date.now() < fastUntil.current ? 1500 : 3000);
    };
    loop();
    return () => {
      alive = false;
      clearTimeout(id);
    };
  }, [poll]);

  const say = (text: string, warn = false) => setToast({ text, warn, at: Date.now() });

  const act = useCallback(
    async (a: any): Promise<{ ok: boolean; message?: string; error?: string }> => {
      const k = store.get();
      if (!k) {
        setUnlockOpen(true);
        return { ok: false, error: "Controls are locked." };
      }
      setBusy(a.type);
      try {
        const r = await fetch("/api/control", {
          method: "POST",
          headers: { "Content-Type": "application/json", "x-jarvis-key": k },
          body: JSON.stringify(a),
        });
        const j = await r.json();
        if (r.status === 401) {
          store.set(null);
          setKey(null);
          setUnlockOpen(true);
        }
        say(j.ok ? j.message : j.error, !j.ok);
        fastUntil.current = Date.now() + 25000;
        setTimeout(poll, 600);
        return j;
      } catch (e: any) {
        say(`Couldn't reach the server: ${e.message}`, true);
        return { ok: false, error: e.message };
      } finally {
        setBusy(null);
      }
    },
    [poll],
  );

  /* ── derived values ── */
  const status: string = link === "lost" && !s ? "OFFLINE" : s?.status || "BOOTING";
  const warn = status === "KILLED" || status === "OFFLINE";
  const task = s?.task;
  const steps: any[] = task?.steps || [];
  const doneSteps = steps.filter((x) => x.status === "success" || x.status === "completed").length;
  const progress = task?.kind === "draft" || task?.kind === "reply" ? (steps.length ? (doneSteps + 0.5) / steps.length : 0.04) : null;
  const uptime = s?.onlineSince && status !== "KILLED" && status !== "PAUSED" ? dur(now - Date.parse(s.onlineSince)) : "--:--:--";
  const nextMs = s?.nextPost ? Date.parse(s.nextPost) - now : null;
  const queue: any[] = s?.queue || [];
  const q = queue[Math.min(sel, Math.max(0, queue.length - 1))];
  const er = s?.audience?.engagementRate ?? null;
  const errs: any[] = s?.errors || [];

  // countdown progress through the current window between scheduled runs
  const windowPct = useMemo(() => {
    if (!s?.nextPost) return 0;
    const next = Date.parse(s.nextPost);
    const h = new Date(next).getUTCHours();
    const span = (h === 13 ? 15 : 9) * 3600e3; // 22:07 -> 13:07 is 15h, 13:07 -> 22:07 is 9h
    return Math.max(0, Math.min(1, 1 - (next - now) / span));
  }, [s?.nextPost, now]);

  /* ── big readout in the task block ── */
  let bigNum = "--";
  let bigLbl = "IDLE";
  if (task?.kind === "draft" || task?.kind === "reply") {
    bigNum = `${pad(Math.min(doneSteps + 1, Math.max(steps.length, 1)))}/${pad(Math.max(steps.length, 1))}`;
    bigLbl = "STEP";
  } else if (task?.kind === "waiting") {
    bigNum = `#${queue[0]?.issue ?? "--"}`;
    bigLbl = "DRAFT READY";
  } else if (nextMs != null) {
    bigNum = `${pad(nextMs / 3600e3)}:${pad((nextMs % 3600e3) / 60e3)}`;
    bigLbl = "T-MINUS NEXT RUN";
  }

  const logLines: any[] = s?.log || [];
  const runs: any[] = s?.runs || [];
  const published: any[] = s?.published || [];
  const engSeries = published.slice().reverse().map((p) => p.likes + p.comments);

  if (!mounted) return <div className="viewport" />;
  return (
    <div className="viewport">
      <div className={`stage ${still ? "still" : ""} ${warn ? "alarm" : ""}`} style={{ transform: `translate(-50%, -50%) scale(${scale})` }}>
        <Background />
        <Visor />

        {/* ── top bar ── */}
        <div className="wordmark glow">
          <svg width="46" height="46" viewBox="0 0 46 46">
            <circle cx="23" cy="23" r="21" className="s2" />
            <circle cx="23" cy="23" r="14" className="s1 o60" strokeDasharray="3 3" />
            <path d="M23 9v10M23 27v10M9 23h10M27 23h10" className="s3" />
            <circle cx="23" cy="23" r="3" className="fill3" />
          </svg>
          <div>
            <div className="wm">JARVIS</div>
            <div className="wm-sub">AI CLUB ∙ INSTAGRAM AGENT ∙ MISSION CONTROL</div>
          </div>
        </div>
        <div className="capsules">
          <div className="cap">
            <span className="lbl">TIME</span>
            <span className="val">{fmtTime(now)}</span>
            <span className="lbl">ET</span>
          </div>
          <div className="cap">
            <span className="val">{fmtDate(now)}</span>
          </div>
          <div className={`cap ${link === "lost" ? "amber" : ""}`}>
            <span className={`dot ${link === "live" ? "on" : link === "lost" ? "bad" : ""}`} />
            <span className="lbl">{link === "live" ? "LINK LIVE" : link === "lost" ? "LINK LOST" : "LINKING"}</span>
          </div>
        </div>
        <div className="topright">
          <button className={`chip ${key ? "on" : ""}`} onClick={() => (key ? (store.set(null), setKey(null), say("Controls locked.")) : setUnlockOpen(true))}>
            {key ? "CONTROLS ARMED" : "CONTROLS LOCKED"}
          </button>
        </div>

        {/* ── far left meter ── */}
        <Meter value={er} followers={s?.audience?.followers ?? null} />

        {/* ── current task ── */}
        <Panel x={150} y={112} w={440} h={330} title="CURRENT TASK" pulse={task?.title} right={<span className={`tag ${status === "WORKING" ? "on" : ""}`}>{task?.kind?.toUpperCase() || "--"}</span>}>
          <div className="bignum">{bigNum}</div>
          <div className="biglbl">{bigLbl}</div>
          <div className="headline">{task?.headline || "ESTABLISHING LINK"}</div>
          <div className="tasktitle">{task?.title || "Waiting for first telemetry…"}</div>
          <div className="reason">
            {(task?.reasoning || []).map((r: string, i: number) => (
              <div key={i}>
                <span className="dim">{pad(i + 1)}</span> {r}
              </div>
            ))}
          </div>
          {steps.length > 0 && (
            <div className="steps">
              {steps.map((st: any, i: number) => (
                <span key={i} className={`stp ${st.status}`} title={st.name}>
                  {st.name}
                </span>
              ))}
            </div>
          )}
        </Panel>

        {/* ── queue radial ── */}
        <QueueRadial
          queue={queue}
          sel={sel}
          setSel={setSel}
          q={q}
          act={act}
          busy={busy}
          requireApproval={s?.settings?.requireApproval ?? true}
        />

        {/* ── system / errors ── */}
        <Panel x={40} y={905} w={550} h={110} title="SYSTEM" warn={errs.length > 0 || link === "lost"} pulse={errs.length}>
          <div className="sys">
            {link === "lost" && <div className="amber">› DASHBOARD SERVER UNREACHABLE. SHOWING LAST KNOWN STATE.</div>}
            {errs.slice(0, 2).map((e, i) => (
              <div key={i} className="amber">
                › {e.source.toUpperCase()}: {e.msg.slice(0, 90)}
              </div>
            ))}
            {s?.lastRun?.conclusion === "failure" && <div className="amber">› LAST RUN FAILED: {s.lastRun.name}</div>}
            {!errs.length && link !== "lost" && s?.lastRun?.conclusion !== "failure" && <div>› ALL SYSTEMS NOMINAL</div>}
            <div className="dim">
              › REPO {s?.repo || "--"} ∙ SYNC {lastSync ? fmtTime(lastSync) : "--"}
            </div>
          </div>
        </Panel>

        {/* ── center core ── */}
        <div className="core-wrap" style={{ left: 660, top: 60 }}>
          <Core status={status} uptime={uptime} progress={progress} stepLabel={task?.title?.toUpperCase() || ""} still={still} />
        </div>

        {/* ── activity log ── */}
        <Panel x={620} y={660} w={680} h={228} title="ACTIVITY LOG" right={<span className="tag">{logLines.length} EVENTS</span>}>
          <div className="log">
            {logLines.slice(0, 9).map((l) => (
              <div key={l.t + l.text} className={`ll ${l.level}`}>
                <span className="lt">
                  {fmtShortDate(l.t)} {fmtTime(l.t)}
                </span>
                <span className="lx">{l.text}</span>
              </div>
            ))}
            {!logLines.length && <div className="ll dim">AWAITING TELEMETRY…</div>}
          </div>
        </Panel>

        {/* ── bottom stats bar ── */}
        <section className="stats" style={{ left: 620, top: 900, width: 680, height: 118 }}>
          <div className="pips">
            {Array.from({ length: 20 }).map((_, i) => {
              const r = runs[19 - i];
              const c = !r ? "" : r.status !== "completed" ? "run" : r.conclusion === "success" ? "ok" : r.conclusion === "failure" ? "bad" : "meh";
              return <span key={i} className={`pip ${c}`} title={r ? `${r.name} ∙ ${r.conclusion || r.status}` : ""} />;
            })}
            <span className="pipl">LAST 20 RUNS</span>
          </div>
          <div className="cols">
            <div>
              <Row l="POSTS SHIPPED" v={<Num v={s?.stats?.shipped} />} />
              <Row l="API COST TOTAL" v={<Num v={s?.stats?.cost} d={2} prefix="$" />} note={s?.stats?.costEstimated ? "EST" : ""} />
              <Row l="COST / POST" v={s?.stats?.costPerPost == null ? <span className="dim">--</span> : <Num v={s.stats.costPerPost} d={3} prefix="$" />} />
            </div>
            <div>
              <Row l="TOKENS USED" v={<Num v={s?.stats?.tokens} />} />
              <Row l="QUEUE DEPTH" v={<Num v={s?.stats?.queueDepth} />} />
              <Row l="ERRORS" v={<Num v={s?.stats?.errors} />} warn={(s?.stats?.errors || 0) > 0} />
            </div>
          </div>
        </section>

        {/* ── right: radar ── */}
        <div className="radar" style={{ left: 1350, top: 100 }}>
          <svg width={320} height={320} className="glow radar-ring">
            <circle cx={160} cy={160} r={158} className="s1 o40" strokeDasharray="1 5" />
            <path d="M160 0v10M160 310v10M0 160h10M310 160h10" className="s2" />
          </svg>
          <div style={{ position: "absolute", left: 10, top: 10 }}>
            <Globe size={300} countries={s?.audience?.countries || null} still={still} />
          </div>
          <div className="radar-lbl">AUDIENCE REACH ∙ {s?.audience?.countries ? "BY COUNTRY" : "AMBIENT"}</div>
        </div>
        <div className="readouts" style={{ left: 1680, top: 120 }}>
          <RO l="FOLLOWERS" v={<Num v={s?.audience?.followers} />} />
          <RO l="REACH 24H" v={s?.audience?.reach == null ? <span className="dim">N/A</span> : <Num v={s.audience.reach} />} />
          <RO l="POSTS LIVE" v={<Num v={s?.audience?.mediaCount} />} />
          <RO l="ENGAGEMENT" v={er == null ? <span className="dim">--</span> : <Num v={er} d={1} suffix="%" />} />
          <RO l="HOME BASE" v={<span className="small">28.49N 81.53W</span>} />
        </div>

        {/* ── right capsule: countdown ── */}
        <div className="capsule glow-box" style={{ left: 1806, top: 104 }}>
          <svg viewBox="0 0 24 24" width="26" height="26" className="cap-icon">
            <path d="M3 11.5 21 3l-6.5 18-3.2-7.3L3 11.5Z" />
            <path d="M11.3 13.7 21 3" />
          </svg>
          <div className="cap-pct">{s?.nextPost ? `${Math.round(windowPct * 100)}%` : "--"}</div>
          <div className="cap-bar">
            <div className="cap-fill" style={{ height: `${windowPct * 100}%` }} />
            {Array.from({ length: 12 }).map((_, i) => (
              <span key={i} className="cap-tick" style={{ bottom: `${(i / 12) * 100}%` }} />
            ))}
          </div>
          <div className="cap-time">{nextMs == null ? "HOLD" : `${pad(nextMs / 3600e3)}:${pad((nextMs % 3600e3) / 60e3)}:${pad((nextMs % 60e3) / 1e3)}`}</div>
          <div className="cap-lbl">NEXT POST</div>
        </div>

        {/* ── settings toggles ── */}
        <Panel x={1340} y={452} w={262} h={162} title="SETTINGS" pulse={JSON.stringify(s?.settings)}>
          <div className="toggles">
            <Toggle
              l="REQUIRE APPROVAL"
              on={s?.settings?.requireApproval ?? true}
              click={(on) => (on ? act({ type: "require_approval", value: true }) : act({ type: "require_approval", value: false }))}
              confirmOff
            />
            <Toggle l="AUTO SCHEDULE" on={!!s?.settings?.schedule} click={(on) => act({ type: on ? "resume" : "pause" })} />
            <Toggle l="REPLY HANDLER" on={!!s?.settings?.replies} info />
            <Toggle l="INSTAGRAM LINK" on={!!s?.settings?.igLinked} info />
            <Toggle l="VOICE SYNTH" on={!!s?.settings?.voice} info />
          </div>
        </Panel>

        {/* ── controls ── */}
        <div className="controls" style={{ left: 1618, top: 452, width: 262 }}>
          <ArmButton
            className="ctl"
            label={busy === "generate" ? "STARTING…" : "GENERATE POST NOW"}
            armed="CONFIRM: GENERATE"
            onFire={() => act({ type: "generate" })}
            disabled={status === "KILLED" || status === "PAUSED"}
          />
          <button className="ctl" onClick={() => act({ type: status === "PAUSED" ? "resume" : "pause" })} disabled={status === "KILLED"}>
            {status === "PAUSED" ? "▶ RESUME SCHEDULE" : "❚❚ PAUSE SCHEDULE"}
          </button>
          {status === "KILLED" ? (
            <HoldButton label="RESTORE AGENT" sub="HOLD TO RESTORE" onDone={() => act({ type: "restore" })} />
          ) : (
            <HoldButton label="⚠ KILL SWITCH" amber sub="HOLD TO STOP EVERYTHING" onDone={() => act({ type: "kill" })} />
          )}
        </div>

        {/* ── published ── */}
        <Panel x={1340} y={628} w={540} h={156} title="PUBLISHED" right={<Spark data={engSeries} w={120} h={16} />} pulse={published[0]?.id}>
          <div className="pubs">
            {published.slice(0, 5).map((p, i) => (
              <a key={p.id} className="pub" href={p.permalink} target="_blank" rel="noreferrer">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={p.image} alt="" referrerPolicy="no-referrer" />
                <div className="pub-meta">
                  <span>♥ {p.likes}</span>
                  <span>✎ {p.comments}</span>
                </div>
                <Spark data={engSeries.slice(0, engSeries.length - i)} w={92} h={10} />
              </a>
            ))}
            {!published.length && <div className="dim pad">{s?.settings?.igLinked === false ? "INSTAGRAM LINK DOWN" : "NO POSTS YET"}</div>}
          </div>
        </Panel>

        {/* ── voice ── */}
        <section className="voice-wrap" style={{ left: 1340, top: 796, width: 540, height: 150 }}>
          <Voice
            getKey={() => store.get()}
            needUnlock={() => setUnlockOpen(true)}
            runAction={act}
            enabled={!!s?.settings?.voice}
            still={still}
          />
        </section>

        {/* ── round icon buttons ── */}
        <IconRow
          onFull={() => {
            if (document.fullscreenElement) document.exitFullscreen?.();
            else document.documentElement.requestFullscreen?.().catch(() => {});
          }}
          onMic={() => window.dispatchEvent(new Event("jarvis:mic"))}
          onBrief={() => window.dispatchEvent(new Event("jarvis:brief"))}
          onRefresh={() => {
            poll();
            say("Telemetry refreshed.");
          }}
          onLock={() => (key ? (store.set(null), setKey(null), say("Controls locked.")) : setUnlockOpen(true))}
          locked={!key}
          repo={s?.repo}
        />

        {/* ── toast ── */}
        {toast && Date.now() - toast.at < 7000 && (
          <div key={toast.at} className={`toast ${toast.warn ? "warn" : ""}`}>
            › {toast.text}
          </div>
        )}

        {status === "KILLED" && <div className="banner">KILL SWITCH ENGAGED ∙ AGENT HALTED ∙ NOTHING CAN POST</div>}
        {link === "lost" && s && <div className="banner soft">TELEMETRY LINK LOST ∙ RETRYING</div>}

        {unlockOpen && (
          <Unlock
            onClose={() => setUnlockOpen(false)}
            onOk={(k) => {
              store.set(k);
              setKey(k);
              setUnlockOpen(false);
              say("Controls armed.");
            }}
          />
        )}

        <div className="scan" />
      </div>
    </div>
  );
}

/* ───────────────────────── sub-panels ───────────────────────── */

function Row({ l, v, note, warn }: { l: string; v: React.ReactNode; note?: string; warn?: boolean }) {
  return (
    <div className={`row ${warn ? "amber" : ""}`}>
      <span className="rl">{l}</span>
      <span className="rdots" />
      <span className="rv">
        {v}
        {note && <em>{note}</em>}
      </span>
    </div>
  );
}

function RO({ l, v }: { l: string; v: React.ReactNode }) {
  return (
    <div className="ro">
      <div className="rol">{l}</div>
      <div className="rov">{v}</div>
    </div>
  );
}

function Toggle({ l, on, click, info, confirmOff }: { l: string; on: boolean; click?: (next: boolean) => void; info?: boolean; confirmOff?: boolean }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(t);
  }, [armed]);
  return (
    <button
      className={`tg ${on ? "on" : ""} ${info ? "info" : ""} ${armed ? "armed" : ""}`}
      disabled={info}
      onClick={() => {
        if (!click) return;
        if (confirmOff && on && !armed) return setArmed(true);
        setArmed(false);
        click(!on);
      }}
    >
      <span className={`dot ${on ? "on" : ""}`} />
      <span className="tl">{armed ? "TAP AGAIN: TURN OFF?" : l}</span>
      {!info ? (
        <span className="sw">
          <span className="kn" />
        </span>
      ) : (
        <span className="tv">{on ? "OK" : "OFF"}</span>
      )}
    </button>
  );
}

function Spark({ data, w, h }: { data: number[]; w: number; h: number }) {
  if (data.length < 2) return <svg width={w} height={h}><path d={`M0 ${h - 1}H${w}`} className="s1 o40" /></svg>;
  const max = Math.max(1, ...data);
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - 1 - (v / max) * (h - 2)}`);
  return (
    <svg width={w} height={h} className="spark">
      <polyline points={pts.join(" ")} className="s2" />
      <circle cx={w} cy={h - 1 - (data[data.length - 1] / max) * (h - 2)} r={1.8} className="fill3" />
    </svg>
  );
}

function Meter({ value, followers }: { value: number | null; followers: number | null }) {
  const MAX = 20;
  const top = 150, bottom = 830, H = bottom - top;
  const v = useTween(value ?? 0, 1400);
  const y = bottom - (Math.min(MAX, v) / MAX) * H;
  const ticks: React.ReactNode[] = [];
  for (let i = 0; i <= MAX * 2; i++) {
    const yy = bottom - (i / (MAX * 2)) * H;
    const major = i % 10 === 0;
    ticks.push(<path key={i} d={`M${major ? 52 : 60} ${yy}H70`} className={major ? "s2" : "s1 o50"} />);
    if (major) ticks.push(<text key={`t${i}`} x={44} y={yy + 4} className="mtxt" textAnchor="end">{i / 2}</text>);
  }
  return (
    <div className="meter">
      <svg width={130} height={900} className="glow">
        <text x={20} y={128} className="mhead">ENGAGEMENT</text>
        <path d={`M76 ${top}V${bottom}`} className="s1 o60" />
        <path d={`M82 ${top}V${bottom}`} className="s1 o20" strokeDasharray="2 4" />
        {ticks}
        <rect x={74} y={y} width={4} height={bottom - y} className="fill2 o50" />
        <g transform={`translate(0 ${y})`} className="mind">
          <path d="M70 0l12 -7v14z" className="fill3" />
          <path d="M84 0H96" className="s3" />
          <rect x={96} y={-11} width={34} height={22} className="s2 flagbg" />
          <text x={113} y={4} textAnchor="middle" className="mflag">{value == null ? "--" : `${value.toFixed(1)}%`}</text>
        </g>
        <text x={20} y={862} className="mtxt">FOLLOWERS</text>
        <text x={20} y={886} className="mbig">{compact(followers)}</text>
      </svg>
    </div>
  );
}

function QueueRadial({ queue, sel, setSel, q, act, busy, requireApproval }: any) {
  const R = 84;
  const [rev, setRev] = useState("");
  const [slide, setSlide] = useState(0);
  useEffect(() => {
    setSlide(0);
  }, [q?.issue, q?.version]);
  useEffect(() => {
    if (!q?.slides?.length) return;
    const id = setInterval(() => setSlide((x) => (x + 1) % q.slides.length), 2600);
    return () => clearInterval(id);
  }, [q?.slides?.length]);
  const items = queue.slice(0, 5);
  const n = Math.max(1, items.length);
  const angles = items.map((_: any, i: number) => (n === 1 ? 0 : -50 + (100 * i) / (n - 1)));
  return (
    <>
      <div className="qradial" style={{ left: 150, top: 452, width: 450, height: 230 }}>
        <svg width={450} height={230} className="glow" style={{ overflow: "visible" }}>
          <g transform="translate(95 118)">
            <circle r={R} className="s1 o40" />
            <circle r={R - 14} className="s2 o70 spin-cw" strokeDasharray="20 6 4 6" style={{ transformOrigin: "center", transformBox: "fill-box" }} />
            <circle r={R - 34} className="s1 o40 spin-ccw" strokeDasharray="1 4" style={{ transformOrigin: "center", transformBox: "fill-box" }} />
            <circle r={R + 10} className="s1 o20" />
            <text y={-6} textAnchor="middle" className="qnum">{pad(queue.length)}</text>
            <text y={16} textAnchor="middle" className="qlbl">IN QUEUE</text>
            <text y={32} textAnchor="middle" className="qlbl dim">{requireApproval ? "APPROVAL ON" : "AUTO-POST"}</text>
            {items.map((it: any, i: number) => {
              const a = (angles[i] * Math.PI) / 180;
              const x1 = Math.cos(a) * (R + 10), y1 = Math.sin(a) * (R + 10);
              const x2 = Math.cos(a) * (R + 40), y2 = Math.sin(a) * (R + 40);
              const on = i === sel;
              return (
                <g key={it.issue} className={`fan ${on ? "on" : ""}`} onClick={() => setSel(i)} style={{ cursor: "pointer" }}>
                  <path d={`M${x1} ${y1}L${x2} ${y2}H${x2 + 18}`} className={on ? "s3" : "s1 o60"} />
                  <circle cx={x1} cy={y1} r={on ? 4 : 2.5} className="fill3" />
                  <text x={x2 + 24} y={y2 + 4} className="fanl">
                    #{it.issue} {it.title.toUpperCase().slice(0, 24)}
                    {it.title.length > 24 ? "…" : ""}
                  </text>
                  <text x={x2 + 24} y={y2 + 18} className="fans">
                    V{it.version} ∙ {String(it.format || "").toUpperCase()} ∙ {it.slides.length} SLIDES
                  </text>
                </g>
              );
            })}
            {!items.length && (
              <g>
                <path d={`M${R + 10} 0H${R + 60}`} className="s1 o40" />
                <text x={R + 68} y={4} className="fanl dim">QUEUE CLEAR ∙ NOTHING WAITING</text>
              </g>
            )}
          </g>
        </svg>
        <div className="ph abs">POST QUEUE</div>
      </div>
      <Panel x={150} y={690} w={440} h={200} pulse={q ? `${q.issue}-${q.version}` : "none"} className="qcard">
        {q ? (
          <div className="qc">
            <div className="qthumb">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={q.slides[slide] || q.thumb} alt="" />
              <div className="qdots">
                {q.slides.map((_: any, i: number) => (
                  <span key={i} className={i === slide ? "on" : ""} />
                ))}
              </div>
            </div>
            <div className="qbody">
              <div className="qt">
                <a href={q.url} target="_blank" rel="noreferrer">#{q.issue}</a> {q.title}
              </div>
              <div className="qcap">{q.caption.split("\n")[0]}</div>
              <div className="qbtns">
                <ArmButton
                  className="ctl sm"
                  label={busy === "approve" ? "SENDING…" : "✓ APPROVE"}
                  armed="CONFIRM POST"
                  onFire={() => act({ type: "approve", issue: q.issue })}
                />
                <ArmButton className="ctl sm" label="✕ REJECT" armed="CONFIRM REJECT" onFire={() => act({ type: "reject", issue: q.issue })} />
              </div>
              <form
                className="qrev"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!rev.trim()) return;
                  act({ type: "revise", issue: q.issue, text: rev });
                  setRev("");
                }}
              >
                <input value={rev} onChange={(e) => setRev(e.target.value)} placeholder="REQUEST CHANGES + ENTER" />
              </form>
            </div>
          </div>
        ) : (
          <div className="qempty">
            <div className="dim">NO DRAFTS WAITING.</div>
            <div className="dim small">New drafts appear here for approval. Press GENERATE POST NOW to make one.</div>
          </div>
        )}
      </Panel>
    </>
  );
}

function IconRow({ onFull, onMic, onBrief, onRefresh, onLock, locked, repo }: any) {
  const B = ({ x, y, t, onClick, children, href }: any) =>
    href ? (
      <a className="ib" style={{ left: x, top: y }} href={href} target="_blank" rel="noreferrer" title={t}>
        {children}
        <span className="ibl">{t}</span>
      </a>
    ) : (
      <button className="ib" style={{ left: x, top: y }} onClick={onClick} title={t}>
        {children}
        <span className="ibl">{t}</span>
      </button>
    );
  return (
    <>
      <B x={1360} y={962} t="FULL" onClick={onFull}>
        <svg viewBox="0 0 24 24"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" /></svg>
      </B>
      <B x={1440} y={970} t="TALK" onClick={onMic}>
        <svg viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" /></svg>
      </B>
      <B x={1520} y={966} t="BRIEF" onClick={onBrief}>
        <svg viewBox="0 0 24 24"><path d="M4 5h16v11H9l-5 4z" /><path d="M8 9h8M8 12h5" /></svg>
      </B>
      <B x={1600} y={958} t="SYNC" onClick={onRefresh}>
        <svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.3-5.6M20 4v5h-5" /></svg>
      </B>
      <B x={1680} y={950} t={locked ? "UNLOCK" : "LOCK"} onClick={onLock}>
        <svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="9" rx="1" /><path d={locked ? "M8 11V8a4 4 0 0 1 8 0v3" : "M8 11V8a4 4 0 0 1 7.5-2"} /></svg>
      </B>
      <B x={1760} y={940} t="REPO" href={repo ? `https://github.com/${repo}/issues` : undefined}>
        <svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="2.2" /><circle cx="6" cy="18" r="2.2" /><circle cx="18" cy="9" r="2.2" /><path d="M6 8.2v7.6M18 11.2c0 3-6 2.5-10.5 5.5" /></svg>
      </B>
    </>
  );
}

function Unlock({ onClose, onOk }: { onClose: () => void; onOk: (k: string) => void }) {
  const [v, setV] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="modal" onClick={onClose}>
      <form
        className="unlock"
        onClick={(e) => e.stopPropagation()}
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setErr("");
          try {
            const r = await fetch("/api/auth", { method: "POST", headers: { "x-jarvis-key": v } });
            const j = await r.json();
            if (j.ok) onOk(v);
            else setErr(j.error || "ACCESS DENIED");
          } catch {
            setErr("SERVER UNREACHABLE");
          }
          setBusy(false);
        }}
      >
        <div className="ph">
          <span>AUTHORIZATION REQUIRED</span>
        </div>
        <p className="dim">Enter the control password to arm approve, pause, kill switch and voice.</p>
        <input autoFocus type="password" value={v} onChange={(e) => setV(e.target.value)} placeholder="PASSWORD" />
        {err && <div className="amber small">{err}</div>}
        <div className="qbtns">
          <button className="ctl sm" type="submit" disabled={busy}>
            {busy ? "VERIFYING…" : "ARM CONTROLS"}
          </button>
          <button className="ctl sm" type="button" onClick={onClose}>
            CANCEL
          </button>
        </div>
      </form>
    </div>
  );
}

function Background() {
  return (
    <svg className="bg" width={1920} height={1080}>
      <defs>
        <pattern id="circ" width="120" height="120" patternUnits="userSpaceOnUse">
          <path d="M0 30h40l10 10h30M60 0v20l10 10v40M120 90H90l-10-10H50M20 120v-30l-10-10V60" className="s1" />
          <circle cx="80" cy="40" r="2" className="s1" />
          <circle cx="50" cy="80" r="2" className="s1" />
          <circle cx="10" cy="60" r="1.5" className="s1" />
        </pattern>
        <radialGradient id="vig" cx="50%" cy="45%" r="75%">
          <stop offset="0%" stopColor="#06213a" stopOpacity="0.55" />
          <stop offset="55%" stopColor="#020b16" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#000" stopOpacity="0.95" />
        </radialGradient>
      </defs>
      <rect width={1920} height={1080} fill="url(#vig)" />
      <rect width={1920} height={1080} fill="url(#circ)" opacity={0.05} />
      {Array.from({ length: 9 }).map((_, i) => (
        <ellipse key={i} cx={960} cy={420} rx={420 + i * 140} ry={260 + i * 95} className="s1" opacity={0.025} />
      ))}
    </svg>
  );
}

function Visor() {
  const top = "M30 110 Q960 -30 1890 110";
  const bot = "M30 1000 Q960 1110 1890 1000";
  return (
    <svg className="visor glow" width={1920} height={1080}>
      <path d={top} className="s2 o70" />
      <path d="M90 122 Q960 -12 1830 122" className="s1 o30" strokeDasharray="1 9" />
      <path d={bot} className="s2 o70" />
      <path d="M90 990 Q960 1090 1830 990" className="s1 o30" strokeDasharray="1 9" />
      {/* end hooks */}
      <path d="M30 110v40l14 14M1890 110v40l-14 14M30 1000v-40l14-14M1890 1000v-40l-14-14" className="s2" />
      {/* center notches */}
      <path d="M900 42h-60M1020 42h60M940 1055h-80M980 1055h80" className="s3 o80" strokeWidth={2} />
    </svg>
  );
}

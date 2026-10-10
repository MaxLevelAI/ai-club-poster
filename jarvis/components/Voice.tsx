"use client";
/**
 * VOICE PANEL
 * -----------
 * Talk to JARVIS. The pipeline is three swappable pieces:
 *   1. Ears   : the browser's built-in speech recognition (Chrome / Edge). See `listen()`.
 *   2. Brain  : POST /api/voice/ask  -> OpenAI reads your words + the live HUD state and answers.
 *               It may propose an action (approve, pause, kill...). You confirm on screen
 *               (or say "confirm") before anything runs.
 *   3. Mouth  : POST /api/voice/speak -> ElevenLabs turns the answer into speech. See `speak()`.
 *               If ElevenLabs isn't set up, it falls back to the browser's own voice.
 * The waveform is drawn from a Web Audio analyser on whatever is active (your mic or JARVIS).
 */
import { useCallback, useEffect, useRef, useState } from "react";

type Msg = { role: "user" | "assistant"; content: string };
type Props = {
  getKey: () => string | null;
  needUnlock: () => void;
  runAction: (a: any) => Promise<{ ok: boolean; message?: string; error?: string }>;
  enabled: boolean;
  still: boolean;
};

const CONFIRM = /^(yes|yeah|yep|confirm|confirmed|do it|go ahead|affirmative|proceed|execute)\b/i;
const CANCEL = /^(no|nope|cancel|stop|never ?mind|abort)\b/i;

function describe(a: any) {
  if (!a) return "";
  switch (a.type) {
    case "approve": return `APPROVE + POST #${a.issue}`;
    case "reject": return `REJECT #${a.issue}`;
    case "revise": return `REVISE #${a.issue}: ${a.text}`;
    case "generate": return `GENERATE POST${a.topic ? `: ${a.topic}` : ""}`;
    case "require_approval": return `REQUIRE APPROVAL → ${a.value ? "ON" : "OFF"}`;
    case "kill": return "KILL SWITCH";
    default: return String(a.type).toUpperCase();
  }
}

export default function Voice({ getKey, needUnlock, runAction, enabled, still }: Props) {
  const [mode, setMode] = useState<"idle" | "listening" | "thinking" | "speaking">("idle");
  const [heard, setHeard] = useState("");
  const [said, setSaid] = useState("Say “Jarvis, status report” or press the mic.");
  const [pending, setPending] = useState<any>(null);
  const [typed, setTyped] = useState("");
  const history = useRef<Msg[]>([]);
  const canvas = useRef<HTMLCanvasElement>(null);
  const actx = useRef<AudioContext | null>(null);
  const analyser = useRef<AnalyserNode | null>(null);
  const audioEl = useRef<HTMLAudioElement | null>(null);
  const micStream = useRef<MediaStream | null>(null);
  const micSrc = useRef<MediaStreamAudioSourceNode | null>(null);
  const rec = useRef<any>(null);
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const pendingRef = useRef(pending);
  pendingRef.current = pending;

  const audio = useCallback(() => {
    if (!actx.current) {
      const AC = (window as any).AudioContext || (window as any).webkitAudioContext;
      actx.current = new AC();
      analyser.current = actx.current!.createAnalyser();
      analyser.current.fftSize = 1024;
      const el = new Audio();
      el.crossOrigin = "anonymous";
      audioEl.current = el;
      const src = actx.current!.createMediaElementSource(el);
      src.connect(analyser.current);
      analyser.current.connect(actx.current!.destination);
    }
    actx.current!.resume?.();
    return actx.current!;
  }, []);

  // ---- 3. Mouth ----
  const speak = useCallback(
    async (text: string) => {
      setSaid(text);
      setMode("speaking");
      try {
        audio();
        const res = await fetch("/api/voice/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json", "x-jarvis-key": getKey() || "" },
          body: JSON.stringify({ text }),
        });
        if (!res.ok) throw new Error("tts");
        const blob = await res.blob();
        const el = audioEl.current!;
        el.src = URL.createObjectURL(blob);
        await el.play();
        await new Promise<void>((r) => {
          el.onended = () => r();
          el.onerror = () => r();
        });
      } catch {
        // Fallback: the browser's built-in voice.
        await new Promise<void>((r) => {
          try {
            const u = new SpeechSynthesisUtterance(text);
            u.rate = 1.02;
            u.onend = () => r();
            u.onerror = () => r();
            speechSynthesis.speak(u);
          } catch {
            r();
          }
        });
      }
      setMode("idle");
    },
    [audio, getKey],
  );

  const doAction = useCallback(
    async (a: any) => {
      setPending(null);
      const r = await runAction(a);
      await speak(r.ok ? r.message || "Done." : `That didn't work. ${r.error || ""}`);
    },
    [runAction, speak],
  );

  // ---- 2. Brain ----
  const ask = useCallback(
    async (text: string) => {
      text = text.trim();
      if (!text) return;
      if (!getKey()) return needUnlock();
      setHeard(text);
      if (pendingRef.current) {
        if (CONFIRM.test(text)) return doAction(pendingRef.current);
        if (CANCEL.test(text)) {
          setPending(null);
          return speak("Cancelled.");
        }
      }
      setMode("thinking");
      try {
        const res = await fetch("/api/voice/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json", "x-jarvis-key": getKey() || "" },
          body: JSON.stringify({ text, history: history.current }),
        });
        const j = await res.json();
        if (res.status === 401) {
          setMode("idle");
          return needUnlock();
        }
        if (!j.ok) throw new Error(j.error);
        history.current = [...history.current, { role: "user" as const, content: text }, { role: "assistant" as const, content: j.say }].slice(-10);
        setPending(j.action || null);
        await speak(j.say);
      } catch (e: any) {
        setMode("idle");
        setSaid(`Brain offline: ${e.message || e}`);
      }
    },
    [getKey, needUnlock, doAction, speak],
  );

  // ---- 1. Ears ----
  const stopMic = () => {
    try {
      rec.current?.stop();
    } catch {}
    micSrc.current?.disconnect();
    micStream.current?.getTracks().forEach((t) => t.stop());
    micStream.current = null;
  };
  const listen = useCallback(async () => {
    if (!getKey()) return needUnlock();
    if (modeRef.current === "listening") {
      stopMic();
      setMode("idle");
      return;
    }
    if (modeRef.current === "speaking") {
      audioEl.current?.pause();
      speechSynthesis.cancel?.();
    }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      setSaid("This browser can't hear. Use Chrome or Edge, or type below.");
      return;
    }
    const ctx = audio();
    try {
      micStream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      micSrc.current = ctx.createMediaStreamSource(micStream.current);
      micSrc.current.connect(analyser.current!); // drawn only; analyser -> speakers is muted by gain below
    } catch {}
    const r = new SR();
    rec.current = r;
    r.lang = "en-US";
    r.interimResults = true;
    r.continuous = false;
    let final = "";
    r.onresult = (e: any) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t;
        else interim += t;
      }
      setHeard((final + interim).trim());
    };
    r.onerror = (e: any) => {
      if (e.error === "not-allowed") setSaid("Microphone blocked. Allow it in the address bar, then try again.");
    };
    r.onend = () => {
      stopMic();
      if (final.trim()) ask(final.replace(/^(hey |ok )?jarvis[,.]?\s*/i, "") || final);
      else if (modeRef.current === "listening") setMode("idle");
    };
    setHeard("");
    setMode("listening");
    r.start();
  }, [ask, audio, getKey, needUnlock]);

  // Let the round mic button / spacebar trigger it.
  useEffect(() => {
    const f = () => listen();
    window.addEventListener("jarvis:mic", f);
    const k = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.code === "Space" && tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        listen();
      }
    };
    window.addEventListener("keydown", k);
    const b = () => ask("Give me a quick status briefing.");
    window.addEventListener("jarvis:brief", b);
    return () => {
      window.removeEventListener("jarvis:mic", f);
      window.removeEventListener("keydown", k);
      window.removeEventListener("jarvis:brief", b);
    };
  }, [listen, ask]);

  // Waveform
  useEffect(() => {
    const c = canvas.current!;
    const ctx = c.getContext("2d")!;
    const W = 330, H = 64;
    c.width = W * 2;
    c.height = H * 2;
    ctx.scale(2, 2);
    const buf = new Uint8Array(1024);
    let raf = 0;
    const draw = (t: number) => {
      ctx.clearRect(0, 0, W, H);
      const live = analyser.current && (modeRef.current === "speaking" || modeRef.current === "listening");
      if (live) analyser.current!.getByteTimeDomainData(buf);
      const bars = 66;
      for (let i = 0; i < bars; i++) {
        let v: number;
        if (live) {
          let m = 0;
          const span = Math.floor(buf.length / bars);
          for (let j = 0; j < span; j++) m = Math.max(m, Math.abs(buf[i * span + j] - 128));
          v = Math.min(1, m / 70);
        } else {
          const thinking = modeRef.current === "thinking";
          v = 0.04 + 0.05 * Math.abs(Math.sin(t / (thinking ? 120 : 700) + i * 0.45)) + (thinking ? 0.12 * Math.abs(Math.sin(t / 200 + i)) : 0);
        }
        const h = Math.max(1.5, v * (H - 6));
        const x = i * (W / bars);
        const mid = Math.abs(i - bars / 2) / (bars / 2);
        ctx.fillStyle = `rgba(57,199,255,${0.35 + 0.65 * (1 - mid) * (live ? 1 : 0.6)})`;
        ctx.fillRect(x, H / 2 - h / 2, W / bars - 1.6, h);
      }
      if (!still) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [still]);

  // Mic audio must not play through the speakers: route analyser -> gain(0) for mic.
  // (Simple approach: when listening, mute output; restore when done.)
  useEffect(() => {
    if (!actx.current || !analyser.current) return;
    try {
      analyser.current.disconnect();
      if (mode !== "listening") analyser.current.connect(actx.current.destination);
    } catch {}
  }, [mode]);

  const label = { idle: "STANDBY", listening: "LISTENING", thinking: "PROCESSING", speaking: "SPEAKING" }[mode];

  return (
    <div className="voice">
      <div className="ph">
        <span>VOICE LINK</span>
        <span className={`tag ${mode !== "idle" ? "on" : ""}`}>{enabled ? label : "TEXT ONLY"}</span>
      </div>
      <div className="voice-row">
        <button className={`mic ${mode === "listening" ? "live" : ""}`} onClick={listen} title="Talk (Space)">
          <svg viewBox="0 0 24 24" width="22" height="22">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" />
          </svg>
        </button>
        <canvas ref={canvas} style={{ width: 330, height: 64 }} />
      </div>
      <div className="voice-lines">
        {heard && <div className="you">› {heard}</div>}
        <div className="jv">{said}</div>
      </div>
      {pending && (
        <div className="voice-confirm">
          <span>PROPOSED: {describe(pending)}</span>
          <button className={pending.type === "kill" ? "amberbtn" : ""} onClick={() => doAction(pending)}>
            CONFIRM
          </button>
          <button onClick={() => setPending(null)}>CANCEL</button>
        </div>
      )}
      <form
        className="voice-type"
        onSubmit={(e) => {
          e.preventDefault();
          const t = typed;
          setTyped("");
          ask(t);
        }}
      >
        <span>›</span>
        <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="TYPE A COMMAND…" />
      </form>
    </div>
  );
}

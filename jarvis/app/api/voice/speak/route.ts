// JARVIS's voice: text -> ElevenLabs speech (MP3). The key never leaves the server.
import { authorized, deny } from "@/lib/auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req: Request) {
  if (!authorized(req)) return deny();
  const key = process.env.ELEVENLABS_API_KEY;
  if (!key) return Response.json({ ok: false, error: "ELEVENLABS_API_KEY isn't set." }, { status: 501 });
  const { text } = await req.json();
  const voice = process.env.ELEVENLABS_VOICE_ID || "JBFqnCBsd6RMkjVDRZzb";
  const res = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${voice}?output_format=mp3_44100_128`, {
    method: "POST",
    headers: { "xi-api-key": key, "Content-Type": "application/json", Accept: "audio/mpeg" },
    body: JSON.stringify({
      text: String(text || "").slice(0, 800),
      model_id: process.env.ELEVENLABS_MODEL || "eleven_flash_v2_5",
      voice_settings: { stability: 0.5, similarity_boost: 0.75, style: 0.15, speed: 1.0 },
    }),
  });
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => "");
    return Response.json({ ok: false, error: `ElevenLabs ${res.status}: ${t.slice(0, 200)}` }, { status: 502 });
  }
  return new Response(res.body, { headers: { "Content-Type": "audio/mpeg", "Cache-Control": "no-store" } });
}

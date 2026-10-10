import { buildState } from "@/lib/state";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try {
    const state = await buildState();
    return Response.json(state, { headers: { "Cache-Control": "no-store" } });
  } catch (e: any) {
    return Response.json({ fatal: true, error: e.message || String(e) }, { status: 200 });
  }
}

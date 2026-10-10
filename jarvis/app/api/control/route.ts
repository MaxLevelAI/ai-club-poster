import { authorized, deny } from "@/lib/auth";
import { runAction } from "@/lib/actions";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req: Request) {
  if (!authorized(req)) return deny();
  try {
    const action = await req.json();
    const message = await runAction(action);
    return Response.json({ ok: true, message });
  } catch (e: any) {
    return Response.json({ ok: false, error: e.message || String(e) }, { status: 400 });
  }
}

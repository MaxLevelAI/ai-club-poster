import { authorized } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  if (!process.env.CONTROL_PASSWORD) {
    return Response.json({ ok: false, error: "CONTROL_PASSWORD isn't set on the server yet." }, { status: 500 });
  }
  const ok = authorized(req);
  return Response.json({ ok }, { status: ok ? 200 : 401 });
}

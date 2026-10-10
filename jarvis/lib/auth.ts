import "server-only";
import { timingSafeEqual, createHash } from "crypto";

/** True when the request carries the right control password (header x-jarvis-key). */
export function authorized(req: Request) {
  const want = process.env.CONTROL_PASSWORD || "";
  const got = req.headers.get("x-jarvis-key") || "";
  if (!want) return false; // no password set = controls stay locked
  const a = createHash("sha256").update(want).digest();
  const b = createHash("sha256").update(got).digest();
  return timingSafeEqual(a, b);
}

export function deny() {
  return Response.json({ ok: false, error: "Locked. Enter the control password." }, { status: 401 });
}

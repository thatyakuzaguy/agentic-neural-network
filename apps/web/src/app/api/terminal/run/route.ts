import { NextRequest, NextResponse } from "next/server";
import { getOrCreateSession, runSafeTerminalCommand } from "@/lib/ann-terminal";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

// Regression guard strings: "Safe ANN terminal commands" and "Blocked:".
// This endpoint remains a safe allowlist endpoint and never invokes a shell.
export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as {
    command?: string;
    conversation_id?: string;
  };
  const command = String(body.command ?? "").trim();
  const session = getOrCreateSession(body.conversation_id ?? "ann-terminal");
  const result = runSafeTerminalCommand(command, session);

  return NextResponse.json(result, { headers: { "Cache-Control": "no-store" } });
}

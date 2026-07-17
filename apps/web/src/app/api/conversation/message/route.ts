import { NextRequest, NextResponse } from "next/server";
import {
  blockedShellAttemptResponse,
  classifyTerminalInput,
  getOrCreateSession,
  handleConversationMessage,
  handleModeCommand,
  runSafeTerminalCommand,
  type TerminalInputMode,
} from "@/lib/ann-terminal";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function isTerminalInputMode(value: unknown): value is TerminalInputMode {
  return value === "auto" || value === "chat" || value === "command";
}

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as {
    conversation_id?: string;
    message?: string;
    mode?: TerminalInputMode;
    active_project?: string | null;
  };

  const session = getOrCreateSession(body.conversation_id ?? "ann-terminal");
  if (isTerminalInputMode(body.mode)) session.currentMode = body.mode;
  if (typeof body.active_project === "string" && body.active_project.trim()) {
    session.activeProject = body.active_project.trim();
  }

  const message = String(body.message ?? "").trim();
  const classification = classifyTerminalInput(message, session.currentMode);

  if (classification === "EMPTY") {
    return NextResponse.json({
      status: "skipped",
      input_classification: classification,
      display_message: "",
      events: [],
    }, { headers: { "Cache-Control": "no-store" } });
  }

  if (classification === "MALFORMED_INPUT") {
    return NextResponse.json({
      status: "blocked",
      input_classification: classification,
      display_message: "Blocked: input is not a registered ANN command in command mode.",
      events: [{ kind: "error", text: "Malformed or unsupported terminal input blocked." }],
    }, { headers: { "Cache-Control": "no-store" } });
  }

  if (classification === "EXPLICIT_SHELL_ATTEMPT") {
    return NextResponse.json(blockedShellAttemptResponse(message, session), {
      headers: { "Cache-Control": "no-store" },
    });
  }

  if (classification === "BUILTIN_COMMAND") {
    if (message.toLowerCase().startsWith("mode ") || message.toLowerCase().startsWith("chat")) {
      return NextResponse.json({
        ...handleModeCommand(message, session),
        input_classification: classification,
        terminal_status: { mode: session.currentMode },
      }, { headers: { "Cache-Control": "no-store" } });
    }
    const result = runSafeTerminalCommand(message, session);
    return NextResponse.json({
      status: "completed",
      input_classification: classification,
      display_message: result.lines.join("\n"),
      command_result: result,
      events: result.lines.map((text) => ({ kind: text.startsWith("Blocked:") ? "error" : "command", text })),
      terminal_status: { mode: session.currentMode },
    }, { headers: { "Cache-Control": "no-store" } });
  }

  if (classification === "ANN_SAFE_COMMAND") {
    const result = runSafeTerminalCommand(message, session);
    return NextResponse.json({
      status: "completed",
      input_classification: classification,
      display_message: result.lines.join("\n"),
      command_result: result,
      events: result.lines.map((text) => ({ kind: text.startsWith("Blocked:") ? "error" : "command", text })),
      terminal_status: { mode: session.currentMode },
    }, { headers: { "Cache-Control": "no-store" } });
  }

  return NextResponse.json(await handleConversationMessage(message, session), {
    headers: { "Cache-Control": "no-store" },
  });
}

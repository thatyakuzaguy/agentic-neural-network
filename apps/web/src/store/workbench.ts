import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { EngineeringRun } from "@/lib/api";

export type ConversationMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
};

export type ProgressEvent = {
  id: string;
  messageId: string;
  kind: "command" | "edit" | "analysis" | "approval";
  label: string;
};

type WorkbenchState = {
  activeRun: EngineeringRun | null;
  terminalLines: string[];
  messages: ConversationMessage[];
  progressEvents: ProgressEvent[];
  setActiveRun: (run: EngineeringRun) => void;
  appendTerminal: (line: string) => void;
  addMessage: (message: ConversationMessage) => void;
  addProgressEvent: (event: ProgressEvent) => void;
};

export const useWorkbench = create<WorkbenchState>()(
  persist(
    (set) => ({
      activeRun: null,
      terminalLines: [
        "ANN terminal is approval-gated.",
        "Commands are proposed for Docker sandbox execution before they can run."
      ],
      messages: [
        {
          id: "welcome",
          role: "assistant",
          text: "Describe what you want to build. I will plan, generate diffs, request approvals, and keep each action visible as the work progresses."
        }
      ],
      progressEvents: [],
      setActiveRun: (run) => set({ activeRun: run }),
      appendTerminal: (line) => set((state) => ({ terminalLines: [...state.terminalLines, line] })),
      addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
      addProgressEvent: (event) => set((state) => ({ progressEvents: [...state.progressEvents, event] }))
    }),
    {
      name: "aen-workbench-state",
      partialize: (state) => ({
        activeRun: state.activeRun,
        terminalLines: state.terminalLines,
        messages: state.messages,
        progressEvents: state.progressEvents
      })
    }
  )
);

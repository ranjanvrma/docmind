import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import { emit } from "@/lib/events";
import type { AskResponse } from "@/lib/types";

export interface ChatTurn {
  id: string;
  question: string;
  topK: number;
  docIds: string[];
  status: "pending" | "done" | "error";
  response?: AskResponse;
  error?: unknown;
}

interface ChatValue {
  turns: ChatTurn[];
  ask: (question: string, topK: number, docIds: string[]) => void;
  retry: (id: string) => void;
  clear: () => void;
}

const ChatContext = createContext<ChatValue | null>(null);
let counter = 0;

/**
 * Conversation state for the Ask page, kept above the router so it survives
 * navigating away and back. Each question is answered independently by the
 * backend (there is no server-side conversation memory).
 */
export function ChatProvider({ children }: { children: ReactNode }) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const turnsRef = useRef(turns);
  turnsRef.current = turns;

  const run = useCallback(async (turn: ChatTurn) => {
    try {
      const response = await api.ask(turn.question, turn.topK, turn.docIds);
      emit("scene-pulse");
      setTurns((all) => all.map((t) => (t.id === turn.id ? { ...t, status: "done", response } : t)));
    } catch (error) {
      setTurns((all) => all.map((t) => (t.id === turn.id ? { ...t, status: "error", error } : t)));
    }
  }, []);

  const ask = useCallback(
    (question: string, topK: number, docIds: string[]) => {
      const turn: ChatTurn = { id: `q${++counter}`, question, topK, docIds, status: "pending" };
      setTurns((all) => [...all, turn]);
      run(turn);
    },
    [run],
  );

  const retry = useCallback(
    (id: string) => {
      // Read the turn from a ref: state updaters must stay pure (StrictMode runs them twice).
      const turn = turnsRef.current.find((t) => t.id === id);
      if (!turn) return;
      setTurns((all) => all.map((t) => (t.id === id ? { ...t, status: "pending", error: undefined } : t)));
      run({ ...turn, status: "pending" });
    },
    [run],
  );

  const value = useMemo(() => ({ turns, ask, retry, clear: () => setTurns([]) }), [turns, ask, retry]);
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat(): ChatValue {
  const value = useContext(ChatContext);
  if (!value) throw new Error("useChat must be used inside ChatProvider");
  return value;
}

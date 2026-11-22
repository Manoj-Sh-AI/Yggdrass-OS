"use client";
/**
 * The chat page (B1): conversation list on surface-1, separated by colour alone; the
 * transcript is transparent content on the canvas; the composer is surface-2 with a
 * highlight and a 0.5px top edge; popovers are surface-3. No status lines (B2).
 */
import { MessageSquarePlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { chatApi, type Conversation } from "@/lib/chat-api";
import { DEFAULT_MODEL, MODELS } from "./composer/model-picker";
import { ConductorProvider } from "./runtime/provider";
import { Thread } from "./thread";

const MODEL_KEY = "yggdras.chat.model";

function storedModel(): string {
  try {
    const saved = window.localStorage.getItem(MODEL_KEY);
    return MODELS.some((m) => m.id === saved) ? (saved as string) : DEFAULT_MODEL;
  } catch {
    return DEFAULT_MODEL;
  }
}

export function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  // Remount the thread only when Manoj picks a conversation or starts a new one; a new
  // conversation receiving its id mid-answer must not remount (B3: zero remount).
  const [mount, setMount] = useState(0);
  const open = (id: string | null) => {
    setSelected(id);
    setMount((n) => n + 1);
  };
  const [model, setModel] = useState<string>(DEFAULT_MODEL);
  useEffect(() => setModel(storedModel()), []);
  const refresh = useCallback(() => {
    chatApi
      .list()
      .then((page) => setConversations(page.conversations))
      .catch(() => setConversations([]));
  }, []);
  useEffect(refresh, [refresh]);
  const chooseModel = (id: string) => {
    setModel(id);
    try {
      window.localStorage.setItem(MODEL_KEY, id);
    } catch {
      // Not remembered across visits; still used for this conversation.
    }
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-1 md:grid-cols-[240px_1fr]">
      <nav aria-label="Conversations" className="hidden min-h-0 flex-col bg-surface-1 md:flex">
        <button
          type="button"
          onClick={() => open(null)}
          className="m-2 flex h-7 items-center gap-2 rounded-md px-2 text-sm text-text-1 hover:bg-surface-2"
        >
          <MessageSquarePlus className="size-4" /> New chat
        </button>
        <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => open(c.id)}
                aria-current={c.id === selected ? "page" : undefined}
                title={c.title}
                className={`flex h-7 w-full items-center truncate rounded-md px-2 text-left text-sm hover:bg-surface-2 ${
                  c.id === selected ? "bg-surface-2 font-semibold text-text-1" : "text-text-2"
                }`}
              >
                <span className="truncate">{c.title}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <main className="min-h-0">
        <ConductorProvider
          key={mount}
          conversationId={selected}
          model={model}
          onConversation={(id) => {
            if (!selected) {
              setSelected(id);
              refresh();
            }
          }}
        >
          <Thread model={model} onModel={chooseModel} />
        </ConductorProvider>
      </main>
    </div>
  );
}

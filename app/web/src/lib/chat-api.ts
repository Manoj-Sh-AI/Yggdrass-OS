import { applicationApi } from "./api";
export type Conversation = {
  id: string;
  title: string;
  archived: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  agent_id: string;
  model_id: string;
};
export type ChatMessage = {
  id: string;
  conversation_id: string;
  ordinal: number;
  role: "user" | "assistant";
  content: string;
  version: number;
  source_message_id: string | null;
  source_version: number | null;
  created_at: string;
  edited_at: string | null;
  deleted_at: string | null;
  agent_id: string;
  model_id: string;
};
export type ChatAttachment = {
  id: string;
  conversation_id: string;
  message_id: string | null;
  name: string;
  media_type: string;
  size: number;
  sha256: string;
};
export type ChatRequest = {
  id: string;
  user_message_id: string;
  state: "held" | "queued" | "streaming" | "completed" | "failed" | "cancelled";
  version: number;
  error: string;
  agent_id: string;
  model_id: string;
};
export type ChatCatalog = {
  agents: { id: string; name: string; available: boolean; models: string[] }[];
  models: { id: string; name: string; available: boolean }[];
};
export type ChatHistory = {
  conversation: Conversation;
  messages: ChatMessage[];
  attachments: ChatAttachment[];
  requests: ChatRequest[];
  next_before: number | null;
};
export type ChatResult = {
  conversation?: Conversation;
  message?: ChatMessage;
  request?: ChatRequest;
  deleted?: boolean;
};
export const chatApi = {
  capabilities: () =>
    applicationApi<{
      receiver_configured: boolean;
      automatic_replay: boolean;
      max_attachment_bytes: number;
      voice: boolean;
      catalog: ChatCatalog;
    }>("chat/capabilities"),
  list: (q = "", archived = false, before?: string, signal?: AbortSignal) =>
    applicationApi<{ conversations: Conversation[]; next: string | null }>(
      `chat/conversations?${new URLSearchParams({ q, archived: String(archived), ...(before ? { before } : {}) })}`,
      { signal },
    ),
  history: (id: string, before?: number, signal?: AbortSignal) =>
    applicationApi<ChatHistory>(
      `chat/conversations/${id}${before ? `?before=${before}` : ""}`,
      { signal },
    ),
  command: (
    key: string,
    operation: string,
    data = {},
    id?: string,
    version?: number,
  ) =>
    applicationApi<ChatResult>("chat/commands", {
      method: "POST",
      body: JSON.stringify({ key, operation, data, id, version }),
    }),
  upload: (id: string, file: File, uploadId: string) =>
    applicationApi<ChatAttachment>(
      `chat/attachments?${new URLSearchParams({ conversation_id: id, name: file.name, upload_id: uploadId })}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      },
    ),
  export: (id: string) =>
    applicationApi<unknown>(`chat/conversations/${id}/export`),
};

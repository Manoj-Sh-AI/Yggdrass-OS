"use client";
import { memo, useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  chatApi,
  type ChatAttachment,
  type ChatHistory,
  type ChatMessage,
  type Conversation,
  type ChatCatalog,
} from "@/lib/chat-api";
import { workspaceRetry } from "@/lib/workspace-retry";
import { Icon, Modal } from "./ui";

const draftKey = (id: string | null) => `yggdras.chat.draft.v1:${id || "new"}`;
const MessageBody = memo(function MessageBody({ text }: { text: string }) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      components={{
        // External images in Markdown are not fetched implicitly; uploads have their own gallery.
        img: ({ alt }) => (
          <span className="chat-image-reference">
            {alt || "Image reference"}
          </span>
        ),
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        ),
      }}
    >
      {text}
    </Markdown>
  );
});

function Attachment({
  file,
  remove,
  disabled = false,
}: {
  file: ChatAttachment;
  remove?: () => void;
  disabled?: boolean;
}) {
  const url = `/api/backend/chat/attachments/${file.id}`;
  return (
    <div className="chat-attachment">
      {file.media_type.startsWith("image/") && (
        <a href={url} download={file.name}>
          <img src={url} alt={file.name} loading="lazy" />
        </a>
      )}
      <a href={url} download={file.name}>
        <Icon name="Paperclip" size={14} />
        <span>{file.name}</span>
        <small>{Math.max(1, Math.ceil(file.size / 1024))} KB</small>
      </a>
      {remove && (
        <button
          className="icon-button"
          aria-label={`Remove attachment ${file.name}`}
          onClick={remove}
          disabled={disabled}
        >
          <Icon name="X" size={14} />
        </button>
      )}
    </div>
  );
}

export function ChatPage() {
  const [threads, setThreads] = useState<Conversation[]>([]),
    [next, setNext] = useState<string | null>(null);
  const [query, setQuery] = useState(""),
    [search, setSearch] = useState(""),
    [archived, setArchived] = useState(false);
  const [selected, setSelected] = useState<string | null>(null),
    [history, setHistory] = useState<ChatHistory | null>(null);
  const [draft, setDraft] = useState({ key: "", text: "" }),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [listLoading, setListLoading] = useState(false);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [connected, setConnected] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false),
    [earlier, setEarlier] = useState(false);
  const [catalog, setCatalog] = useState<ChatCatalog>({
    agents: [],
    models: [],
  });
  const selectedAgent = history?.conversation.agent_id || "yggdras";
  const selectedModel = history?.conversation.model_id || "default";
  const agent = catalog.agents.find((item) => item.id === selectedAgent);
  const model = catalog.models.find((item) => item.id === selectedModel);
  const destinationReady =
    connected &&
    !!agent?.available &&
    !!model?.available &&
    !!agent.models.includes(selectedModel);
  const completionSignature =
    history?.requests.map((item) => `${item.id}:${item.state}`).join(",") || "";
  useEffect(() => {
    if (completionSignature)
      window.dispatchEvent(new Event("yggdress:agent-changes"));
  }, [completionSignature]);
  const [rename, setRename] = useState<{
    item: Conversation;
    title: string;
  } | null>(null);
  const [remove, setRemove] = useState<{
    kind: "conversation" | "message";
    id: string;
    version: number;
  } | null>(null);
  const [editing, setEditing] = useState<{
    message: ChatMessage;
    content: string;
  } | null>(null);
  const active = useRef<string | null>(null),
    readSequence = useRef(0),
    listSequence = useRef(0),
    locked = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null),
    composer = useRef<HTMLTextAreaElement>(null),
    stream = useRef<HTMLDivElement>(null);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const retryKeys = useRef(new Map<string, string>());
  const atBottom = useRef(true),
    [unseen, setUnseen] = useState(false);

  const list = useCallback(
    async (cursor?: string) => {
      const sequence = ++listSequence.current;
      setListLoading(true);
      try {
        const result = await chatApi.list(search, archived, cursor);
        if (sequence === listSequence.current) {
          setThreads((previous) =>
            cursor
              ? [
                  ...previous,
                  ...result.conversations.filter(
                    (item) => !previous.some((old) => old.id === item.id),
                  ),
                ]
              : result.conversations,
          );
          setNext(result.next);
        }
      } catch (error) {
        if (sequence === listSequence.current)
          setError(
            error instanceof Error
              ? error.message
              : "Conversation history could not be loaded.",
          );
      } finally {
        if (sequence === listSequence.current) setListLoading(false);
      }
    },
    [search, archived],
  );
  const latestList = useRef(list);
  latestList.current = list;
  const read = useCallback(async (id: string, before?: number) => {
    const sequence = ++readSequence.current;
    setLoading(true);
    try {
      const result = await chatApi.history(id, before);
      if (active.current === id && sequence === readSequence.current) {
        setHistory(result);
        setEarlier(!!before);
        if (!atBottom.current) setUnseen(true);
      }
    } catch (error) {
      if (active.current === id && sequence === readSequence.current)
        setError(
          error instanceof Error
            ? error.message
            : "Conversation could not be loaded.",
        );
    } finally {
      if (sequence === readSequence.current) setLoading(false);
    }
  }, []);
  const choose = useCallback((id: string | null) => {
    if (locked.current) return;
    active.current = id;
    ++readSequence.current;
    setSelected(id);
    setHistory(null);
    setEditing(null);
    setError("");
    setNotice("");
    setEarlier(false);
    setHistoryOpen(false);
    setUnseen(false);
    atBottom.current = true;
    try {
      localStorage.setItem("yggdras.chat.active.v1", id || "");
    } catch {
      /* Optional view state. */
    }
  }, []);
  useEffect(() => {
    try {
      const remembered = localStorage.getItem("yggdras.chat.active.v1");
      if (remembered && /^[a-f0-9-]{36}$/i.test(remembered)) choose(remembered);
    } catch {
      /* Optional view state. */
    }
  }, [choose]);
  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), 180);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    void list();
    return () => {
      ++listSequence.current;
    };
  }, [list]);
  useEffect(() => {
    let current = true;
    void chatApi
      .capabilities()
      .then((value) => {
        if (current) {
          setConnected(value.receiver_configured);
          setCatalog(value.catalog);
        }
      })
      .catch((error) => {
        if (current) setError(error.message);
      });
    return () => {
      current = false;
    };
  }, []);
  useEffect(() => {
    let text = "";
    try {
      text = localStorage.getItem(draftKey(selected)) || "";
    } catch {
      /* Editing still works without recovery storage. */
    }
    setDraft({ key: draftKey(selected), text });
    if (selected) void read(selected);
  }, [selected, read]);
  const waiting = history?.requests.some(
    (item) => item.state === "queued" || item.state === "streaming",
  );
  useEffect(() => {
    if (!selected || !waiting || earlier) return;
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void read(selected);
    }, 1500);
    return () => clearInterval(timer);
  }, [selected, waiting, earlier, read]);
  useEffect(() => {
    const resume = () => {
      void list();
      if (active.current && !earlier) void read(active.current);
    };
    window.addEventListener("focus", resume);
    return () => window.removeEventListener("focus", resume);
  }, [list, read, earlier]);
  useEffect(() => {
    if (atBottom.current && stream.current)
      stream.current.scrollTop = stream.current.scrollHeight;
  }, [history]);
  useEffect(() => {
    if (composer.current) {
      composer.current.style.height = "auto";
      composer.current.style.height =
        Math.min(220, composer.current.scrollHeight) + "px";
    }
  }, [draft.text]);

  function write(text: string, id = active.current) {
    const key = draftKey(id);
    setDraft({ key, text });
    try {
      if (text) localStorage.setItem(key, text);
      else localStorage.removeItem(key);
    } catch {
      setNotice(
        "Draft recovery is unavailable on this device. Keep this page open until your message is saved.",
      );
    }
  }
  async function execute(
    operation: string,
    data = {},
    id?: string,
    version?: number,
  ) {
    const identity = JSON.stringify({ operation, data, id, version });
    const retry = await workspaceRetry(
      "chat:" + identity,
      retryKeys.current.get(identity),
    );
    retryKeys.current.set(identity, retry.key);
    const result = await chatApi.command(
      retry.key,
      operation,
      data,
      id,
      version,
    );
    retry.complete();
    retryKeys.current.delete(identity);
    return result;
  }
  async function action(run: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await run();
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "This change could not be saved. Your entered content is preserved.",
      );
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  async function ensureConversation() {
    if (active.current) return active.current;
    const result = await execute("conversation.create");
    const conversation = result.conversation!;
    const text = draftRef.current.text;
    active.current = conversation.id;
    write(text, conversation.id);
    try {
      localStorage.removeItem(draftKey(null));
      localStorage.setItem("yggdras.chat.active.v1", conversation.id);
    } catch {
      /* Optional view state. */
    }
    setSelected(conversation.id);
    setHistory({
      conversation,
      messages: [],
      attachments: [],
      requests: [],
      next_before: null,
    });
    return conversation.id;
  }
  const attachments =
    history?.attachments.filter((file) => file.message_id === null) || [];
  async function send() {
    if (
      (!draft.text.trim() && !attachments.length) ||
      history?.conversation.archived
    )
      return;
    const text = draft.text,
      files = attachments.map((file) => file.id);
    await action(async () => {
      const id = await ensureConversation();
      await execute(
        "message.send",
        { content: text, attachment_ids: files, deliver: destinationReady },
        id,
      );
      write("", id);
      atBottom.current = true;
      setEarlier(false);
      await read(id);
      await latestList.current();
      composer.current?.focus();
    });
  }
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    if (files.length + attachments.length > 5) {
      setError("Attach up to five files to one message.");
      return;
    }
    if (
      Array.from(files).some(
        (file) => !file.size || file.size > 10 * 1024 * 1024,
      )
    ) {
      setError("Choose nonempty files of 10 MB or smaller.");
      return;
    }
    await action(async () => {
      const id = await ensureConversation();
      for (const file of Array.from(files)) {
        const hash = Array.from(
          new Uint8Array(
            await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
          ),
          (value) => value.toString(16).padStart(2, "0"),
        ).join("");
        const retry = await workspaceRetry(
          `chat-upload:${id}:${file.name}:${hash}`,
        );
        try {
          await chatApi.upload(id, file, retry.key);
          retry.complete();
        } finally {
          await read(id);
        }
      }
    });
    if (fileInput.current) fileInput.current.value = "";
  }
  async function routeTo(agentId: string, modelId: string) {
    await action(async () => {
      const id = await ensureConversation();
      const latest = await chatApi.history(id);
      await execute(
        "conversation.route",
        { agent_id: agentId, model_id: modelId },
        id,
        latest.conversation.version,
      );
      await read(id);
      await latestList.current();
    });
  }
  async function change(
    operation: string,
    item: { id: string; version: number },
    data = {},
  ) {
    return action(async () => {
      await execute(operation, data, item.id, item.version);
      if (
        operation === "conversation.delete" ||
        (operation === "conversation.archive" &&
          "archived" in data &&
          data.archived)
      ) {
        const old = active.current;
        active.current = null;
        setSelected(null);
        setHistory(null);
        if (operation === "conversation.delete")
          try {
            if (old) localStorage.removeItem(draftKey(old));
          } catch {
            /* Optional recovery data. */
          }
        try {
          localStorage.removeItem("yggdras.chat.active.v1");
        } catch {
          /* Optional view state. */
        }
      } else if (active.current) await read(active.current);
      setRename(null);
      setRemove(null);
      setEditing(null);
      await latestList.current();
    });
  }
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setNotice("Copied.");
    } catch {
      setError(
        "Clipboard access is unavailable. Select and copy the text manually.",
      );
    }
  }
  async function exportConversation() {
    if (!selected) return;
    await action(async () => {
      const content = await chatApi.export(selected);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(content, null, 2)], {
          type: "application/json",
        }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "yggdras-conversation.json";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  const conversations = (
    <>
      <button
        className="button chat-new"
        disabled={busy}
        onClick={() => {
          choose(null);
          composer.current?.focus();
        }}
      >
        <Icon name="Plus" size={16} />
        New chat
      </button>
      <label className="sr-only" htmlFor="chat-history-search">
        Search conversations
      </label>
      <input
        id="chat-history-search"
        placeholder="Search conversations"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <label className="chat-archive-toggle">
        <input
          type="checkbox"
          checked={archived}
          onChange={(event) => setArchived(event.target.checked)}
        />
        Archived
      </label>
      <nav aria-label="Conversation history">
        {threads.map((thread) => (
          <button
            key={thread.id}
            className={`chat-thread ${selected === thread.id ? "selected" : ""}`}
            aria-current={selected === thread.id ? "page" : undefined}
            disabled={busy}
            onClick={() => choose(thread.id)}
          >
            <span>{thread.title}</span>
            <small>
              {new Date(thread.updated_at).toLocaleDateString("en", {
                month: "short",
                day: "numeric",
              })}
            </small>
          </button>
        ))}
      </nav>
      {!threads.length && !listLoading && (
        <p className="muted">
          {search ? "No matching conversations." : "No conversations yet."}
        </p>
      )}
      {listLoading && <p role="status">Loading conversations…</p>}
      {next && (
        <button
          className="text-link"
          disabled={listLoading}
          onClick={() => void list(next)}
        >
          Load more conversations
        </button>
      )}
    </>
  );

  return (
    <section className="chat-page" aria-label="Yggdras chat">
      <aside className="chat-history panel" aria-label="Conversations">
        {!historyOpen && conversations}
      </aside>
      <div className="chat-workspace">
        <header className="chat-heading">
          <button
            className="icon-button chat-history-button"
            aria-label="Open conversation history"
            onClick={() => setHistoryOpen(true)}
          >
            <Icon name="PanelLeft" size={19} />
          </button>
          <div>
            <h1>{history?.conversation.title || "Yggdras"}</h1>
            <p>
              {destinationReady
                ? "Response connection configured"
                : "Messages saved here · Yggdras responses not connected"}
            </p>
          </div>
          {history && (
            <details className="chat-options">
              <summary aria-label="Conversation options">
                <Icon name="Ellipsis" size={20} />
              </summary>
              <div>
                <button
                  onClick={() =>
                    setRename({
                      item: history.conversation,
                      title: history.conversation.title,
                    })
                  }
                  disabled={busy}
                >
                  Rename
                </button>
                <button
                  onClick={() => void exportConversation()}
                  disabled={busy}
                >
                  Export conversation
                </button>
                <button
                  onClick={() =>
                    void change("conversation.archive", history.conversation, {
                      archived: !history.conversation.archived,
                    })
                  }
                  disabled={busy}
                >
                  {history.conversation.archived ? "Restore" : "Archive"}
                </button>
                <button
                  onClick={() =>
                    setRemove({
                      kind: "conversation",
                      id: history.conversation.id,
                      version: history.conversation.version,
                    })
                  }
                  disabled={busy}
                >
                  Delete conversation
                </button>
              </div>
            </details>
          )}
        </header>
        <div className="chat-destination" aria-label="Chat destination">
          <label>
            Agent
            <select
              aria-label="Chat agent"
              value={selectedAgent}
              disabled={
                busy ||
                loading ||
                !!history?.conversation.archived ||
                !catalog.agents.length
              }
              onChange={(event) => {
                const next = catalog.agents.find(
                  (item) => item.id === event.target.value,
                )!;
                void routeTo(
                  next.id,
                  next.models.includes(selectedModel)
                    ? selectedModel
                    : next.models[0],
                );
              }}
            >
              {!catalog.agents.some((item) => item.id === selectedAgent) && (
                <option value={selectedAgent}>
                  Previous agent unavailable
                </option>
              )}
              {catalog.agents.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                  {!item.available ? " · not connected" : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            Model
            <select
              aria-label="Chat model"
              value={selectedModel}
              disabled={
                busy ||
                loading ||
                !!history?.conversation.archived ||
                !catalog.models.length
              }
              onChange={(event) =>
                void routeTo(selectedAgent, event.target.value)
              }
            >
              {!catalog.models.some((item) => item.id === selectedModel) && (
                <option value={selectedModel}>
                  Previous model unavailable
                </option>
              )}
              {catalog.models
                .filter((item) => agent?.models.includes(item.id))
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                    {!item.available ? " · not connected" : ""}
                  </option>
                ))}
            </select>
          </label>
          {!destinationReady && (
            <small>
              Saved to history. Responses wait for a connection and your
              explicit resend.
            </small>
          )}
        </div>
        {error && (
          <div className="chat-feedback error" role="alert">
            <span>{error}</span>
            <button
              className="text-link"
              onClick={() => {
                setError("");
                void list();
                if (selected) void read(selected);
              }}
            >
              Refresh
            </button>
          </div>
        )}
        {notice && (
          <p className="chat-feedback" role="status">
            {notice}
          </p>
        )}
        <div
          className="chat-stream"
          ref={stream}
          onScroll={(event) => {
            const element = event.currentTarget;
            atBottom.current =
              element.scrollHeight - element.scrollTop - element.clientHeight <
              100;
            if (atBottom.current) setUnseen(false);
          }}
        >
          {loading && !history && <p role="status">Opening conversation…</p>}
          {!history?.messages.length && !loading && (
            <div className="chat-empty">
              <Icon name="Sprout" size={30} />
              <h2>Start a conversation</h2>
              <p>
                Write a thought or attach a file. Your messages stay in history
                until you explicitly resend them to a connected Yggdras.
              </p>
            </div>
          )}
          {history?.next_before && (
            <button
              className="button small-button chat-earlier"
              disabled={loading}
              onClick={() => {
                atBottom.current = true;
                void read(history.conversation.id, history.next_before!);
              }}
            >
              Earlier messages
            </button>
          )}
          {earlier && (
            <button
              className="text-link chat-latest"
              onClick={() => {
                atBottom.current = true;
                void read(history!.conversation.id);
              }}
            >
              Return to latest messages
            </button>
          )}
          {history?.messages.map((message) => {
            const request = history.requests
              .filter((item) => item.user_message_id === message.id)
              .at(-1);
            const source = message.source_message_id
              ? history.messages.find(
                  (item) => item.id === message.source_message_id,
                )
              : undefined;
            return (
              <article
                className={`chat-message ${message.role}`}
                key={message.id}
                aria-label={`${message.role === "user" ? "Your" : catalog.agents.find((item) => item.id === message.agent_id)?.name || "Assistant"} message`}
              >
                <div className="chat-message-label">
                  {message.role === "user"
                    ? "You"
                    : catalog.agents.find(
                        (item) => item.id === message.agent_id,
                      )?.name || "Assistant"}
                  <small>
                    {catalog.agents.find((item) => item.id === message.agent_id)
                      ?.name || message.agent_id}{" "}
                    ·{" "}
                    {catalog.models.find((item) => item.id === message.model_id)
                      ?.name || message.model_id}
                  </small>
                  {message.edited_at && <small>Edited</small>}
                </div>
                {message.deleted_at ? (
                  <p className="muted">This message was deleted.</p>
                ) : editing?.message.id === message.id ? (
                  <div className="chat-edit">
                    <label className="sr-only" htmlFor="chat-edit-message">
                      Edit message
                    </label>
                    <textarea
                      id="chat-edit-message"
                      value={editing.content}
                      onChange={(event) =>
                        setEditing({ ...editing, content: event.target.value })
                      }
                      autoFocus
                    />
                    <div>
                      <button
                        className="button primary"
                        disabled={busy || !editing.content.trim()}
                        onClick={() =>
                          void change("message.edit", message, {
                            content: editing.content,
                          })
                        }
                      >
                        Save edit
                      </button>
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() => setEditing(null)}
                      >
                        Cancel edit
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="chat-message-body">
                    <MessageBody text={message.content} />
                  </div>
                )}
                {history.attachments
                  .filter((file) => file.message_id === message.id)
                  .map((file) => (
                    <Attachment key={file.id} file={file} />
                  ))}
                {message.role === "assistant" &&
                  source &&
                  (source.deleted_at ||
                    source.version !== message.source_version) && (
                    <small className="chat-state">
                      Reply to an earlier version of your message.
                    </small>
                  )}
                {!message.deleted_at && !editing && (
                  <div className="chat-message-actions">
                    <button
                      className="text-link"
                      onClick={() => void copy(message.content)}
                    >
                      Copy
                    </button>
                    {message.role === "user" && (
                      <>
                        <button
                          className="text-link"
                          disabled={busy}
                          onClick={() =>
                            setEditing({ message, content: message.content })
                          }
                        >
                          Edit
                        </button>
                        <button
                          className="text-link"
                          disabled={busy}
                          onClick={() =>
                            setRemove({
                              kind: "message",
                              id: message.id,
                              version: message.version,
                            })
                          }
                        >
                          Delete
                        </button>
                        {destinationReady &&
                          !request?.state.match(/^(queued|streaming)$/) && (
                            <button
                              className="text-link"
                              disabled={busy}
                              onClick={() =>
                                void change("message.resend", message)
                              }
                            >
                              Resend to Yggdras
                            </button>
                          )}
                      </>
                    )}
                  </div>
                )}
                {request && (
                  <small className="chat-state">
                    {request.state === "held"
                      ? "Saved · not submitted for processing"
                      : request.state === "queued"
                        ? "Waiting for a response"
                        : request.state === "streaming"
                          ? "Receiving response"
                          : request.state === "failed"
                            ? request.error ||
                              "Response failed; your message is saved"
                            : request.state === "cancelled"
                              ? "Response cancelled"
                              : ""}
                  </small>
                )}
                {request && ["queued", "streaming"].includes(request.state) && (
                  <button
                    className="text-link"
                    disabled={busy}
                    onClick={() => void change("request.cancel", request)}
                  >
                    Stop response
                  </button>
                )}
              </article>
            );
          })}
        </div>
        {unseen && (
          <button
            className="button small-button chat-new-messages"
            onClick={() => {
              atBottom.current = true;
              if (stream.current)
                stream.current.scrollTop = stream.current.scrollHeight;
              setUnseen(false);
            }}
          >
            Latest messages <Icon name="ArrowDown" size={14} />
          </button>
        )}
        <form
          className="chat-composer"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
          aria-busy={busy}
        >
          {attachments.length > 0 && (
            <div className="chat-draft-attachments">
              {attachments.map((file) => (
                <Attachment
                  key={file.id}
                  file={file}
                  disabled={busy}
                  remove={() =>
                    void action(async () => {
                      await execute("attachment.remove", {}, file.id);
                      if (selected) await read(selected);
                    })
                  }
                />
              ))}
            </div>
          )}
          <label className="sr-only" htmlFor="chat-compose">
            Message
          </label>
          <textarea
            ref={composer}
            id="chat-compose"
            placeholder={
              history?.conversation.archived
                ? "Restore this conversation to continue"
                : `Write to ${agent?.name || "Yggdras"}…`
            }
            rows={2}
            maxLength={50000}
            value={draft.key === draftKey(selected) ? draft.text : ""}
            readOnly={busy}
            disabled={!!history?.conversation.archived}
            onChange={(event) => write(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                if (!busy) void send();
              }
            }}
          />
          <div className="chat-compose-tools">
            <input
              type="file"
              multiple
              ref={fileInput}
              aria-label="Choose chat attachments"
              tabIndex={-1}
              className="sr-only"
              onChange={(event) => void upload(event.target.files)}
            />
            <button
              type="button"
              className="icon-button"
              aria-label="Attach files or images"
              disabled={
                busy ||
                attachments.length >= 5 ||
                !!history?.conversation.archived
              }
              onClick={() => fileInput.current?.click()}
            >
              <Icon name="Paperclip" size={19} />
            </button>
            <small>Shift + Enter for a new line · files up to 10 MB</small>
            <button
              type="submit"
              className="button primary"
              disabled={
                busy ||
                (!draft.text.trim() && !attachments.length) ||
                !!history?.conversation.archived
              }
            >
              {busy ? "Saving…" : destinationReady ? "Send" : "Save message"}
              <Icon name="ArrowUp" size={16} />
            </button>
          </div>
        </form>
      </div>
      <Modal
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        title="Conversations"
      >
        <div className="chat-mobile-history">
          {historyOpen && conversations}
        </div>
      </Modal>
      <Modal
        open={!!rename}
        onOpenChange={(open) => {
          if (!open && !busy) setRename(null);
        }}
        preventDismiss={busy}
        title="Rename conversation"
      >
        {rename && (
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              void change("conversation.rename", rename.item, {
                title: rename.title,
              });
            }}
          >
            <label>
              Conversation title
              <input
                autoFocus
                maxLength={180}
                required
                value={rename.title}
                onChange={(event) =>
                  setRename({ ...rename, title: event.target.value })
                }
              />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button className="button primary" disabled={busy}>
              Save title
            </button>
          </form>
        )}
      </Modal>
      <Modal
        open={!!remove}
        onOpenChange={(open) => {
          if (!open && !busy) setRemove(null);
        }}
        preventDismiss={busy}
        title={
          remove?.kind === "conversation"
            ? "Delete conversation?"
            : "Delete message?"
        }
      >
        <p>
          {remove?.kind === "conversation"
            ? "This permanently removes the conversation and its files. Brain notes and tasks are unaffected."
            : "This permanently removes your message text and its files. Existing replies remain in the conversation."}
        </p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button
            className="button"
            disabled={busy}
            onClick={() => setRemove(null)}
          >
            Cancel
          </button>
          <button
            className="button primary"
            disabled={busy}
            onClick={() => {
              if (remove)
                void change(
                  remove.kind === "conversation"
                    ? "conversation.delete"
                    : "message.delete",
                  remove,
                );
            }}
          >
            Delete permanently
          </button>
        </div>
      </Modal>
    </section>
  );
}

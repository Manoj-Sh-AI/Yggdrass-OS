import { useEffect, useRef, useState } from "react";
import {
  Alert,
  AppState,
  FlatList,
  Pressable,
  Share,
  Text,
  TextInput,
  View,
} from "react-native";
import { Markdown } from "./markdown";
import * as DocumentPicker from "expo-document-picker";
import { File } from "expo-file-system";
import { randomUUID } from "expo-crypto";
import { api } from "./api";
import { Reviews } from "./reviews";
import {
  Button,
  ErrorText,
  Field,
  Loading,
  Panel,
  Sheet,
  styles,
  colors,
} from "./ui";
import type {
  Attachment,
  Catalog,
  Conversation,
  History,
  Message,
} from "./types";

export function Chat({ active }: { active: boolean }) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [query, setQuery] = useState("");
  const [archived, setArchived] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<History | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [draft, setDraft] = useState("");
  const [files, setFiles] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [actions, setActions] = useState(false);
  const [menuFor, setMenuFor] = useState<Message | null>(null);
  const [rename, setRename] = useState(false);
  const [title, setTitle] = useState("");
  const [route, setRoute] = useState(false);
  const [editing, setEditing] = useState<Message | null>(null);
  const [editText, setEditText] = useState("");
  const selected = useRef<string | null>(null);
  const visible = useRef(active);
  visible.current = active;
  const drafts = useRef(new Map<string, string>());
  async function list(more = false) {
    const found = await api.conversations(
      query,
      more ? cursor || undefined : undefined,
      archived,
    );
    setConversations((items) =>
      more ? [...items, ...found.conversations] : found.conversations,
    );
    setCursor(found.next);
  }
  async function open(id: string) {
    if (selected.current) drafts.current.set(selected.current, draft);
    selected.current = id;
    setError("");
    setLoading(true);
    try {
      const value = await api.history(id);
      if (selected.current !== id) return;
      setHistory(value);
      setDraft(drafts.current.get(id) || "");
      setFiles(value.attachments.filter((a) => !a.message_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open conversation.");
    } finally {
      setLoading(false);
    }
  }
  async function reload() {
    if (!selected.current) return;
    const value = await api.history(selected.current);
    if (selected.current === value.conversation.id)
      setHistory((current) => {
        if (!current || current.conversation.id !== value.conversation.id)
          return value;
        const first = value.messages[0]?.ordinal;
        const prefix =
          first === undefined
            ? []
            : current.messages.filter((message) => message.ordinal < first);
        return {
          ...value,
          messages: [...prefix, ...value.messages],
          next_before: prefix.length ? current.next_before : value.next_before,
        };
      });
  }
  useEffect(() => {
    if (!active) return;
    let live = true;
    const timer = setTimeout(() => {
      void Promise.all([
        api.catalog(),
        api.conversations(query, undefined, archived),
      ])
        .then(([capability, result]) => {
          if (live) {
            setCatalog(capability.catalog);
            setConversations(result.conversations);
            setCursor(result.next);
          }
        })
        .catch((e) => {
          if (live) setError(e.message);
        });
    }, 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [query, active, archived]);
  useEffect(() => {
    if (!active || !history) return;
    let fetching = false;
    const tick = () => {
      if (!visible.current || fetching || AppState.currentState !== "active")
        return;
      fetching = true;
      void reload()
        .catch((e) => setError(e.message))
        .finally(() => {
          fetching = false;
        });
    };
    const timer = setInterval(tick, 2000);
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") tick();
    });
    return () => {
      clearInterval(timer);
      subscription.remove();
    };
  }, [active, history?.conversation.id]);
  async function perform(operation: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await operation();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }
  const conversation = history?.conversation;
  const available =
    catalog?.agents.some(
      (a) => a.id === conversation?.agent_id && a.available,
    ) &&
    catalog?.models.some((m) => m.id === conversation?.model_id && m.available);
  async function create() {
    const value = await api.chat<{ conversation: Conversation }>(
      "conversation.create",
      { title: "New conversation" },
    );
    await list();
    await open(value.conversation.id);
  }
  async function send() {
    if (!conversation || (!draft.trim() && !files.length)) return;
    await api.chat(
      "message.send",
      {
        content: draft,
        attachment_ids: files.map((f) => f.id),
        deliver: !!available,
      },
      conversation.id,
    );
    setDraft("");
    drafts.current.delete(conversation.id);
    setFiles([]);
    await reload();
    await list();
  }
  async function attach() {
    if (!conversation) return;
    const result = await DocumentPicker.getDocumentAsync({
      copyToCacheDirectory: true,
      multiple: false,
    });
    if (result.canceled) return;
    const asset = result.assets[0];
    if (asset.size && asset.size > 10 * 1024 * 1024)
      throw new Error("Choose a file smaller than 10 MB.");
    const bytes = await new File(asset.uri).arrayBuffer();
    const uploaded = await api.upload(
      conversation.id,
      asset,
      bytes,
      randomUUID(),
    );
    setFiles((all) => [...all, uploaded]);
  }
  async function older() {
    if (!conversation || !history?.next_before) return;
    const earlier = await api.history(conversation.id, history.next_before);
    setHistory((current) =>
      current
        ? {
            ...current,
            messages: [...earlier.messages, ...current.messages],
            next_before: earlier.next_before,
          }
        : current,
    );
  }
  const back = () => {
    if (conversation) drafts.current.set(conversation.id, draft);
    selected.current = null;
    setHistory(null);
    setDraft("");
    setFiles([]);
    void list().catch((e) => setError(e.message));
  };
  return (
    <View style={styles.screen}>
      <View
        style={[
          styles.content,
          conversation ? { paddingTop: 8, paddingBottom: 4, gap: 8 } : null,
        ]}
      >
        {conversation ? (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="All chats"
              onPress={back}
              style={{ minWidth: 44, minHeight: 44, justifyContent: "center" }}
            >
              <Text style={{ fontSize: 29, color: colors.text }}>‹</Text>
            </Pressable>
            <Text
              accessibilityRole="header"
              numberOfLines={1}
              style={[styles.text, { flex: 1, fontWeight: "600" }]}
            >
              {conversation.title || "Chat"}
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Conversation actions"
              onPress={() => setActions(true)}
              style={{
                minWidth: 44,
                minHeight: 44,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Text style={{ fontSize: 20, color: colors.text }}>⋯</Text>
            </Pressable>
          </View>
        ) : (
          <View style={[styles.row, { justifyContent: "space-between" }]}>
            <Text
              accessibilityRole="header"
              style={[styles.title, { flex: 1 }]}
            >
              Chat
            </Text>
            <Button title="New chat" onPress={() => void perform(create)} />
          </View>
        )}
        {!conversation && (
          <>
            <TextInput
              accessibilityLabel="Search conversations"
              placeholder="Search conversations"
              placeholderTextColor={colors.faint}
              value={query}
              onChangeText={setQuery}
              style={styles.input}
            />
            <Pressable
              accessibilityRole="button"
              onPress={() => setArchived((value) => !value)}
              style={{
                alignSelf: "flex-start",
                minHeight: 44,
                justifyContent: "center",
              }}
            >
              <Text style={[styles.subtitle, { color: colors.accent }]}>
                {archived ? "Show active chats" : "Show archived chats"}
              </Text>
            </Pressable>
          </>
        )}
        <ErrorText message={error} />
        {loading && <Loading />}
      </View>
      {!conversation ? (
        <FlatList
          data={conversations}
          keyExtractor={(c) => c.id}
          contentContainerStyle={{ padding: 16, paddingTop: 4, gap: 12 }}
          ListEmptyComponent={
            <Text style={styles.subtitle}>
              Start a conversation. It will be saved in your application.
            </Text>
          }
          renderItem={({ item }) => (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Open ${item.title}`}
              onPress={() => void open(item.id)}
              style={({ pressed }) => ({
                paddingVertical: 12,
                paddingHorizontal: 16,
                borderRadius: 18,
                borderWidth: 1,
                borderColor: colors.glassBorder,
                backgroundColor: colors.glass,
                opacity: pressed ? 0.7 : 1,
              })}
            >
              <Text
                numberOfLines={1}
                style={[styles.text, { fontWeight: "500" }]}
              >
                {item.title}
              </Text>
              <Text style={[styles.subtitle, { fontSize: 12 }]}>
                {item.agent_id}
              </Text>
            </Pressable>
          )}
          ListFooterComponent={
            cursor ? (
              <Button
                title="Load more chats"
                onPress={() => void perform(() => list(true))}
              />
            ) : null
          }
        />
      ) : (
        <>
          <FlatList
            // Inverted: a chat opens at its newest message, like a messenger.
            inverted
            data={[...(history?.messages || [])].reverse()}
            keyExtractor={(m) => m.id}
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{
              paddingHorizontal: 16,
              paddingBottom: 12,
              gap: 12,
            }}
            ListFooterComponent={
              history?.next_before ? (
                <Button
                  title="Earlier messages"
                  onPress={() => void perform(older)}
                />
              ) : null
            }
            renderItem={({ item }) => {
              const request = history?.requests.find(
                (r) =>
                  r.user_message_id === item.id &&
                  !["completed", "cancelled"].includes(r.state),
              );
              const mine = item.role === "user";
              return (
                <Pressable
                  accessibilityRole="text"
                  accessibilityHint={
                    mine && !item.deleted_at
                      ? "Long press for message actions"
                      : undefined
                  }
                  delayLongPress={350}
                  onLongPress={
                    mine && !item.deleted_at
                      ? () => setMenuFor(item)
                      : undefined
                  }
                  style={{
                    alignSelf: mine ? "flex-end" : "flex-start",
                    maxWidth: mine ? "85%" : "100%",
                    gap: 6,
                    padding: 12,
                    borderRadius: 18,
                    borderWidth: mine ? 0 : 1,
                    borderColor: colors.glassBorder,
                    backgroundColor: mine ? colors.accent : colors.glass,
                  }}
                >
                  {!mine && (
                    <Text style={[styles.label, { marginBottom: 0 }]}>
                      {conversation.agent_id}
                    </Text>
                  )}
                  {item.deleted_at ? (
                    <Text style={styles.subtitle}>Message deleted</Text>
                  ) : mine ? (
                    <Text
                      selectable
                      style={[styles.text, { color: colors.ink }]}
                    >
                      {item.content}
                    </Text>
                  ) : (
                    <Markdown source={item.content} />
                  )}
                  {history?.attachments
                    .filter((a) => a.message_id === item.id)
                    .map((a) => (
                      <Text
                        key={a.id}
                        style={[styles.subtitle, mine && { color: colors.ink }]}
                      >
                        Attachment · {a.name}
                      </Text>
                    ))}
                  {request && (
                    <>
                      <Text
                        style={[styles.subtitle, mine && { color: colors.ink }]}
                      >
                        {request.state === "held"
                          ? "Saved. Not sent to an agent."
                          : request.state === "failed"
                            ? request.error || "Response failed."
                            : "Response in progress…"}
                      </Text>
                      {["queued", "streaming"].includes(request.state) && (
                        <BubbleAction
                          title="Stop response"
                          onLight={mine}
                          disabled={busy}
                          onPress={() =>
                            void perform(async () => {
                              await api.chat(
                                "request.cancel",
                                {},
                                request.id,
                                request.version,
                              );
                              await reload();
                            })
                          }
                        />
                      )}
                      {available &&
                        ["failed", "held"].includes(request.state) && (
                          <BubbleAction
                            title="Resend"
                            onLight={mine}
                            disabled={busy}
                            onPress={() =>
                              void perform(async () => {
                                await api.chat(
                                  "message.resend",
                                  {},
                                  item.id,
                                  item.version,
                                );
                                await reload();
                              })
                            }
                          />
                        )}
                    </>
                  )}
                </Pressable>
              );
            }}
          />
          <View
            style={{
              margin: 8,
              marginTop: 4,
              padding: 8,
              gap: 8,
              borderRadius: 18,
              borderColor: colors.glassBorder,
              borderWidth: 1,
              backgroundColor: colors.glass,
            }}
          >
            {!available && (
              <Text style={styles.subtitle}>
                Messages are saved. They will only be processed if you resend
                after connecting an agent.
              </Text>
            )}
            {files.map((file) => (
              <View key={file.id} style={styles.row}>
                <Text style={[styles.subtitle, { flex: 1 }]}>{file.name}</Text>
                <Button
                  title="Remove attachment"
                  onPress={() =>
                    void perform(async () => {
                      await api.chat("attachment.remove", {}, file.id);
                      setFiles((all) => all.filter((f) => f.id !== file.id));
                    })
                  }
                />
              </View>
            ))}
            <View
              style={{ flexDirection: "row", alignItems: "flex-end", gap: 8 }}
            >
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Attach file or image"
                disabled={busy || files.length >= 5 || conversation.archived}
                onPress={() => void perform(attach)}
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: colors.buttonBorder,
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Text style={{ fontSize: 20, color: colors.text }}>+</Text>
              </Pressable>
              <TextInput
                accessibilityLabel="Message"
                placeholder="Message"
                placeholderTextColor={colors.faint}
                value={draft}
                onChangeText={setDraft}
                multiline
                maxLength={50000}
                style={[styles.input, { flex: 1, maxHeight: 120 }]}
              />
              <Button
                title={busy ? "Saving…" : available ? "Send" : "Save message"}
                primary
                disabled={
                  busy ||
                  conversation.archived ||
                  (!draft.trim() && !files.length)
                }
                onPress={() => void perform(send)}
              />
            </View>
          </View>
        </>
      )}
      {menuFor && (
        <Sheet visible title="Message" onClose={() => setMenuFor(null)}>
          <Button
            title="Edit message"
            disabled={busy}
            onPress={() => {
              setEditing(menuFor);
              setEditText(menuFor.content);
              setMenuFor(null);
            }}
          />
          <Button
            title="Delete message"
            disabled={busy}
            onPress={() => {
              const item = menuFor;
              setMenuFor(null);
              Alert.alert(
                "Delete this message?",
                "Its attachment data will also be removed.",
                [
                  { text: "Keep", style: "cancel" },
                  {
                    text: "Delete",
                    style: "destructive",
                    onPress: () =>
                      void perform(async () => {
                        await api.chat(
                          "message.delete",
                          {},
                          item.id,
                          item.version,
                        );
                        await reload();
                      }),
                  },
                ],
              );
            }}
          />
        </Sheet>
      )}
      {conversation && (
        <Sheet
          visible={actions}
          title="Conversation actions"
          onClose={() => setActions(false)}
        >
          <Button
            title={`${conversation.agent_id} · ${conversation.model_id}`}
            onPress={() => setRoute(true)}
          />
          <Button title="Review changes" onPress={() => setReviewing(true)} />
          <Button
            title={conversation.archived ? "Restore chat" : "Archive chat"}
            onPress={() =>
              void perform(async () => {
                await api.chat(
                  "conversation.archive",
                  { archived: !conversation.archived },
                  conversation.id,
                  conversation.version,
                );
                await reload();
                await list();
              })
            }
          />
          <Button
            title="Rename"
            onPress={() => {
              setTitle(conversation.title);
              setRename(true);
            }}
          />
          <Button
            title="Export"
            onPress={() =>
              void perform(async () => {
                const data = await api.export(conversation.id);
                await Share.share({
                  message: JSON.stringify(data, null, 2),
                  title: conversation.title,
                });
              })
            }
          />
          <Button
            title="Delete"
            onPress={() =>
              Alert.alert(
                "Delete conversation?",
                "Messages and attachments in this conversation will be removed.",
                [
                  { text: "Keep", style: "cancel" },
                  {
                    text: "Delete",
                    style: "destructive",
                    onPress: () =>
                      void perform(async () => {
                        await api.chat(
                          "conversation.delete",
                          {},
                          conversation.id,
                          conversation.version,
                        );
                        back();
                      }),
                  },
                ],
              )
            }
          />
        </Sheet>
      )}
      {reviewing && <Reviews onClose={() => setReviewing(false)} />}
      <Sheet
        visible={rename}
        title="Rename conversation"
        onClose={() => setRename(false)}
      >
        <Field
          label="Conversation title"
          value={title}
          onChangeText={setTitle}
        />
        <Button
          title="Save name"
          primary
          disabled={busy}
          onPress={() =>
            void perform(async () => {
              await api.chat(
                "conversation.rename",
                { title },
                conversation!.id,
                conversation!.version,
              );
              setRename(false);
              await reload();
              await list();
            })
          }
        />
        <ErrorText message={error} />
      </Sheet>
      <Sheet
        visible={route}
        title="Who would you like to talk to?"
        onClose={() => setRoute(false)}
      >
        {catalog?.agents.map((agent) => (
          <Panel key={agent.id}>
            <Text style={styles.text}>
              {agent.name}
              {!agent.available ? " · not connected" : ""}
            </Text>
            {agent.models.map((id) => {
              const model = catalog.models.find((m) => m.id === id);
              return (
                <Button
                  key={id}
                  title={`${model?.name || id}${!model?.available ? " · not connected" : ""}`}
                  primary={
                    conversation?.agent_id === agent.id &&
                    conversation?.model_id === id
                  }
                  disabled={busy}
                  onPress={() =>
                    void perform(async () => {
                      await api.chat(
                        "conversation.route",
                        { agent_id: agent.id, model_id: id },
                        conversation!.id,
                        conversation!.version,
                      );
                      setRoute(false);
                      await reload();
                    })
                  }
                />
              );
            })}
          </Panel>
        ))}
        <ErrorText message={error} />
      </Sheet>
      <Sheet
        visible={!!editing}
        title="Edit message"
        onClose={() => setEditing(null)}
      >
        <Field
          label="Message text"
          value={editText}
          onChangeText={setEditText}
          multiline
        />
        <Text style={styles.subtitle}>
          Saving an edit does not automatically resend it.
        </Text>
        <Button
          title="Save edit"
          primary
          disabled={busy}
          onPress={() =>
            void perform(async () => {
              await api.chat(
                "message.edit",
                { content: editText },
                editing!.id,
                editing!.version,
              );
              setEditing(null);
              await reload();
            })
          }
        />
        <ErrorText message={error} />
      </Sheet>
    </View>
  );
}

/** A small action inside a chat bubble, readable on the light (own) bubble too. */
function BubbleAction({
  title,
  onPress,
  disabled,
  onLight,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  onLight: boolean;
}) {
  const color = onLight ? colors.ink : colors.text;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => ({
        alignSelf: "flex-start",
        minHeight: 44,
        justifyContent: "center",
        paddingHorizontal: 15,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: color,
        opacity: disabled ? 0.5 : pressed ? 0.7 : 1,
      })}
    >
      <Text style={[styles.buttonText, { color }]}>{title}</Text>
    </Pressable>
  );
}

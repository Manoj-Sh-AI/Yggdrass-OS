/** Yggdras on the phone: Chat with approval cards, calls, and Notes and Graph (web components,
 * in a WebView). Today, Tasks, Calendar and Settings native screens are not built yet. */
import { useState } from "react";
import { Pressable, SafeAreaView, ScrollView, Text, TextInput, View } from "react-native";
import { WebView } from "react-native-webview";
import { api, signIn, type Card } from "./src/api";
import { ringer } from "./src/calls";

type Tab = "chat" | "notes" | "graph" | "call";

function CardView({ card, done }: { card: Card; done: () => void }) {
  return (
    <View style={{ borderWidth: 2, borderColor: card.offer ? "#10b981" : "#f59e0b", borderRadius: 14, padding: 14, marginBottom: 10 }}>
      <Text style={{ fontWeight: "700", fontSize: 16 }}>{card.title}</Text>
      {card.old_text !== null && <Text style={{ backgroundColor: "#fee2e2", padding: 6, marginTop: 6, textDecorationLine: "line-through" }}>{card.old_text}</Text>}
      {card.new_text !== null && <Text style={{ backgroundColor: "#dcfce7", padding: 6, marginTop: 6 }}>{card.new_text}</Text>}
      {card.links_added.length > 0 && <Text>Links added: {card.links_added.join(", ")}</Text>}
      {card.warning !== "" && <Text style={{ color: "#991b1b", fontWeight: "700", marginTop: 6 }}>{card.warning}</Text>}
      <View style={{ flexDirection: "row", gap: 10, marginTop: 10 }}>
        <Pressable onPress={() => void api.approve(card.id).then(done)} style={{ backgroundColor: "#15803d", padding: 14, borderRadius: 10, flex: 1 }}>
          <Text style={{ color: "#fff", fontWeight: "700", textAlign: "center" }}>{card.offer ? "File it" : "Approve"}</Text>
        </Pressable>
        <Pressable onPress={() => void api.reject(card.id).then(done)} style={{ backgroundColor: "#e5e7eb", padding: 14, borderRadius: 10, flex: 1 }}>
          <Text style={{ fontWeight: "700", textAlign: "center" }}>Reject</Text>
        </Pressable>
      </View>
    </View>
  );
}

function Chat() {
  const [text, setText] = useState("");
  const [answer, setAnswer] = useState("");
  const [cards, setCards] = useState<Card[]>([]);
  const send = async () => {
    const out = await api.ask(text);
    setText("");
    setAnswer(out.error || out.answer);
    setCards(out.cards);
  };
  return (
    <ScrollView contentContainerStyle={{ padding: 16 }}>
      {cards.map((c) => (
        <CardView key={c.id} card={c} done={() => setCards((all) => all.filter((x) => x.id !== c.id))} />
      ))}
      {answer !== "" && <Text style={{ marginBottom: 12 }}>{answer}</Text>}
      <TextInput value={text} onChangeText={setText} placeholder="Ask Yggdras" multiline style={{ borderWidth: 1, borderRadius: 12, padding: 10, minHeight: 60 }} />
      <Pressable onPress={() => void send()} style={{ backgroundColor: "#0f172a", padding: 12, borderRadius: 10, marginTop: 8 }}>
        <Text style={{ color: "#fff", textAlign: "center" }}>Send</Text>
      </Pressable>
    </ScrollView>
  );
}

export default function App() {
  const [origin, setOrigin] = useState("");
  const [password, setPassword] = useState("");
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<Tab>("chat");
  const [status, setStatus] = useState("");
  if (!ready)
    return (
      <SafeAreaView style={{ flex: 1, padding: 24, gap: 12, justifyContent: "center" }}>
        <Text style={{ fontSize: 24, fontWeight: "800" }}>Yggdras</Text>
        <TextInput placeholder="App address (https://…)" autoCapitalize="none" value={origin} onChangeText={setOrigin} style={{ borderWidth: 1, borderRadius: 10, padding: 10 }} />
        <TextInput placeholder="Password" secureTextEntry value={password} onChangeText={setPassword} style={{ borderWidth: 1, borderRadius: 10, padding: 10 }} />
        <Pressable
          onPress={() =>
            void signIn(origin, password)
              .then(() => ringer.register().catch((e: Error) => setStatus(e.message)))
              .then(() => setReady(true))
              .catch((e: Error) => setStatus(e.message))
          }
          style={{ backgroundColor: "#15803d", padding: 14, borderRadius: 10 }}
        >
          <Text style={{ color: "#fff", textAlign: "center", fontWeight: "700" }}>Sign in</Text>
        </Pressable>
        {status !== "" && <Text>{status}</Text>}
      </SafeAreaView>
    );
  return (
    <SafeAreaView style={{ flex: 1 }}>
      <View style={{ flex: 1 }}>
        {tab === "chat" && <Chat />}
        {tab === "notes" && <WebView source={{ uri: `${api.origin()}/notes` }} sharedCookiesEnabled />}
        {tab === "graph" && <WebView source={{ uri: `${api.origin()}/graph` }} sharedCookiesEnabled />}
        {tab === "call" && (
          <View style={{ flex: 1, justifyContent: "center", padding: 24 }}>
            <Pressable onPress={() => void api.callYggdras().then((c) => setStatus(c.simulated ? "Connected (simulated: voice keys not set up)" : "Connected"))} style={{ backgroundColor: "#15803d", padding: 18, borderRadius: 999 }}>
              <Text style={{ color: "#fff", textAlign: "center", fontWeight: "700", fontSize: 18 }}>Call Yggdras</Text>
            </Pressable>
            {status !== "" && <Text style={{ marginTop: 12, textAlign: "center" }}>{status}</Text>}
          </View>
        )}
      </View>
      <View style={{ flexDirection: "row", borderTopWidth: 1, borderColor: "#e5e7eb" }}>
        {(["chat", "notes", "graph", "call"] as Tab[]).map((t) => (
          <Pressable key={t} onPress={() => setTab(t)} style={{ flex: 1, padding: 14 }}>
            <Text style={{ textAlign: "center", fontWeight: tab === t ? "800" : "400" }}>{t[0].toUpperCase() + t.slice(1)}</Text>
          </Pressable>
        ))}
      </View>
    </SafeAreaView>
  );
}

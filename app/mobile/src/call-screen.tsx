import { useEffect, useState } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Scenery } from "./scenery";
import { ErrorText, colors, styles } from "./ui";

/** A phone-style call screen in the open-air look: who, why, status, round controls. */
export type CallControl = {
  label: string;
  glyph: string;
  tone?: "answer" | "end" | "plain";
  active?: boolean;
  disabled?: boolean;
  onPress: () => void;
};

export function CallScreen({
  visible,
  heading,
  reason,
  status,
  since,
  controls,
  error,
}: {
  visible: boolean;
  heading: string;
  reason: string;
  status: string;
  since?: number;
  controls: CallControl[];
  error?: string;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!visible || !since) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [visible, since]);
  const elapsed = since ? Math.max(0, Math.floor((now - since) / 1000)) : 0;
  const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;
  return (
    <Modal
      visible={visible}
      animationType="fade"
      presentationStyle="fullScreen"
      onRequestClose={() => {}}
    >
      <View style={styles.root}>
        <Scenery />
        <SafeAreaView style={[styles.screen, local.frame]}>
          <View style={local.who}>
            <Text style={local.eyebrow}>{heading}</Text>
            <View style={local.avatar} accessibilityElementsHidden>
              <Text style={local.avatarText}>Y</Text>
            </View>
            <Text accessibilityRole="header" style={[styles.title, local.name]}>
              Yggdras
            </Text>
            <Text style={[styles.subtitle, local.center]} numberOfLines={3}>
              {reason}
            </Text>
            <Text
              accessibilityLiveRegion="polite"
              style={[styles.subtitle, local.center, local.status]}
            >
              {since ? `${status} · ${clock}` : status}
            </Text>
            <ErrorText message={error || ""} />
          </View>
          <View style={local.controls}>
            {controls.map((c) => (
              <View key={c.label} style={local.control}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={c.label}
                  accessibilityState={{
                    disabled: !!c.disabled,
                    selected: !!c.active,
                  }}
                  disabled={c.disabled}
                  onPress={c.onPress}
                  style={({ pressed }) => [
                    local.round,
                    c.tone === "answer" && local.answer,
                    c.tone === "end" && local.end,
                    c.active && local.on,
                    (pressed || c.disabled) && {
                      opacity: c.disabled ? 0.4 : 0.75,
                    },
                  ]}
                >
                  <Text
                    style={[
                      local.glyph,
                      c.tone === "answer" && { color: "#10261a" },
                      c.active && { color: colors.ink },
                    ]}
                  >
                    {c.glyph}
                  </Text>
                </Pressable>
                <Text style={local.label}>{c.label}</Text>
              </View>
            ))}
          </View>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const local = StyleSheet.create({
  frame: {
    justifyContent: "space-between",
    paddingHorizontal: 24,
    paddingBottom: 36,
  },
  who: { alignItems: "center", gap: 10, paddingTop: 70 },
  eyebrow: {
    color: colors.muted,
    fontSize: 12,
    letterSpacing: 1.6,
    fontWeight: "600",
  },
  avatar: {
    width: 112,
    height: 112,
    borderRadius: 56,
    marginVertical: 18,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.accent,
    borderWidth: 10,
    borderColor: "rgba(220, 226, 207, 0.18)",
  },
  avatarText: { fontSize: 46, color: colors.ink, fontWeight: "300" },
  name: { fontSize: 36, textAlign: "center" },
  center: { textAlign: "center" },
  status: { fontSize: 13 },
  controls: {
    flexDirection: "row",
    justifyContent: "space-around",
    alignItems: "flex-start",
    padding: 18,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    backgroundColor: colors.glass,
  },
  control: { alignItems: "center", gap: 8, minWidth: 72 },
  round: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.buttonBorder,
    backgroundColor: "rgba(255, 255, 255, 0.08)",
  },
  answer: { backgroundColor: "#6fbf8e", borderColor: "#8fd3a9" },
  end: { backgroundColor: "#d9665b", borderColor: "#e88a80" },
  on: { backgroundColor: colors.accent, borderColor: "#ecf0df" },
  glyph: { fontSize: 22, color: colors.text, fontWeight: "600" },
  label: { color: colors.muted, fontSize: 12 },
});

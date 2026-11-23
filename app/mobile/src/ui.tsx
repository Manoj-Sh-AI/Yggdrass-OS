import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Scenery } from "./scenery";

/** Open-air tokens, kept in step with web/src/app/open-air.css. */
export const colors = {
  bg: "#232b2d",
  glass: "rgba(32, 34, 35, 0.84)",
  glassStrong: "#293334",
  glassBorder: "rgba(238, 242, 229, 0.22)",
  line: "rgba(230, 238, 226, 0.12)",
  control: "#263132",
  controlBorder: "rgba(194, 207, 195, 0.3)",
  buttonFill: "rgba(255, 255, 255, 0.03)",
  buttonBorder: "rgba(200, 211, 198, 0.35)",
  text: "#f6f5ed",
  muted: "#cbd2cc",
  faint: "#bec8c0",
  accent: "#dce2cf",
  ink: "#29342c",
  error: "#ffb4ae",
};
const headingShadow = {
  textShadowColor: "rgba(20, 41, 44, 0.6)",
  textShadowOffset: { width: 0, height: 2 },
  textShadowRadius: 14,
};
export const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  screen: { flex: 1, backgroundColor: "transparent" },
  content: { padding: 16, paddingTop: 20, paddingBottom: 32, gap: 14 },
  title: {
    fontSize: 29,
    fontWeight: "400",
    color: colors.text,
    letterSpacing: -1.1,
    ...headingShadow,
  },
  subtitle: {
    fontSize: 14,
    color: colors.muted,
    lineHeight: 21,
  },
  text: { fontSize: 15, color: colors.text, lineHeight: 24 },
  label: {
    fontSize: 12,
    fontWeight: "500",
    color: colors.muted,
    marginBottom: 6,
    letterSpacing: 0.2,
  },
  panel: {
    backgroundColor: colors.glass,
    borderColor: colors.glassBorder,
    borderWidth: 1,
    borderRadius: 18,
    padding: 18,
    gap: 10,
    shadowColor: "#102024",
    shadowOpacity: 0.25,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
    elevation: 0,
  },
  input: {
    backgroundColor: colors.control,
    borderWidth: 1,
    borderColor: colors.controlBorder,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 11,
    color: colors.text,
    fontSize: 15,
    minHeight: 46,
  },
  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 8,
  },
  button: {
    minHeight: 44,
    borderRadius: 12,
    paddingHorizontal: 15,
    paddingVertical: 11,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.buttonBorder,
    backgroundColor: colors.buttonFill,
  },
  buttonText: { fontSize: 14, fontWeight: "500", color: colors.text },
  error: { color: colors.error, fontSize: 14, lineHeight: 21 },
});
export function Button({
  title,
  onPress,
  disabled = false,
  primary = false,
  accessibilityLabel,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  primary?: boolean;
  accessibilityLabel?: string;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel || title}
      accessibilityState={{ disabled }}
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.button,
        primary && {
          backgroundColor: colors.accent,
          borderColor: "#ecf0df",
        },
        pressed && !disabled && { transform: [{ scale: 0.98 }], opacity: 0.85 },
        disabled && { opacity: 0.45 },
      ]}
    >
      <Text style={[styles.buttonText, primary && { color: colors.ink }]}>
        {title}
      </Text>
    </Pressable>
  );
}
export function Field({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        {...props}
        accessibilityLabel={label}
        placeholderTextColor={colors.faint}
        style={[
          styles.input,
          props.multiline && { minHeight: 100, textAlignVertical: "top" },
          props.style,
        ]}
      />
    </View>
  );
}
export function Panel({ children }: { children: ReactNode }) {
  return <View style={styles.panel}>{children}</View>;
}
export function Page({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <ScrollView
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={styles.content}
    >
      <View>
        <Text accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
        {subtitle && (
          <Text style={[styles.subtitle, { marginTop: 6 }]}>{subtitle}</Text>
        )}
      </View>
      {children}
    </ScrollView>
  );
}
export function ErrorText({ message }: { message: string }) {
  return message ? (
    <Text
      accessibilityRole="alert"
      accessibilityLiveRegion="assertive"
      style={styles.error}
    >
      {message}
    </Text>
  ) : null;
}
export function Loading() {
  return (
    <ActivityIndicator accessibilityLabel="Loading" color={colors.accent} />
  );
}
export function Sheet({
  title,
  visible,
  onClose,
  children,
}: {
  title: string;
  visible: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <Modal
      visible={visible}
      onRequestClose={onClose}
      animationType="fade"
      presentationStyle="fullScreen"
    >
      <View style={styles.root}>
        <Scenery />
        <SafeAreaView style={styles.screen}>
          <ScrollView
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={styles.content}
          >
            <View style={[styles.row, { justifyContent: "space-between" }]}>
              <Text
                accessibilityRole="header"
                style={[styles.title, { flex: 1 }]}
              >
                {title}
              </Text>
              <Button title="Close" onPress={onClose} />
            </View>
            {children}
          </ScrollView>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

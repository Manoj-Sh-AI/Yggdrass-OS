import { useEffect, useMemo, useRef, useState } from "react";
import { AppState, Text, View } from "react-native";
import { WebView } from "react-native-webview";
import { session, sessionExpired } from "./api";
import { Button, ErrorText, Loading, styles } from "./ui";

/** HttpOnly session established by POST; no token in URLs, injected JS or messages. */
export function Embedded({
  view,
  active = true,
}: {
  view: "notes" | "graph";
  active?: boolean;
}) {
  const current = session()!;
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const ref = useRef<WebView>(null);
  const loaded = useRef(false);
  useEffect(() => {
    const refresh = () => {
      if (active && loaded.current)
        ref.current?.injectJavaScript(
          "window.dispatchEvent(new Event('yggdras:foreground'));true;",
        );
    };
    refresh();
    const listener = AppState.addEventListener("change", (state) => {
      if (state === "active") refresh();
    });
    return () => listener.remove();
  }, [active]);
  const source = useMemo(
    () => ({
      uri: `${current.origin}/api/mobile-session?view=${view}`,
      method: "POST" as const,
      body: new URLSearchParams({ token: current.token }).toString(),
    }),
    [view, current.origin, current.token],
  );
  return (
    <View style={styles.screen}>
      <View style={{ padding: 16, gap: 8 }}>
        <Text accessibilityRole="header" style={styles.title}>
          {view === "notes" ? "Notes" : "Graph"}
        </Text>
        <ErrorText message={error} />
        {error && (
          <Button
            title="Retry"
            onPress={() => {
              setError("");
              ref.current?.reload();
            }}
          />
        )}
        {loading && <Loading />}
      </View>
      <WebView
        ref={ref}
        source={source}
        sharedCookiesEnabled
        thirdPartyCookiesEnabled={false}
        originWhitelist={[current.origin]}
        javaScriptEnabled
        domStorageEnabled
        mixedContentMode="never"
        allowFileAccess={false}
        setSupportMultipleWindows={false}
        onShouldStartLoadWithRequest={(request) => {
          if (request.url.startsWith(current.origin + "/login")) {
            sessionExpired();
            return false;
          }
          return (
            request.url.startsWith(current.origin + "/") ||
            request.url === "about:blank"
          );
        }}
        onLoadEnd={() => {
          loaded.current = true;
          setLoading(false);
        }}
        onError={() => {
          setError(
            "Cannot reach the application. Check your internet connection and retry.",
          );
          setLoading(false);
        }}
        onHttpError={(event) => {
          if (event.nativeEvent.statusCode >= 400) {
            setError(
              "This view is unavailable. Your session may have expired; return to Settings to sign in again.",
            );
            setLoading(false);
          }
        }}
        style={{ flex: 1, backgroundColor: "transparent" }}
      />
    </View>
  );
}

import { useEffect, useState } from "react";
import { AppState, Image, StyleSheet, View } from "react-native";
import { sceneImages, sceneKey } from "./scenes";

/** The web app's open-air backdrop: a seasonal photo, softened, under the glass. */
export function Scenery() {
  const [key, setKey] = useState(() => sceneKey(new Date()));
  useEffect(() => {
    const tick = () => setKey(sceneKey(new Date()));
    const timer = setInterval(tick, 60000);
    const listener = AppState.addEventListener("change", (state) => {
      if (state === "active") tick();
    });
    return () => {
      clearInterval(timer);
      listener.remove();
    };
  }, []);
  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={StyleSheet.absoluteFill}
      testID="scenery"
    >
      <Image
        source={sceneImages[key]}
        resizeMode="cover"
        fadeDuration={400}
        style={[StyleSheet.absoluteFill, { width: "100%", height: "100%" }]}
      />
      {/* Matches .scene-image filter (dimmed) and .scene-shade (darker toward the bottom). */}
      <View
        style={[StyleSheet.absoluteFill, { backgroundColor: "#11212433" }]}
      />
      <View
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: "55%",
          backgroundColor: "#13232266",
        }}
      />
    </View>
  );
}

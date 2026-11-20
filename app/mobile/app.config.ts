import { existsSync } from "node:fs";
import type { ExpoConfig } from "expo/config";

const firebase = existsSync("./google-services.json");
const config: ExpoConfig = {
  name: "Yggdras",
  slug: "yggdras",
  scheme: "yggdras",
  version: "0.3.1",
  orientation: "default",
  userInterfaceStyle: "dark",
  android: {
    package: "app.yggdras.mobile",
    blockedPermissions: ["android.permission.CAMERA"],
    permissions: [
      "RECORD_AUDIO",
      "POST_NOTIFICATIONS",
      "USE_FULL_SCREEN_INTENT",
      "FOREGROUND_SERVICE",
      "FOREGROUND_SERVICE_MICROPHONE",
    ],
    ...(firebase ? { googleServicesFile: "./google-services.json" } : {}),
  },
  plugins: [
    "expo-secure-store",
    "expo-document-picker",
    "./plugins/with-loopback-network",
    // The ringtone is copied to res/raw/yggdras_ring for the call channel.
    ["expo-notifications", { sounds: ["./assets/sounds/yggdras_ring.wav"] }],
    "@livekit/react-native-expo-plugin",
    "@config-plugins/react-native-webrtc",
    "./plugins/with-android-calls",
  ],
  extra: { voiceConfigured: false, firebaseConfigured: firebase },
};
export default config;

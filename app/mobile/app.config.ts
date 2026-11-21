import { existsSync } from "node:fs";
import type { ExpoConfig } from "expo/config";

const firebase = existsSync("./google-services.json");
// The one place the phone's server address lives. Override at build time with
// YGGDRAS_SERVER_ORIGIN (e.g. when the custom domain arrives).
const serverOrigin =
  process.env.YGGDRAS_SERVER_ORIGIN ||
  "https://web-production-7c89ea1a.up.railway.app";
// Developer option only: YGGDRAS_DEV_USB=1 allows http://127.0.0.1 over adb reverse.
const devUsb = process.env.YGGDRAS_DEV_USB === "1";
const config: ExpoConfig = {
  name: "Yggdras",
  slug: "yggdras",
  scheme: "yggdras",
  version: "0.3.2",
  runtimeVersion: { policy: "fingerprint" },
  updates: {
    url: `${serverOrigin}/api/mobile-updates/manifest`,
    checkAutomatically: "ON_LOAD",
    fallbackToCacheTimeout: 0,
    codeSigningCertificate: "./certs/update-certificate.pem",
    codeSigningMetadata: { keyid: "main", alg: "rsa-v1_5-sha256" },
  },
  orientation: "default",
  userInterfaceStyle: "dark",
  android: {
    package: "app.yggdras.mobile",
    versionCode: 2,
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
    ["./plugins/with-loopback-network", { loopback: devUsb }],
    // The ringtone is copied to res/raw/yggdras_ring for the call channel.
    ["expo-notifications", { sounds: ["./assets/sounds/yggdras_ring.wav"] }],
    "@livekit/react-native-expo-plugin",
    "@config-plugins/react-native-webrtc",
    "./plugins/with-android-calls",
    // Release APKs use the owner's upload key (local-data/android-signing).
    "./plugins/with-release-signing",
  ],
  extra: {
    voiceConfigured: false,
    firebaseConfigured: firebase,
    serverOrigin,
    devUsb,
  },
};
export default config;

const {
  withAndroidManifest,
  withDangerousMod,
  withMainApplication,
  withAppBuildGradle,
  withMainActivity,
} = require("expo/config-plugins");
const fs = require("node:fs/promises");
const path = require("node:path");
module.exports = function (config) {
  config = withAndroidManifest(config, (c) => {
    const m = c.modResults.manifest;
    m.$["xmlns:tools"] = "http://schemas.android.com/tools";
    const app = m.application[0];
    app.service = (app.service || []).filter(
      (s) =>
        ![
          ".YggdrasMessagingService",
          ".YggdrasAudioService",
          "expo.modules.notifications.service.ExpoFirebaseMessagingService",
        ].includes(s.$["android:name"]),
    );
    app.service.push({
      $: {
        "android:name":
          "expo.modules.notifications.service.ExpoFirebaseMessagingService",
        "tools:node": "remove",
      },
    });
    app.service.push({
      $: {
        "android:name": ".YggdrasMessagingService",
        "android:exported": "false",
      },
      "intent-filter": [
        {
          action: [
            { $: { "android:name": "com.google.firebase.MESSAGING_EVENT" } },
          ],
        },
      ],
    });
    app.service.push({
      $: {
        "android:name": ".YggdrasAudioService",
        "android:exported": "false",
        "android:foregroundServiceType": "microphone",
      },
    });
    app.activity = (app.activity || []).filter(
      (a) => a.$["android:name"] !== ".YggdrasIncomingActivity",
    );
    app.activity.push({
      $: {
        "android:name": ".YggdrasIncomingActivity",
        "android:exported": "false",
        "android:excludeFromRecents": "true",
        "android:theme": "@android:style/Theme.Material.NoActionBar",
        "android:showWhenLocked": "true",
        "android:turnScreenOn": "true",
      },
    });
    return c;
  });
  config = withAppBuildGradle(config, (c) => {
    const dependency =
      'implementation("com.google.firebase:firebase-messaging:24.0.1")';
    if (!c.modResults.contents.includes(dependency))
      c.modResults.contents = c.modResults.contents.replace(
        "dependencies {",
        "dependencies {\n    " + dependency,
      );
    return c;
  });
  config = withMainApplication(config, (c) => {
    const marker = "PackageList(this).packages.apply {";
    if (!c.modResults.contents.includes("add(YggdrasCallsPackage())")) {
      if (!c.modResults.contents.includes(marker))
        throw new Error(
          "Unsupported Android application template for call package.",
        );
      c.modResults.contents = c.modResults.contents.replace(
        marker,
        marker + "\n              add(YggdrasCallsPackage())",
      );
    }
    return c;
  });
  config = withMainActivity(config, (c) => {
    // An Answer tapped on the lock screen opens the call over the lock screen.
    let text = c.modResults.contents;
    if (!text.includes("YggdrasLockScreen.apply")) {
      const marker = "super.onCreate(null)";
      if (!text.includes(marker))
        throw new Error("Unsupported Android activity template for calls.");
      text = text.replace(
        marker,
        marker + "\n    YggdrasLockScreen.apply(this, intent)",
      );
      text = text.replace(
        /\n}\s*$/,
        [
          "",
          "",
          "  override fun onNewIntent(intent: android.content.Intent) {",
          "    super.onNewIntent(intent)",
          "    YggdrasLockScreen.apply(this, intent)",
          "  }",
          "}",
          "",
        ].join("\n"),
      );
    }
    c.modResults.contents = text;
    return c;
  });
  return withDangerousMod(config, [
    "android",
    async (c) => {
      const folder = path.join(
        c.modRequest.platformProjectRoot,
        "app/src/main/java/app/yggdras/mobile",
      );
      await fs.mkdir(folder, { recursive: true });
      await fs.copyFile(
        path.join(__dirname, "../native/YggdrasCalls.kt"),
        path.join(folder, "YggdrasCalls.kt"),
      );
      return c;
    },
  ]);
};

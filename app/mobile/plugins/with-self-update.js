const {
  withAndroidManifest,
  withDangerousMod,
  withMainApplication,
} = require("expo/config-plugins");
const fs = require("node:fs/promises");
const path = require("node:path");

// Self-update (rationale/decisions/android-self-update.md): permission to install
// its own APKs, plus the receiver for install results and "app was updated".
const PERMISSIONS = [
  "android.permission.REQUEST_INSTALL_PACKAGES",
  "android.permission.UPDATE_PACKAGES_WITHOUT_USER_ACTION",
];
const RECEIVER = ".YggdrasUpdateReceiver";

function applyManifest(manifest) {
  const uses = (manifest["uses-permission"] = manifest["uses-permission"] || []);
  for (const name of PERMISSIONS)
    if (!uses.some((p) => p.$["android:name"] === name))
      uses.push({ $: { "android:name": name } });
  const app = manifest.application[0];
  app.receiver = (app.receiver || []).filter(
    (r) => r.$["android:name"] !== RECEIVER,
  );
  app.receiver.push({
    $: { "android:name": RECEIVER, "android:exported": "false" },
    "intent-filter": [
      {
        action: [
          { $: { "android:name": "android.intent.action.MY_PACKAGE_REPLACED" } },
        ],
      },
    ],
  });
  return manifest;
}

function applyMainApplication(contents) {
  if (contents.includes("add(YggdrasUpdaterPackage())")) return contents;
  const marker = "PackageList(this).packages.apply {";
  if (!contents.includes(marker))
    throw new Error("Unsupported Android application template for self-update.");
  return contents.replace(
    marker,
    marker + "\n              add(YggdrasUpdaterPackage())",
  );
}

module.exports = function withSelfUpdate(config) {
  config = withAndroidManifest(config, (c) => {
    applyManifest(c.modResults.manifest);
    return c;
  });
  config = withMainApplication(config, (c) => {
    c.modResults.contents = applyMainApplication(c.modResults.contents);
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
        path.join(__dirname, "../native/YggdrasUpdater.kt"),
        path.join(folder, "YggdrasUpdater.kt"),
      );
      return c;
    },
  ]);
};
module.exports.applyManifest = applyManifest;
module.exports.applyMainApplication = applyMainApplication;

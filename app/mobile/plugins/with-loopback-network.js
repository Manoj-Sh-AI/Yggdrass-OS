const {
  withAndroidManifest,
  withDangerousMod,
} = require("expo/config-plugins");
const fs = require("node:fs/promises");
const path = require("node:path");
module.exports = function (config) {
  config = withAndroidManifest(config, (c) => {
    c.modResults.manifest.application[0].$["android:networkSecurityConfig"] =
      "@xml/yggdras_network_security";
    return c;
  });
  return withDangerousMod(config, [
    "android",
    async (c) => {
      const directory = path.join(
        c.modRequest.platformProjectRoot,
        "app/src/main/res/xml",
      );
      await fs.mkdir(directory, { recursive: true });
      await fs.writeFile(
        path.join(directory, "yggdras_network_security.xml"),
        '<?xml version="1.0" encoding="utf-8"?><network-security-config><base-config cleartextTrafficPermitted="false"/><domain-config cleartextTrafficPermitted="true"><domain includeSubdomains="false">127.0.0.1</domain><domain includeSubdomains="false">localhost</domain></domain-config></network-security-config>',
      );
      return c;
    },
  ]);
};

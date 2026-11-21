const { withAppBuildGradle } = require("expo/config-plugins");

// Release APKs are signed with Manoj's own upload key, never the public debug key
// that every React Native template ships. The key and its passwords live in
// local-data/android-signing (git-ignored); YGGDRAS_ANDROID_SIGNING names its
// properties file. A release build without it stops instead of signing with debug.
const MARKER = "// yggdras-release-signing";

const SIGNING_CONFIG = `
        release { ${MARKER}
            def yggdrasSigning = System.getenv('YGGDRAS_ANDROID_SIGNING')
            if (yggdrasSigning && file(yggdrasSigning).isFile()) {
                def values = new Properties()
                file(yggdrasSigning).withInputStream { values.load(it) }
                storeFile file(values['storeFile'])
                storePassword values['storePassword']
                keyAlias values['keyAlias']
                keyPassword values['keyPassword']
            }
        }`;

const GUARD = `
${MARKER}
gradle.taskGraph.whenReady { graph ->
    def signing = System.getenv('YGGDRAS_ANDROID_SIGNING')
    if (graph.allTasks.any { it.name.contains('Release') } && !(signing && file(signing).isFile())) {
        throw new GradleException('Release signing key missing: run android-tools.py android-key once, then build with android-tools.py build.')
    }
}
`;

function applyReleaseSigning(gradle) {
  if (gradle.includes(MARKER)) return gradle;
  const debugBlock = /(signingConfigs\s*\{\s*debug\s*\{[^}]*\})/;
  const releaseUse =
    /(buildTypes\s*\{[\s\S]*?release\s*\{[\s\S]*?)signingConfig signingConfigs\.debug/;
  if (!debugBlock.test(gradle) || !releaseUse.test(gradle)) {
    throw new Error("app/build.gradle layout changed; release signing not applied.");
  }
  return (
    gradle
      .replace(debugBlock, `$1${SIGNING_CONFIG}`)
      .replace(releaseUse, "$1signingConfig signingConfigs.release") + GUARD
  );
}

module.exports = function withReleaseSigning(config) {
  return withAppBuildGradle(config, (c) => {
    c.modResults.contents = applyReleaseSigning(c.modResults.contents);
    return c;
  });
};
module.exports.applyReleaseSigning = applyReleaseSigning;

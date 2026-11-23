// eslint-disable-next-line @typescript-eslint/no-require-imports
const { applyReleaseSigning } = require("../plugins/with-release-signing");

const TEMPLATE = `android {
    signingConfigs {
        debug {
            storeFile file('debug.keystore')
            storePassword 'android'
            keyAlias 'androiddebugkey'
            keyPassword 'android'
        }
    }
    buildTypes {
        debug {
            signingConfig signingConfigs.debug
        }
        release {
            // Caution! In production, you need to generate your own keystore file.
            signingConfig signingConfigs.debug
            minifyEnabled enableMinifyInReleaseBuilds
        }
    }
}
`;

describe("release signing plugin", () => {
  it("signs release with the owner's key and keeps debug on the debug key", () => {
    const result: string = applyReleaseSigning(TEMPLATE);
    const buildTypes = result.slice(result.indexOf("buildTypes"));
    expect(buildTypes).toMatch(/debug \{\s*signingConfig signingConfigs\.debug/);
    expect(buildTypes).toMatch(/release \{[\s\S]*signingConfig signingConfigs\.release/);
    expect(buildTypes).not.toMatch(/release \{[^}]*signingConfigs\.debug/);
    expect(result).toContain("System.getenv('YGGDRAS_ANDROID_SIGNING')");
  });

  it("stops a release build when the key is missing", () => {
    expect(applyReleaseSigning(TEMPLATE)).toContain("throw new GradleException");
  });

  it("is applied once", () => {
    const once: string = applyReleaseSigning(TEMPLATE);
    expect(applyReleaseSigning(once)).toBe(once);
  });

  it("refuses an unknown build.gradle layout instead of silently skipping", () => {
    expect(() => applyReleaseSigning("android {}")).toThrow(/layout changed/);
  });
});

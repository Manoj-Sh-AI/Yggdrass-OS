// eslint-disable-next-line @typescript-eslint/no-require-imports
const plugin = require("../plugins/with-self-update");

type Item = { $: Record<string, string>; [key: string]: unknown };
type Manifest = { "uses-permission"?: Item[]; application: { receiver?: Item[] }[] };

test("adds the install permissions and one non-exported update receiver", () => {
  const manifest: Manifest = { application: [{}] };
  plugin.applyManifest(manifest);
  plugin.applyManifest(manifest);
  const permissions = manifest["uses-permission"]!.map((p) => p.$["android:name"]);
  expect(permissions).toEqual([
    "android.permission.REQUEST_INSTALL_PACKAGES",
    "android.permission.UPDATE_PACKAGES_WITHOUT_USER_ACTION",
  ]);
  const receivers = manifest.application[0].receiver!;
  expect(receivers).toHaveLength(1);
  expect(receivers[0].$).toEqual({
    "android:name": ".YggdrasUpdateReceiver",
    "android:exported": "false",
  });
  expect(JSON.stringify(receivers[0])).toContain("MY_PACKAGE_REPLACED");
});

test("registers the native package once", () => {
  const template = "override fun getPackages() = PackageList(this).packages.apply {\n}";
  const once = plugin.applyMainApplication(template);
  expect(plugin.applyMainApplication(once)).toBe(once);
  expect(once.match(/add\(YggdrasUpdaterPackage\(\)\)/g)).toHaveLength(1);
  expect(() => plugin.applyMainApplication("class X")).toThrow(/Unsupported/);
});

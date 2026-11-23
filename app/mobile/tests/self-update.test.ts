import { CHECK_EVERY, GRACE, SelfUpdater, type UpdaterDeps } from "../src/self-update";

jest.mock("expo-application", () => ({ nativeBuildVersion: "3" }));
jest.mock("expo-file-system", () => ({ File: class {}, Paths: {} }));
jest.mock("../src/server", () => ({ SERVER_ORIGIN: "https://app.example.test" }));

const SHA = "a".repeat(64);
const release = (versionCode: number) => ({
  version: `0.3.${versionCode}`,
  versionCode,
  sha256: SHA,
  url: `https://app.example.test/api/mobile-updates/apk/${SHA}.apk`,
});

function setup(versionCode = 4) {
  let clock = 1_000_000;
  let pending: (() => void) | null = null;
  const deps: jest.Mocked<UpdaterDeps> = {
    fetchRelease: jest.fn().mockResolvedValue(release(versionCode)),
    download: jest.fn().mockResolvedValue("file:///cache/yggdras-update.apk"),
    discard: jest.fn(),
    canInstall: jest.fn().mockResolvedValue(true),
    install: jest.fn().mockResolvedValue(true),
    now: jest.fn(() => clock),
    setTimer: jest.fn((run: () => void, ms: number) => {
      expect(ms).toBe(GRACE);
      pending = run;
      return 1;
    }),
    clearTimer: jest.fn((_timer: unknown) => {
      pending = null;
    }),
  };
  const updater = new SelfUpdater(deps);
  return {
    deps,
    updater,
    advance: (ms: number) => (clock += ms),
    fire: async () => {
      const run = pending;
      pending = null;
      run?.();
      await new Promise((r) => setImmediate(r));
    },
  };
}

test("installs a newer release after the grace period in the background", async () => {
  const { deps, updater, fire } = setup();
  await updater.check();
  updater.onAppState("background");
  await fire();
  expect(deps.install).toHaveBeenCalledWith("file:///cache/yggdras-update.apk", SHA);
});

test("never installs while a call rings or is in progress", async () => {
  const { deps, updater, fire } = setup();
  await updater.check();
  updater.setCallBusy(true);
  updater.onAppState("background");
  expect(deps.setTimer).not.toHaveBeenCalled();
  updater.onAppState("active");
  updater.onAppState("background");
  await fire();
  expect(deps.install).not.toHaveBeenCalled();
});

test("a call starting during the grace period cancels the install", async () => {
  const { deps, updater, fire } = setup();
  await updater.check();
  updater.onAppState("background");
  updater.setCallBusy(true);
  await fire();
  expect(deps.install).not.toHaveBeenCalled();
});

test("returning to the app cancels the grace period", async () => {
  const { deps, updater, fire } = setup();
  await updater.check();
  updater.onAppState("background");
  updater.onAppState("active");
  await fire();
  expect(deps.clearTimer).toHaveBeenCalled();
  expect(deps.install).not.toHaveBeenCalled();
});

test("checks at most every six hours unless forced", async () => {
  const { deps, updater, advance } = setup();
  await updater.check();
  await updater.check();
  expect(deps.fetchRelease).toHaveBeenCalledTimes(1);
  await updater.check(true);
  expect(deps.fetchRelease).toHaveBeenCalledTimes(2);
  advance(CHECK_EVERY);
  await updater.check();
  expect(deps.fetchRelease).toHaveBeenCalledTimes(3);
  expect(deps.download).toHaveBeenCalledTimes(1);
});

test("an equal or older version is ignored", async () => {
  const { deps, updater, fire } = setup(3);
  await updater.check();
  updater.onAppState("background");
  await fire();
  expect(deps.download).not.toHaveBeenCalled();
  expect(deps.install).not.toHaveBeenCalled();
});

test("a refused install discards the file and downloads again next check", async () => {
  const { deps, updater, fire } = setup();
  deps.install.mockRejectedValueOnce(new Error("hash"));
  await updater.check();
  updater.onAppState("background");
  await fire();
  expect(deps.discard).toHaveBeenCalledWith("file:///cache/yggdras-update.apk");
  await updater.check();
  expect(deps.download).toHaveBeenCalledTimes(2);
});

test("without install permission nothing is attempted", async () => {
  const { deps, updater, fire } = setup();
  deps.canInstall.mockResolvedValue(false);
  await updater.check();
  updater.onAppState("background");
  await fire();
  expect(deps.install).not.toHaveBeenCalled();
});

test("a failed download is retried on the next check", async () => {
  const { deps, updater } = setup();
  deps.download.mockRejectedValueOnce(new Error("offline"));
  await updater.check();
  await updater.check();
  expect(deps.download).toHaveBeenCalledTimes(2);
  expect(updater.ready).not.toBeNull();
});

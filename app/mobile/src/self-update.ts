import { useEffect } from "react";
import { AppState, NativeModules, Platform } from "react-native";
import * as Application from "expo-application";
import { File, Paths } from "expo-file-system";
import { SERVER_ORIGIN } from "./server";

// Native Android updates install themselves "when safe" (rationale/decisions/
// android-self-update.md): download in the background, then install only after the
// app has been in the background for GRACE with no call ringing or in progress.
// Android replaces the process; the next open is the new version.

export const CHECK_EVERY = 6 * 60 * 60 * 1000;
export const GRACE = 2 * 60 * 1000;

export type AndroidRelease = {
  version: string;
  versionCode: number;
  sha256: string;
  url: string;
};

export function availableAndroidRelease(value: unknown): AndroidRelease | null {
  if (!value || typeof value !== "object") return null;
  const release = value as AndroidRelease;
  if (
    !Number.isSafeInteger(release.versionCode) ||
    release.versionCode < 1 ||
    !/^\d+\.\d+\.\d+$/.test(release.version) ||
    !/^[a-f0-9]{64}$/.test(release.sha256) ||
    release.url !==
      `${SERVER_ORIGIN}/api/mobile-updates/apk/${release.sha256}.apk`
  )
    return null;
  return release.versionCode > Number(Application.nativeBuildVersion || 0)
    ? release
    : null;
}

export type UpdaterDeps = {
  fetchRelease: () => Promise<unknown>;
  download: (release: AndroidRelease) => Promise<string>;
  discard: (uri: string) => void;
  canInstall: () => Promise<boolean>;
  install: (uri: string, sha256: string) => Promise<unknown>;
  now: () => number;
  setTimer: (run: () => void, ms: number) => unknown;
  clearTimer: (timer: unknown) => void;
};

export class SelfUpdater {
  private lastCheck = -Infinity;
  private checking = false;
  private timer: unknown = null;
  private callBusy = false;
  ready: { release: AndroidRelease; uri: string } | null = null;

  constructor(private deps: UpdaterDeps) {}

  async check(force = false) {
    const now = this.deps.now();
    if (this.checking || (!force && now - this.lastCheck < CHECK_EVERY)) return;
    this.checking = true;
    this.lastCheck = now;
    try {
      const release = availableAndroidRelease(await this.deps.fetchRelease());
      if (!release) {
        this.ready = null;
        return;
      }
      if (this.ready?.release.sha256 === release.sha256) return;
      this.ready = { release, uri: await this.deps.download(release) };
    } catch {
      // Offline or a failed download: try again on a later check.
      this.lastCheck = -Infinity;
    } finally {
      this.checking = false;
    }
  }

  onAppState(state: string) {
    if (state === "active") {
      this.cancel();
      void this.check();
    } else if (state === "background") this.schedule();
  }

  setCallBusy(busy: boolean) {
    this.callBusy = busy;
    if (busy) this.cancel();
  }

  private schedule() {
    if (!this.ready || this.callBusy || this.timer) return;
    this.timer = this.deps.setTimer(() => {
      this.timer = null;
      void this.installNow();
    }, GRACE);
  }

  private cancel() {
    if (this.timer) this.deps.clearTimer(this.timer);
    this.timer = null;
  }

  private async installNow() {
    const ready = this.ready;
    if (!ready || this.callBusy || !(await this.deps.canInstall())) return;
    try {
      await this.deps.install(ready.uri, ready.release.sha256);
    } catch {
      // The native side refused it (hash, signer, version): drop the file so the
      // next check downloads a fresh copy.
      this.deps.discard(ready.uri);
      this.ready = null;
      this.lastCheck = -Infinity;
    }
  }
}

type NativeUpdater = {
  canInstall: () => Promise<boolean>;
  openInstallSettings: () => void;
  lastStatus: () => Promise<string | null>;
  install: (uri: string, sha256: string) => Promise<boolean>;
};
export const nativeUpdater: NativeUpdater | undefined =
  Platform.OS === "android" ? NativeModules.YggdrasUpdater : undefined;

function deviceDeps(native: NativeUpdater): UpdaterDeps {
  return {
    fetchRelease: async () => {
      const response = await fetch(`${SERVER_ORIGIN}/api/mobile-updates/android`);
      if (!response.ok) throw new Error();
      return (await response.json()).release;
    },
    download: async (release) => {
      const target = new File(Paths.cache, `yggdras-update-${release.versionCode}.apk`);
      if (target.exists) return target.uri;
      return (await File.downloadFileAsync(release.url, target)).uri;
    },
    discard: (uri) => {
      try {
        new File(uri).delete();
      } catch {
        // Already gone.
      }
    },
    canInstall: () => native.canInstall(),
    install: (uri, sha256) => native.install(uri, sha256),
    now: () => Date.now(),
    setTimer: (run, ms) => setTimeout(run, ms),
    clearTimer: (timer) => clearTimeout(timer as ReturnType<typeof setTimeout>),
  };
}

/** Removes downloaded APKs this build has already reached. */
function cleanDownloads() {
  const current = Number(Application.nativeBuildVersion || 0);
  try {
    for (const item of Paths.cache.list()) {
      const match = /^yggdras-update-(\d+)\.apk$/.exec(item.name);
      if (match && Number(match[1]) <= current) item.delete();
    }
  } catch {
    // Cache listing unavailable: nothing to clean.
  }
}

export const selfUpdater: SelfUpdater | null =
  nativeUpdater && !__DEV__ ? new SelfUpdater(deviceDeps(nativeUpdater)) : null;

/** Mounted once inside CallProvider. */
export function useSelfUpdate(callBusy: boolean) {
  useEffect(() => {
    if (!selfUpdater) return;
    cleanDownloads();
    void selfUpdater.check();
    const subscription = AppState.addEventListener("change", (state) =>
      selfUpdater.onAppState(state),
    );
    return () => subscription.remove();
  }, []);
  useEffect(() => {
    selfUpdater?.setCallBusy(callBusy);
  }, [callBusy]);
}

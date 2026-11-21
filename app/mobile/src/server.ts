/** The server address comes from app.config.ts (build-time); never hard-code it elsewhere. */
import Constants from "expo-constants";

const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, unknown>;
export const SERVER_ORIGIN =
  typeof extra.serverOrigin === "string" ? extra.serverOrigin : "";
/** Developer builds only: allow http://127.0.0.1 over `adb reverse`. */
export const DEV_USB = extra.devUsb === true;

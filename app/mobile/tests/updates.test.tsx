import { fireEvent, render, screen } from "@testing-library/react-native";
import { Alert } from "react-native";
import * as Updates from "expo-updates";
import { AppUpdates, availableAndroidRelease } from "../src/updates";
jest.mock("expo-application", () => ({
  nativeBuildVersion: "2",
  nativeApplicationVersion: "0.3.2",
}));
jest.mock("expo-updates", () => ({
  isEnabled: true,
  checkForUpdateAsync: jest.fn(),
  fetchUpdateAsync: jest.fn(),
  reloadAsync: jest.fn(),
}));
jest.mock("../src/server", () => ({
  SERVER_ORIGIN: "https://app.example.test",
}));

beforeEach(() => {
  jest.clearAllMocks();
  global.fetch = jest
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ release: null }) });
  (Updates.checkForUpdateAsync as jest.Mock).mockResolvedValue({
    isAvailable: false,
  });
  (Updates.fetchUpdateAsync as jest.Mock).mockResolvedValue({ isNew: true });
});
test("downloads compatible screens but only reloads after explicit confirmation", async () => {
  (Updates.checkForUpdateAsync as jest.Mock).mockResolvedValue({
    isAvailable: true,
  });
  const alert = jest.spyOn(Alert, "alert");
  render(<AppUpdates />);
  fireEvent.press(screen.getByText("Check for updates"));
  await screen.findByText("Reload to apply update");
  expect(Updates.fetchUpdateAsync).toHaveBeenCalledTimes(1);
  expect(Updates.reloadAsync).not.toHaveBeenCalled();
  fireEvent.press(screen.getByText("Reload to apply update"));
  expect(alert).toHaveBeenCalled();
  expect(Updates.reloadAsync).not.toHaveBeenCalled();
  alert.mockRestore();
});
test("failed update checks keep the installed app and do not reload", async () => {
  (global.fetch as jest.Mock).mockRejectedValue(new Error("offline"));
  render(<AppUpdates />);
  fireEvent.press(screen.getByText("Check for updates"));
  await screen.findByText(
    "Could not check for updates. Try again when connected.",
  );
  expect(Updates.reloadAsync).not.toHaveBeenCalled();
  expect(Updates.fetchUpdateAsync).not.toHaveBeenCalled();
});
test("native upgrade only accepts a newer package on the configured download host", () => {
  const sha256 = "a".repeat(64);
  const value = {
    version: "0.3.3",
    versionCode: 3,
    sha256,
    url: `https://app.example.test/api/mobile-updates/apk/${sha256}.apk`,
  };
  expect(availableAndroidRelease(value)).toEqual(value);
  expect(availableAndroidRelease({ ...value, versionCode: 2 })).toBeNull();
  expect(
    availableAndroidRelease({ ...value, url: "https://other.test/app.apk" }),
  ).toBeNull();
});

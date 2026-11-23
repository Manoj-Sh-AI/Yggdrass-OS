import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react-native";
import { Linking } from "react-native";
import { CallProvider, Calls, SessionNotice } from "../src/call-ui";
import { callApi, callCommand } from "../src/call-api";
import { VoiceTransport } from "../src/voice-transport";
import { ringer } from "../src/calls";
jest.mock("../src/api", () => ({
  MobileError: class MobileError extends Error { status=500; },
  request: jest.fn().mockResolvedValue([]),
  onSessionExpired: jest.fn(() => jest.fn()),
  onSessionChanged: jest.fn(() => jest.fn()),
  session: jest.fn(() => null),
}));
jest.mock("../src/call-api", () => ({
  callApi: {
    snapshot: jest.fn(),
    preferences: jest.fn(),
    savePreferences: jest.fn(),
    schedule: jest.fn(),
  },
  callCommand: jest.fn(),
  deviceId: jest.fn().mockResolvedValue("phone"),
}));
jest.mock("../src/voice-transport", () => ({
  VoiceTransport: jest.fn().mockImplementation(() => ({
    connect: jest.fn(async (_a, status) => status("simulated")),
    close: jest.fn().mockResolvedValue(undefined),
    mute: jest.fn(),
    speaker: jest.fn(),
  })),
}));
jest.mock("../src/calls", () => ({
  ringer: {
    listen: jest.fn(() => jest.fn()),
    stop: jest.fn().mockResolvedValue(undefined),
    register: jest.fn(),
    disable: jest.fn(),
    fullScreenSettings: jest.fn(),
    reconcile: jest.fn().mockResolvedValue(undefined),
    ringInApp: jest.fn(),
    overLockScreen: jest.fn(),
  },
}));
const cap = { mode: "disabled", voice_ready: false, push_ready: false };
beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(Linking, "getInitialURL").mockResolvedValue(null);
  (callApi.snapshot as jest.Mock).mockResolvedValue({
    calls: [],
    capabilities: cap,
  });
  (callApi.preferences as jest.Mock).mockResolvedValue({
    version: 1,
    scheduled: true,
    calendar_starts: true,
    calendar_ends: true,
    routines: true,
    timezone: "Europe/Berlin",
    quiet_start: "22:00",
    quiet_end: "08:00",
  });
});
test("missing configuration disables real calls and asks for no microphone access", async () => {
  render(
    <CallProvider>
      <Calls />
    </CallProvider>,
  );
  await screen.findByText("Live activation is off");
  expect(screen.getByRole("button", { name: "Call Yggdras" })).toBeDisabled();
  fireEvent.press(screen.getByText("Call Yggdras"));
  expect(callCommand).not.toHaveBeenCalled();
});
test("simulated transport stays explicitly simulated rather than claiming connected", async () => {
  (callApi.snapshot as jest.Mock).mockResolvedValue({
    calls: [],
    capabilities: {
      ...cap,
      mode: "simulated",
      simulated: true,
      voice_ready: true,
    },
  });
  (callCommand as jest.Mock).mockResolvedValue({
    id: "fixture",
    state: "answered",
    version: 1,
    simulated: true,
    url: "sim://livekit",
    token: "",
  });
  render(
    <CallProvider>
      <Calls />
    </CallProvider>,
  );
  await screen.findByText("Simulation service");
  fireEvent.press(screen.getByText("Call Yggdras"));
  await waitFor(() => expect(VoiceTransport).toHaveBeenCalled());
  expect(screen.queryByText(/^connected$/)).toBeNull();
});
test("an expired notification action cannot answer a call", async () => {
  const id = "11111111-1111-4111-8111-111111111111";
  (Linking.getInitialURL as jest.Mock).mockResolvedValue(
    `yggdras://calls/${id}?action=answer`,
  );
  (callApi.snapshot as jest.Mock).mockResolvedValue({
    calls: [{ id, state: "ringing", expires_at: "2000-01-01T00:00:00Z" }],
    capabilities: cap,
  });
  render(
    <CallProvider>
      <Calls />
    </CallProvider>,
  );
  await screen.findByText("Live activation is off");
  expect(callCommand).not.toHaveBeenCalled();
  expect(screen.queryByText("Answer")).toBeNull();
});
test("preference failures preserve entered quiet hours and show the error", async () => {
  (callApi.savePreferences as jest.Mock).mockRejectedValue(
    new Error("Call preferences changed. Refresh before saving."),
  );
  render(
    <CallProvider>
      <Calls />
    </CallProvider>,
  );
  const input = await screen.findByLabelText("Quiet hours end (HH:mm)");
  fireEvent.changeText(input, "09:00");
  fireEvent.press(screen.getByText("Save call preferences"));
  await screen.findByText("Call preferences changed. Refresh before saving.");
  expect(input.props.value).toBe("09:00");
});

test("a ringing call plays the chime and stops it once answered on another device", async () => {
  const id = "22222222-2222-4222-8222-222222222222";
  const expires = new Date(Date.now() + 40000).toISOString();
  const ringingCall = { id, state: "ringing", expires_at: expires, version: 1 };
  (callApi.snapshot as jest.Mock).mockResolvedValue({
    calls: [ringingCall],
    capabilities: cap,
  });
  const view = render(
    <CallProvider>
      <Calls />
    </CallProvider>,
  );
  await waitFor(() => expect(ringer.ringInApp).toHaveBeenCalledWith(id, expires));
  expect(ringer.stop).not.toHaveBeenCalled();
  (callApi.snapshot as jest.Mock).mockResolvedValue({
    calls: [{ ...ringingCall, state: "answered", answered_by: "web-desk" }],
    capabilities: cap,
  });
  fireEvent.press(screen.getByText("Refresh calls"));
  await waitFor(() => expect(ringer.stop).toHaveBeenCalledWith(id));
  view.unmount();
});
test("a simulated call rings silently", async () => {
  const id = "33333333-3333-4333-8333-333333333333";
  (callApi.snapshot as jest.Mock).mockResolvedValue({
    calls: [{ id, state: "ringing", simulated: true, version: 1,
      expires_at: new Date(Date.now() + 40000).toISOString() }],
    capabilities: cap,
  });
  render(
    <CallProvider>
      <Calls />
    </CallProvider>,
  );
  await screen.findAllByText("Answer");
  expect(ringer.ringInApp).not.toHaveBeenCalled();
});

test("the phone says until when it will ring, and when its sign-in has expired", () => {
  const now = Date.parse("2026-11-20T12:00:00Z");
  const view = render(
    <SessionNotice expiresAt="2026-11-20T20:00:00Z" now={now} />,
  );
  expect(view.getByText(/^Rings this phone until/)).toBeTruthy();
  view.rerender(<SessionNotice expiresAt="2026-11-20T11:00:00Z" now={now} />);
  expect(view.getByText(/has expired, so it will not ring/)).toBeTruthy();
  view.rerender(<SessionNotice />);
  expect(view.toJSON()).toBeNull();
});

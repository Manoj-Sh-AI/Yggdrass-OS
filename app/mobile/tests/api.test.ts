import * as SecureStore from "expo-secure-store";
import {
  api,
  command,
  request,
  restore,
  session,
  signIn,
  validOrigin,
} from "../src/api";

const token = "a".repeat(43);
const response = (data: unknown, ok = true, status = 200) =>
  ({ ok, status, json: async () => data }) as Response;
beforeEach(() => {
  jest.clearAllMocks();
  global.fetch = jest.fn() as typeof fetch;
});
async function login() {
  (fetch as jest.Mock).mockResolvedValueOnce(
    response({ token, expires_at: "2099-01-01T00:00:00Z" }),
  );
  await signIn("https://example.test", "invented password only");
}
test("only application tokens enter device secure storage", async () => {
  await login();
  const [key, raw] = (SecureStore.setItemAsync as jest.Mock).mock.calls[0];
  expect(key).toContain("mobile.session");
  expect(raw).not.toContain("password");
  expect(JSON.parse(raw).token).toBe(token);
  (fetch as jest.Mock).mockResolvedValueOnce(response({ tasks: [] }));
  await request("application/tasks");
  expect((fetch as jest.Mock).mock.calls[1][1].headers.Authorization).toBe(
    `Bearer ${token}`,
  );
});
test("an interrupted write retries the same receipt without losing its input", async () => {
  await login();
  (fetch as jest.Mock).mockRejectedValueOnce(new Error("offline"));
  await expect(
    command("application/planning/commands", "task.create", {
      title: "Invented task",
    }),
  ).rejects.toThrow("draft is still here");
  (fetch as jest.Mock).mockResolvedValueOnce(response({ id: "saved" }));
  await command("application/planning/commands", "task.create", {
    title: "Invented task",
  });
  const calls = (fetch as jest.Mock).mock.calls;
  expect(calls[1][1].body).toBe(calls[2][1].body);
});
test("session restoration validates the saved token without resending messages", async () => {
  (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(
    JSON.stringify({
      origin: "https://example.test",
      token,
      expires_at: "2099-01-01T00:00:00Z",
    }),
  );
  (fetch as jest.Mock).mockResolvedValueOnce(response({ authenticated: true }));
  expect(await restore()).toEqual({
    origin: "https://example.test",
    token,
    expires_at: "2099-01-01T00:00:00Z",
  });
  expect((fetch as jest.Mock).mock.calls).toHaveLength(1);
  expect((fetch as jest.Mock).mock.calls[0][0]).toContain("auth/session");
});
test("logout revokes server access before clearing local credentials", async () => {
  await login();
  (fetch as jest.Mock).mockResolvedValueOnce(
    response({ authenticated: false }),
  );
  await api.logout();
  expect(session()).toBeNull();
  expect(SecureStore.deleteItemAsync).toHaveBeenCalled();
});
test("cleartext credentials are confined to loopback USB development", () => {
  expect(validOrigin("http://127.0.0.1:3000", true)).toBe("http://127.0.0.1:3000");
  expect(() => validOrigin("http://127.0.0.1:3000", false)).toThrow("HTTPS");
  expect(validOrigin("https://web.example.test/")).toBe("https://web.example.test");
  expect(() => validOrigin("http://example.test")).toThrow("HTTPS");
  expect(() => validOrigin("https://user:password@example.test")).toThrow(
    "credentials",
  );
});

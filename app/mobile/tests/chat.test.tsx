import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react-native";
import { Chat } from "../src/chat";
import { api } from "../src/api";

jest.mock("../src/api", () => ({
  api: {
    conversations: jest.fn(),
    catalog: jest.fn(),
    history: jest.fn(),
    chat: jest.fn(),
  },
}));
const conversation = {
  id: "conversation-one",
  title: "Invented conversation",
  version: 2,
  agent_id: "yggdras",
  model_id: "default",
  archived: false,
};
beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  (api.conversations as jest.Mock).mockResolvedValue({
    conversations: [conversation],
    next: null,
  });
  (api.catalog as jest.Mock).mockResolvedValue({
    catalog: {
      agents: [
        {
          id: "yggdras",
          name: "Yggdras",
          available: false,
          models: ["default"],
        },
      ],
      models: [{ id: "default", name: "Default", available: false }],
    },
  });
  (api.history as jest.Mock).mockResolvedValue({
    conversation,
    messages: [
      {
        id: "message",
        role: "user",
        content: "An invented saved message",
        version: 1,
        ordinal: 1,
        deleted_at: null,
      },
    ],
    requests: [
      { id: "request", user_message_id: "message", state: "held", version: 1 },
    ],
    attachments: [],
    next_before: null,
  });
});
afterEach(() => jest.useRealTimers());
async function openChat() {
  render(<Chat active />);
  await act(async () => {
    jest.advanceTimersByTime(250);
  });
  fireEvent.press(screen.getByLabelText("Open Invented conversation"));
  await waitFor(() =>
    expect(screen.getByText("An invented saved message")).toBeTruthy(),
  );
}
test("opens saved conversation without automatically processing held messages", async () => {
  await openChat();
  expect(api.chat).not.toHaveBeenCalled();
  expect(screen.getByText("Saved. Not sent to an agent.")).toBeTruthy();
});
test("an unavailable agent saves a message without queueing it for later processing", async () => {
  await openChat();
  (api.chat as jest.Mock).mockResolvedValue({});
  fireEvent.changeText(screen.getByLabelText("Message"), "My invented draft");
  fireEvent.press(screen.getByText("Save message"));
  await waitFor(() =>
    expect(api.chat).toHaveBeenCalledWith(
      "message.send",
      { content: "My invented draft", attachment_ids: [], deliver: false },
      conversation.id,
    ),
  );
});
test("failed message submission preserves the complete editable draft", async () => {
  await openChat();
  (api.chat as jest.Mock).mockRejectedValue(new Error("Connection lost"));
  fireEvent.changeText(
    screen.getByLabelText("Message"),
    "Do not lose this invented message",
  );
  fireEvent.press(screen.getByText("Save message"));
  await waitFor(() => expect(screen.getByText("Connection lost")).toBeTruthy());
  expect(
    screen.getByDisplayValue("Do not lose this invented message"),
  ).toBeTruthy();
});

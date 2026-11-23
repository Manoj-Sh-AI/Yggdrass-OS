import { Alert } from "react-native";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react-native";
import { TaskDetails, Tasks } from "../src/tasks";
import { api } from "../src/api";
import type { Task, Snapshot } from "../src/types";

jest.mock("../src/api", () => ({ api: { plan: jest.fn() } }));
const task = {
  id: "task-b",
  title: "Invented task",
  objective: "Original goal stays fixed",
  state: "todo",
  progress: 0,
  actual_seconds: 0,
  estimated_minutes: 30,
  version: 4,
  description: "",
  due_date: null,
  done: false,
} as Task;
const mockSnapshot = {
  tasks: [{ ...task, id: "task-a", version: 7 }, task],
  sessions: [
    {
      id: "session",
      task_id: "task-a",
      started_at: "2026-11-16T08:00:00Z",
      ended_at: null,
    },
  ],
  server_now: new Date().toISOString(),
} as Snapshot;
jest.mock("../src/workspace", () => ({
  useWorkspace: () => ({ timezone: "Europe/Berlin" }),
  usePlanning: () => ({
    snapshot: mockSnapshot,
    loading: false,
    error: "",
    refresh: jest.fn(),
    changed: jest.fn(),
  }),
}));
beforeEach(() => {
  jest.clearAllMocks();
  (api.plan as jest.Mock).mockResolvedValue({});
});
test("inspecting a task leaves focus unchanged; explicit focus asks first", async () => {
  const alert = jest.spyOn(Alert, "alert");
  const changed = jest.fn();
  render(
    <TaskDetails
      task={task}
      snapshot={mockSnapshot}
      onClose={jest.fn()}
      onChanged={changed}
    />,
  );
  expect(screen.getByText("Original goal stays fixed")).toBeTruthy();
  expect(api.plan).not.toHaveBeenCalled();
  fireEvent.press(screen.getByText("Focus on this"));
  expect(api.plan).not.toHaveBeenCalled();
  const buttons = alert.mock.calls[0][2]!;
  await act(async () =>
    buttons.find((button) => button.text === "Start focus")!.onPress!(),
  );
  await waitFor(() =>
    expect(api.plan).toHaveBeenCalledWith(
      "focus.switch",
      { from_task_id: "task-a", from_version: 7 },
      "task-b",
      4,
    ),
  );
  alert.mockRestore();
});
test("completion uses the current version and never changes the goal", async () => {
  render(
    <TaskDetails
      task={task}
      snapshot={mockSnapshot}
      onClose={jest.fn()}
      onChanged={jest.fn()}
    />,
  );
  fireEvent.press(screen.getByText("Complete task"));
  await waitFor(() =>
    expect(api.plan).toHaveBeenCalledWith(
      "task.execute",
      { action: "complete" },
      "task-b",
      4,
    ),
  );
});
test("a failed task save keeps all entered content available to retry", async () => {
  (api.plan as jest.Mock).mockRejectedValue(
    new Error("Offline; your draft is still here."),
  );
  render(<Tasks active />);
  fireEvent.press(screen.getByText("New task"));
  fireEvent.changeText(
    screen.getByLabelText("Task title"),
    "Invented new task",
  );
  fireEvent.changeText(screen.getByLabelText("Goal"), "Keep my goal");
  fireEvent.press(screen.getByText("Save task"));
  await waitFor(() =>
    expect(screen.getByText("Offline; your draft is still here.")).toBeTruthy(),
  );
  expect(screen.getByDisplayValue("Invented new task")).toBeTruthy();
  expect(screen.getByDisplayValue("Keep my goal")).toBeTruthy();
});

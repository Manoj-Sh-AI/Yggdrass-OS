import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react-native";
import { GoalEditor, RoutineEditor } from "../src/planning-library";
import { TaskEditor } from "../src/tasks";
import { api } from "../src/api";
jest.mock("../src/api", () => ({ api: { plan: jest.fn() } }));
jest.mock("../src/workspace", () => ({
  useWorkspace: () => ({ timezone: "Europe/Berlin" }),
}));
beforeEach(() => jest.clearAllMocks());
test("a goal failure keeps its draft and does not close the editor", async () => {
  (api.plan as jest.Mock).mockRejectedValue(new Error("Offline"));
  const close = jest.fn();
  render(<GoalEditor goal={null} close={close} saved={jest.fn()} />);
  fireEvent.changeText(screen.getByLabelText("Goal title"), "Invented goal");
  fireEvent.press(screen.getByText("Save goal"));
  await screen.findByText("Offline");
  expect(close).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Goal title").props.value).toBe("Invented goal");
});
test("new routines carry an explicit local window, weekdays and timezone", async () => {
  (api.plan as jest.Mock).mockResolvedValue({});
  render(<RoutineEditor routine={null} close={jest.fn()} saved={jest.fn()} />);
  fireEvent.changeText(screen.getByLabelText("Routine title"), "Invented walk");
  fireEvent.changeText(
    screen.getByLabelText("Routine objective"),
    "Take a break",
  );
  fireEvent.changeText(screen.getByLabelText("Window starts (HH:mm)"), "14:00");
  fireEvent.changeText(screen.getByLabelText("Window ends (HH:mm)"), "14:30");
  fireEvent.press(screen.getByText("Save routine"));
  await waitFor(() =>
    expect(api.plan).toHaveBeenCalledWith(
      "routine.create",
      expect.objectContaining({
        timezone: "Europe/Berlin",
        window_start: "14:00",
        window_end: "14:30",
        objective: "Take a break",
        weekdays: [0, 1, 2, 3, 4, 5, 6],
      }),
      undefined,
      undefined,
    ),
  );
});
test("a native task deadline is saved as an instant, never a floating wall time", async () => {
  (api.plan as jest.Mock).mockResolvedValue({});
  render(<TaskEditor task={null} onClose={jest.fn()} onSaved={jest.fn()} />);
  fireEvent.changeText(
    screen.getByLabelText("Task title"),
    "Invented deadline",
  );
  fireEvent.changeText(screen.getByLabelText("Goal"), "Keep this fixed");
  fireEvent.changeText(
    screen.getByLabelText("Deadline date (YYYY-MM-DD)"),
    "2030-04-10",
  );
  fireEvent.changeText(screen.getByLabelText("Deadline time (HH:mm)"), "10:30");
  fireEvent.press(screen.getByText("Save task"));
  await waitFor(() =>
    expect(api.plan).toHaveBeenCalledWith(
      "task.create",
      expect.objectContaining({
        deadline_at: "2030-04-10T08:30:00.000Z",
        objective: "Keep this fixed",
      }),
      undefined,
      undefined,
    ),
  );
});
test("a nonexistent DST deadline preserves the draft without sending a command", async () => {
  render(<TaskEditor task={null} onClose={jest.fn()} onSaved={jest.fn()} />);
  fireEvent.changeText(
    screen.getByLabelText("Task title"),
    "Invented deadline",
  );
  fireEvent.changeText(screen.getByLabelText("Goal"), "Keep this fixed");
  fireEvent.changeText(
    screen.getByLabelText("Deadline date (YYYY-MM-DD)"),
    "2030-03-31",
  );
  fireEvent.changeText(screen.getByLabelText("Deadline time (HH:mm)"), "02:30");
  fireEvent.press(screen.getByText("Save task"));
  await waitFor(() =>
    expect(screen.getByLabelText("Deadline time (HH:mm)").props.value).toBe(
      "02:30",
    ),
  );
  expect(api.plan).not.toHaveBeenCalled();
});

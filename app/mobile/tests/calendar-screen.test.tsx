import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { Calendar } from "../src/calendar";
import { api } from "../src/api";
import { addDays, dayKey } from "../src/dates";

const zone = "Europe/Berlin";
const today = dayKey(new Date(), zone);
const tomorrow = addDays(today, 1);
const mockTask = {
  id: "invented-task",
  title: "Invented errand",
  objective: "",
  description: "",
  area: "personal",
  due_date: tomorrow,
  deadline_at: null,
  timezone: zone,
  state: "todo",
  progress: 0,
  version: 4,
  done: false,
  estimated_minutes: 30,
  actual_seconds: 0,
  priority: 0,
  effort: "",
  tags: [],
  goal_id: null,
  project_id: null,
  parent_id: null,
};
const mockEvent = {
  id: "invented-event",
  title: "Invented dentist",
  description: "",
  starts_at: `${tomorrow}T08:00:00Z`,
  ends_at: `${tomorrow}T09:00:00Z`,
  timezone: zone,
  version: 1,
};
jest.mock("../src/api", () => ({ api: { plan: jest.fn(), time: jest.fn() } }));
const mockChanged = jest.fn();
jest.mock("../src/workspace", () => ({
  useWorkspace: () => ({ timezone: "Europe/Berlin" }),
  usePlanning: () => ({
    snapshot: {
      tasks: [mockTask],
      blocks: [],
      events: [mockEvent],
      date_items: [],
      availability: [],
      sessions: [],
    },
    error: "",
    loading: false,
    refresh: jest.fn(),
    changed: mockChanged,
  }),
}));

test("the schedule opens first and lists events and tasks together", () => {
  render(<Calendar active />);
  expect(screen.getByLabelText("Event: Invented dentist")).toBeTruthy();
  expect(screen.getByLabelText("Task: Invented errand")).toBeTruthy();
});

test("a task is ticked off right in the calendar", async () => {
  (api.plan as jest.Mock).mockClear().mockResolvedValue({});
  render(<Calendar active />);
  fireEvent.press(screen.getByLabelText("Complete Invented errand"));
  await waitFor(() =>
    expect(api.plan).toHaveBeenCalledWith(
      "task.execute",
      { action: "complete" },
      "invented-task",
      4,
    ),
  );
  expect(mockChanged).toHaveBeenCalled();
});

test("the menu switches to the month view, and a day opens its timeline", () => {
  render(<Calendar active />);
  fireEvent.press(screen.getByLabelText("Calendar views and filters"));
  fireEvent.press(screen.getByLabelText("Month"));
  fireEvent.press(screen.getByLabelText(`${tomorrow}, 2 items`));
  // Day view: the hour grid offers to create an event at a time.
  expect(screen.getByLabelText(`New event ${tomorrow} 09:00`)).toBeTruthy();
  expect(screen.getByLabelText(/Event: Invented dentist, /)).toBeTruthy();
});

test("filters hide a kind of item", () => {
  render(<Calendar active />);
  fireEvent.press(screen.getByLabelText("Calendar views and filters"));
  fireEvent.press(screen.getByLabelText("Tasks"));
  fireEvent.press(screen.getByText("Close"));
  expect(screen.queryByLabelText("Task: Invented errand")).toBeNull();
  expect(screen.getByLabelText("Event: Invented dentist")).toBeTruthy();
});

test("a new task from the calendar starts due on the chosen day", () => {
  render(<Calendar active />);
  fireEvent.press(screen.getByLabelText("Create"));
  fireEvent.press(screen.getByLabelText("New task"));
  expect(screen.getByDisplayValue(today)).toBeTruthy();
});

import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react-native";
import { Calendar, EventEditor } from "../src/calendar";
import { api } from "../src/api";

jest.mock("../src/api", () => ({ api: { plan: jest.fn(), time: jest.fn() } }));
const openNewEvent = () => {
  fireEvent.press(screen.getByLabelText("Create"));
  fireEvent.press(screen.getByLabelText("New event"));
};
jest.mock("../src/workspace", () => ({
  useWorkspace: () => ({ timezone: "Europe/Berlin" }),
  usePlanning: () => ({
    snapshot: {
      tasks: [],
      blocks: [],
      events: [],
      date_items: [],
      availability: [],
    },
    error: "",
    loading: false,
    refresh: jest.fn(),
    changed: jest.fn(),
  }),
}));
test("all-day dates save with an exclusive end and no invented clock time", async () => {
  (api.time as jest.Mock).mockResolvedValue({});
  render(<Calendar active />);
  openNewEvent();
  fireEvent.press(screen.getByText("All day"));
  fireEvent.changeText(screen.getByLabelText("Title"), "Invented trip");
  fireEvent.changeText(
    screen.getByLabelText("Date (YYYY-MM-DD)"),
    "2030-04-10",
  );
  fireEvent.changeText(
    screen.getByLabelText("Last day (inclusive)"),
    "2030-04-12",
  );
  fireEvent.press(screen.getByText("Save calendar item"));
  await waitFor(() =>
    expect(api.time).toHaveBeenCalledWith(
      "date_item.create",
      {
        title: "Invented trip",
        description: "",
        kind: "event",
        starts_on: "2030-04-10",
        ends_before: "2030-04-13",
      },
      undefined,
      undefined,
    ),
  );
});
test("a timed appointment carries an explicit instant and named timezone", async () => {
  (api.plan as jest.Mock).mockResolvedValue({});
  render(<Calendar active />);
  openNewEvent(); // a new item is a timed appointment by default, as in Google Calendar
  fireEvent.changeText(screen.getByLabelText("Title"), "Invented appointment");
  fireEvent.changeText(
    screen.getByLabelText("Date (YYYY-MM-DD)"),
    "2026-11-16",
  );
  fireEvent.changeText(screen.getByLabelText("Start (HH:mm)"), "09:00");
  fireEvent.changeText(screen.getByLabelText("End (HH:mm)"), "10:00");
  fireEvent.press(screen.getByText("Save calendar item"));
  await waitFor(() =>
    expect(api.plan).toHaveBeenCalledWith(
      "event.create",
      expect.objectContaining({
        start: "2026-11-16T08:00:00.000Z",
        end: "2026-11-16T09:00:00.000Z",
        timezone: "Europe/Berlin",
      }),
      undefined,
      undefined,
    ),
  );
});
test("editing a multi-day appointment preserves both original instants", async () => {
  const item = {
    id: "invented-event",
    title: "Invented overnight event",
    description: "",
    starts_at: "2026-11-16T20:00:00Z",
    ends_at: "2026-11-17T08:00:00Z",
    timezone: "Europe/Berlin",
    version: 3,
  };
  (api.plan as jest.Mock).mockClear().mockResolvedValue({});
  render(
    <EventEditor
      day="2026-11-16"
      selection={{ type: "event", item }}
      onClose={jest.fn()}
      onSaved={jest.fn()}
    />,
  );
  fireEvent.changeText(
    screen.getByLabelText("Title"),
    "Updated overnight title",
  );
  fireEvent.press(screen.getByText("Save calendar item"));
  await waitFor(() =>
    expect(api.plan).toHaveBeenCalledWith(
      "event.update",
      expect.objectContaining({ start: item.starts_at, end: item.ends_at }),
      item.id,
      item.version,
    ),
  );
});

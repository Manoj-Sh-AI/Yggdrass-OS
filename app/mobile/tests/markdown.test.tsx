import { render, screen } from "@testing-library/react-native";
import { blocks, inline, Markdown } from "../src/markdown";

test("inline bold, italic and code lose their markers; a link keeps its text only", () => {
  expect(
    inline("**Role:** you *started* on `1 July` [see](https://example.test)"),
  ).toEqual([
    { text: "Role:", bold: true },
    { text: " you " },
    { text: "started", italic: true },
    { text: " on " },
    { text: "1 July", code: true },
    { text: " " },
    { text: "see" },
  ]);
});

test("headings, bullets, numbered items and paragraphs become blocks", () => {
  const out = blocks(
    "## Plan\n- **Role:** student\n2. Extension\n\nOne line\ncontinues here.",
  );
  expect(out.map((b) => b.kind)).toEqual([
    "heading",
    "bullet",
    "bullet",
    "paragraph",
  ]);
  expect(out[2]).toMatchObject({ marker: "2." });
  expect(out[3].inline[0].text).toBe("One line continues here.");
});

test("unknown syntax stays plain text and nothing renders asterisks for bold", () => {
  render(
    <Markdown
      source={"- **Payroll:** a sensitive note.\n<b>no html</b> 3 * 4"}
    />,
  );
  expect(screen.getByText("Payroll:")).toBeTruthy();
  expect(screen.queryByText(/\*\*Payroll/)).toBeNull();
  expect(screen.getByText(/<b>no html<\/b> 3 \* 4/)).toBeTruthy();
});

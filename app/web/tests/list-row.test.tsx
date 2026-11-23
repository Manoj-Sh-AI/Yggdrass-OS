// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ListGroupLabel, ListRow } from "@/components/primitives";
import { areaLabel } from "@/lib/brain-adapter";

afterEach(cleanup);

describe("ListRow (Phase D anatomy)", () => {
  it("is one 28px title-only row with the full title as a tooltip", () => {
    render(<ListRow title="Invented garden plan for the long weekend" />);
    const row = screen.getByRole("button", { name: /Invented garden plan/ });
    expect(row.className).toContain("h-(--row-h)");
    expect(row.getAttribute("title")).toBe("Invented garden plan for the long weekend");
    expect(row.querySelector(".truncate")).toBeTruthy();
  });
  it("shows state as an icon in the status slot, not a subtitle", () => {
    render(<ListRow title="Invented diary" status={<span role="img" aria-label="Sensitive note">x</span>} />);
    expect(screen.getByRole("img", { name: "Sensitive note" })).toBeTruthy();
    expect(screen.queryByText(/Sensitive note/)).toBeNull(); // no text subtitle
  });
  it("marks the open note with weight and the active state, never a bar", () => {
    render(<ListRow title="Invented" active />);
    const row = screen.getByRole("button");
    expect(row.getAttribute("aria-current")).toBe("page");
    expect(row.className).toContain("bg-(--state-active)");
    expect(row.className).toContain("font-semibold");
    expect(row.className).not.toMatch(/border-l/);
  });
  it("selects on click and indents by depth on the spacing scale", () => {
    const onSelect = vi.fn();
    render(<ListRow title="Invented child" depth={2} onSelect={onSelect} />);
    const row = screen.getByRole("button");
    fireEvent.click(row);
    expect(onSelect).toHaveBeenCalledOnce();
    expect(row.getAttribute("style")).toContain("calc(var(--spacing) * 9)");
  });
  it("keeps the status slot when actions are present (actions overlay it)", () => {
    render(<ListRow title="Invented" status={<i>s</i>} actions={<i>a</i>} />);
    expect(screen.getByText("s").parentElement!.className).toContain("group-hover/row:invisible");
    expect(screen.getByText("a").parentElement!.className).toContain("group-hover/row:visible");
  });
  it("group label carries the name once with an optional count", () => {
    render(<ListGroupLabel count={3}>Health</ListGroupLabel>);
    expect(screen.getByText("Health")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
  });
});

describe("area names (the '01' bug)", () => {
  it.each([
    ["03-health", "Health"],
    ["14-inbox", "Inbox"],
    ["01", "Area 01"],
    ["cross", "Cross"],
    ["02-german-language", "German language"],
  ])("%s -> %s", (id, label) => expect(areaLabel(id)).toBe(label));
});

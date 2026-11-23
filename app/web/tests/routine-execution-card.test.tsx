import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RoutineExecutionCard } from "../src/components/routine-execution-card";
import {
  applyRoutineAction,
  createRoutineStore,
  type RoutineStore,
} from "../src/lib/routines";
const initial = createRoutineStore(new Date("2026-11-08T12:00:00Z"));
const render = (store: RoutineStore, extra = {}) =>
  renderToStaticMarkup(
    createElement(RoutineExecutionCard, {
      definition: store.definition,
      execution: store.execution,
      onAction: async () => true,
      ...extra,
    }),
  );
describe("controlled routine card rendering", () => {
  it("shows the goal, original window and expected duration before starting", () => {
    const html = render(initial);
    for (const text of [
      initial.definition.goal,
      "18:00",
      "18:30",
      "30",
      "Europe/Berlin",
      "Fixed goal",
      "Start routine",
      "Ready to begin",
    ])
      expect(html).toContain(text);
    expect(html).not.toContain("Save progress");
  });
  it("renders progress controls only for a started execution", () => {
    const html = render(applyRoutineAction(initial, { type: "start" }));
    expect(html).toContain("Save progress");
    expect(html).toContain("Complete routine");
    expect(html).toContain('type="number"');
    expect(html).not.toContain("Start routine");
  });
  it("shows saved completion and no further mutation controls", () => {
    const html = render(
      applyRoutineAction(applyRoutineAction(initial, { type: "start" }), {
        type: "complete",
      }),
    );
    expect(html).toContain("Goal marked complete.");
    expect(html).toContain("100%");
    expect(html).not.toContain("Save progress");
    expect(html).not.toContain("Complete routine");
    expect(html).toContain(initial.definition.goal);
  });
  it("exposes pending and save failures accessibly", () => {
    const html = render(initial, {
      pending: true,
      error: "Could not save. Try again.",
    });
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain('disabled=""');
    expect(html).toContain('role="alert"');
    expect(html).toContain("Could not save. Try again.");
  });
  it("can render two independent cards without duplicate labeling IDs", () => {
    const html = renderToStaticMarkup(
      createElement(
        "div",
        {},
        createElement(RoutineExecutionCard, {
          definition: initial.definition,
          execution: initial.execution,
          onAction: async () => true,
        }),
        createElement(RoutineExecutionCard, {
          definition: {
            ...initial.definition,
            id: "weekly-reading",
            title: "Weekly reading",
          },
          execution: initial.execution,
          onAction: async () => true,
        }),
      ),
    );
    const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
    expect(new Set(ids).size).toBe(ids.length);
    expect(html).toContain("Weekly reading");
  });
});

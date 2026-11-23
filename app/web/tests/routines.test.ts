import { describe, expect, it } from "vitest";
import {
  applyRoutineAction,
  createRoutineStore,
  isRoutineStore,
  type RoutineAction,
  type RoutineStore,
} from "../src/lib/routines";
import {
  routineRepository,
  ROUTINE_STORAGE_KEY,
} from "../src/lib/routine-repository";
import { browserRepository, STORAGE_KEY } from "../src/lib/repository";
import { seed } from "../src/lib/data";

const now = new Date("2026-11-08T12:00:00Z"),
  start = "2026-11-08T18:00:00Z",
  middle = "2026-11-08T18:10:00Z",
  end = "2026-11-08T18:30:00Z";
const storage = () => {
  const values = new Map<string, string>();
  return {
    getItem: (k: string) => values.get(k) ?? null,
    setItem: (k: string, v: string) => {
      values.set(k, v);
    },
  };
};
describe("routine execution invariants", () => {
  it("starts once, records progress and explicit completion without changing the definition", () => {
    const initial = createRoutineStore(now);
    Object.freeze(initial.definition);
    const started = applyRoutineAction(initial, { type: "start" }, start),
      progressed = applyRoutineAction(
        started,
        { type: "progress", percent: 40 },
        middle,
      ),
      finished = applyRoutineAction(progressed, { type: "complete" }, end);
    for (const s of [started, progressed, finished]) {
      expect(s.definition).toBe(initial.definition);
      expect(s.definition.goal).toBe(initial.definition.goal);
      expect(isRoutineStore(s)).toBe(true);
    }
    expect(started.execution.startedAt).toBe(start);
    expect(progressed.execution.progressHistory).toEqual([
      { percent: 40, at: middle },
    ]);
    expect(finished.execution).toMatchObject({
      status: "completed",
      progress: 100,
      completedAt: end,
    });
    expect(initial.execution.status).toBe("not_started");
  });
  it("keeps the original start timestamp when Start is repeated", () => {
    const s = applyRoutineAction(
      createRoutineStore(now),
      { type: "start" },
      start,
    );
    expect(applyRoutineAction(s, { type: "start" }, end)).toBe(s);
  });
  it.each([
    { type: "progress", percent: 10 },
    { type: "complete" },
  ] as RoutineAction[])("requires Start before $type", (action) =>
    expect(() => applyRoutineAction(createRoutineStore(now), action)).toThrow(
      "Start the routine",
    ),
  );
  it.each([-1, 101, 0.5, NaN, Infinity])(
    "rejects invalid progress %s",
    (percent) => {
      const s = applyRoutineAction(
        createRoutineStore(now),
        { type: "start" },
        start,
      );
      expect(() =>
        applyRoutineAction(s, { type: "progress", percent }),
      ).toThrow("whole-number");
      expect(s.execution.progress).toBe(0);
    },
  );
  it("does not confuse 100% reported progress with explicit completion", () => {
    const s = applyRoutineAction(
      applyRoutineAction(createRoutineStore(now), { type: "start" }, start),
      { type: "progress", percent: 100 },
      middle,
    );
    expect(s.execution.status).toBe("in_progress");
    expect(s.execution.completedAt).toBeNull();
    expect(
      applyRoutineAction(s, { type: "complete" }, end).execution
        .progressHistory,
    ).toHaveLength(1);
  });
  it("retains a correction in self-reported history without changing the goal", () => {
    const s = applyRoutineAction(
      applyRoutineAction(createRoutineStore(now), { type: "start" }, start),
      { type: "progress", percent: 80 },
      middle,
    );
    const corrected = applyRoutineAction(
      s,
      { type: "progress", percent: 60 },
      end,
    );
    expect(corrected.execution.progressHistory.map((p) => p.percent)).toEqual([
      80, 60,
    ]);
    expect(corrected.definition).toBe(s.definition);
  });
  it("makes completed execution terminal", () => {
    const s = applyRoutineAction(
      applyRoutineAction(createRoutineStore(now), { type: "start" }, start),
      { type: "complete" },
      end,
    );
    expect(() => applyRoutineAction(s, { type: "complete" })).toThrow(
      "already completed",
    );
    expect(() =>
      applyRoutineAction(s, { type: "progress", percent: 25 }),
    ).toThrow("already completed");
  });
  it("never auto-progresses with elapsed time", () => {
    const s = applyRoutineAction(
      createRoutineStore(now),
      { type: "start" },
      start,
    );
    expect(s.execution.progress).toBe(0);
    expect(s.execution.completedAt).toBeNull();
  });
});
describe("isolated routine storage", () => {
  it("round-trips each execution stage and preserves legacy demo bytes", async () => {
    const db = storage();
    db.setItem(STORAGE_KEY, JSON.stringify(seed(now)));
    const before = db.getItem(STORAGE_KEY),
      repo = routineRepository(db, () => now);
    let s = await repo.load();
    for (const action of [
      { type: "start" },
      { type: "progress", percent: 35 },
      { type: "complete" },
    ] as RoutineAction[]) {
      s = applyRoutineAction(s, action);
      await repo.save(s);
      expect(await routineRepository(db).load()).toEqual(s);
      expect(db.getItem(STORAGE_KEY)).toBe(before);
    }
  });
  it("loads an older demo with no routine key without modifying it", async () => {
    const db = storage();
    const state = seed(now);
    await browserRepository(db).save(state);
    expect(
      (await routineRepository(db, () => now).load()).execution.status,
    ).toBe("not_started");
    expect(db.getItem(ROUTINE_STORAGE_KEY)).toBeNull();
    expect(await browserRepository(db).load()).toEqual(state);
  });
  it.each(["broken JSON", '{"version":2}', '{"version":1}'])(
    "preserves unreadable data: %s",
    async (raw) => {
      const db = storage();
      db.setItem(ROUTINE_STORAGE_KEY, raw);
      await expect(routineRepository(db).load()).rejects.toThrow(
        "could not be read",
      );
      expect(db.getItem(ROUTINE_STORAGE_KEY)).toBe(raw);
    },
  );
  it("preserves the previous execution on quota failure", async () => {
    const db = storage(),
      repo = routineRepository(db, () => now);
    const ready = await repo.load();
    await repo.save(ready);
    const broken = routineRepository({
      ...db,
      setItem: () => {
        throw new Error("Quota exceeded");
      },
    });
    await expect(
      broken.save(applyRoutineAction(ready, { type: "start" }, start)),
    ).rejects.toThrow("Quota");
    expect(await repo.load()).toEqual(ready);
  });
  it("rejects malformed states before writing", async () => {
    const db = storage(),
      repo = routineRepository(db);
    const s = createRoutineStore(now);
    await expect(
      repo.save({ ...s, execution: { ...s.execution, progress: 200 } }),
    ).rejects.toThrow("invalid");
    expect(db.getItem(ROUTINE_STORAGE_KEY)).toBeNull();
    expect(
      isRoutineStore({
        ...s,
        definition: { ...s.definition, timezone: "Invalid/Timezone" },
      }),
    ).toBe(false);
  });
  it("Reset demo restores the routine as well as the existing demo", async () => {
    const db = storage(),
      repo = routineRepository(db, () => now);
    await repo.save(
      applyRoutineAction(await repo.load(), { type: "start" }, start),
    );
    await browserRepository(db).reset();
    expect((await repo.load()).execution.status).toBe("not_started");
  });
  it("retains the occurrence date and zone across reloads after midnight", async () => {
    const db = storage(),
      repo = routineRepository(db, () => now, "Pacific/Auckland");
    const s = applyRoutineAction(await repo.load(), { type: "start" }, start);
    await repo.save(s);
    expect(
      (await routineRepository(db, () => new Date("2026-11-10"), "UTC").load())
        .definition,
    ).toEqual(s.definition);
  });
});

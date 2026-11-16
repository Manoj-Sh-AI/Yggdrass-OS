import {
  createRoutineStore,
  isRoutineStore,
  type RoutineStore,
} from "./routines";

export const ROUTINE_STORAGE_KEY = "yggdras.app.routines.v1";
export interface RoutineStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}
export interface RoutineRepository {
  load(): Promise<RoutineStore>;
  save(store: RoutineStore): Promise<void>;
}
export function routineRepository(
  storage: RoutineStorage,
  now = () => new Date(),
  timezone = "Europe/Berlin",
): RoutineRepository {
  return {
    async load() {
      const raw = storage.getItem(ROUTINE_STORAGE_KEY);
      if (raw === null) return createRoutineStore(now(), timezone);
      try {
        const value: unknown = JSON.parse(raw);
        if (isRoutineStore(value)) return value;
      } catch {
        /* Preserve the original record for explicit reset/recovery. */
      }
      throw new Error(
        "This saved routine could not be read. Retry, or use Reset demo in Settings to restore the fictional routine.",
      );
    },
    async save(store) {
      if (!isRoutineStore(store))
        throw new Error(
          "The routine execution could not be saved because its data is invalid.",
        );
      storage.setItem(ROUTINE_STORAGE_KEY, JSON.stringify(store));
    },
  };
}

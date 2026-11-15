import { applicationApi } from "./api";
import type { RoutineAction, RoutineStore } from "./routines";
export const routineHttp = {
  load: () => applicationApi<RoutineStore>("application/routine"),
  command: (action: RoutineAction) =>
    applicationApi<RoutineStore>("application/routine/actions", {
      method: "POST",
      body: JSON.stringify(action),
    }),
};

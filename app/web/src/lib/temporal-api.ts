import { applicationApi } from "./api";
import type { CommandResult } from "./planning";
import { workspaceRetry } from "./workspace-retry";
export async function temporalWrite(operation: string, data: Record<string, unknown>, id?: string, version?: number) {
  const retry = await workspaceRetry("time:" + JSON.stringify({ operation, data, id, version }));
  const result = await applicationApi<CommandResult>("application/time/commands", { method: "POST", body: JSON.stringify({ key: retry.key, operation, data, id, version }) });
  retry.complete();
  window.dispatchEvent(new Event("yggdress:tasks-changed"));
  window.dispatchEvent(new Event("yggdress:connections-changed"));
  return result;
}

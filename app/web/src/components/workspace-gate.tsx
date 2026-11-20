import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { AppProvider } from "./provider";
import { SceneryProvider } from "./scenery";
import { AppShell } from "./shell";
import { PlanningProvider } from "./planning-provider";
import { PlanningTaskSheet } from "./planning-ui";
export async function WorkspaceGate({ children }: { children: ReactNode }) {
  const jar = await cookies();
  let authenticated = false;
  let mobile = false;
  try {
    const result = await fetch(
      `${process.env.YGGDRESS_API_URL || "http://127.0.0.1:8100"}/v1/auth/session`,
      {
        headers: { Cookie: jar.toString() },
        cache: "no-store",
        signal: AbortSignal.timeout(6000),
      },
    );
    authenticated = result.ok;
    if (authenticated)
      mobile = String((await result.json()).csrf || "").startsWith(
        "mobile:v1:",
      );
  } catch {
    /* Private workspace stays closed. */
  }
  if (!authenticated) redirect("/login");
  return (
    <AppProvider>
      <SceneryProvider>
        <PlanningProvider>
          {mobile ? (
            <main className="native-workspace" id="main">
              {children}
              <PlanningTaskSheet />
            </main>
          ) : (
            <AppShell>{children}</AppShell>
          )}
        </PlanningProvider>
      </SceneryProvider>
    </AppProvider>
  );
}

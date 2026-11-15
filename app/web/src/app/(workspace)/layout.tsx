import type { ReactNode } from "react";
import { WorkspaceGate } from "@/components/workspace-gate";
export const dynamic = "force-dynamic";
export default function Layout({ children }: { children: ReactNode }) {
  return <WorkspaceGate>{children}</WorkspaceGate>;
}

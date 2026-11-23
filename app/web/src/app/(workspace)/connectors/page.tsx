import type { Metadata } from "next";
import { ConnectorCatalog } from "@/components/catalogs";
export const metadata: Metadata = { title: "Connectors" };
export default function Page() {
  return <ConnectorCatalog />;
}

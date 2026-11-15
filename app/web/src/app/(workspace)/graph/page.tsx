import type { Metadata } from "next";
import { BrainGraphPage } from "@/components/brain-graph";
export const metadata: Metadata = { title: "Graph visualization" };
export default function Graph() {
  return <BrainGraphPage />;
}

import type { Metadata } from "next";
import { SkillCatalog } from "@/components/catalogs";
export const metadata: Metadata = { title: "Skills" };
export default function Page() {
  return <SkillCatalog />;
}

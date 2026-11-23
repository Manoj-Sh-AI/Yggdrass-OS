import { redirect } from "next/navigation";
import { notFound } from "next/navigation";
import { areas } from "@/lib/data";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!areas.some((area) => area.id === id)) notFound();
  redirect("/notes");
}

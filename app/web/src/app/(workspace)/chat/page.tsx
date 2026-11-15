import type { Metadata } from "next";
import { ChatPage } from "@/components/chat";
export const metadata: Metadata = { title: "Chat" };
export default function Chat() {
  return <ChatPage />;
}

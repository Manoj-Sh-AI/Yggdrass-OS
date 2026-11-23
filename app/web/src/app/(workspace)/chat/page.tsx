import type { Metadata } from "next";
import { ChatPage } from "@/features/chat/chat-page";
export const metadata: Metadata = { title: "Chat" };
export default function Chat() {
  return <ChatPage />;
}

import type { Metadata } from "next";
import { ChatPage } from "@/components/chat";
import { YggdrasPanel } from "@/components/yggdras-panel";
export const metadata: Metadata = { title: "Chat" };
export default function Chat() {
  return (
    <>
      <YggdrasPanel />
      <ChatPage />
    </>
  );
}

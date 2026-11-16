import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import "./notes.css";
import "./planning.css";
import "./graph.css";
import "./nature-glass.css";
import "./interface-feel.css";
import "./kanban.css";
import "./open-air.css";
import "./signal-workspace.css";
import "./calendar-workspace.css";
import "./linked-work.css";
import "./chat.css";
import "./yggdras.css";
export const metadata: Metadata = {
  title: {
    default: "Yggdras · A little clarity, every day",
    template: "%s · Yggdras",
  },
  description:
    "A calm home for your thoughts, your time, and the things that matter.",
};
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

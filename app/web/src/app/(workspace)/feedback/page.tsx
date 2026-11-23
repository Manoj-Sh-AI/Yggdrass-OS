import type { Metadata } from "next";
import { FeedbackLog } from "@/components/feedback-log";
export const metadata: Metadata = { title: "How Yggdras works" };
export default function Feedback() {
  return <FeedbackLog />;
}

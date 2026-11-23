import { notFound } from "next/navigation";
import { ComponentGallery } from "@/features/chat/gallery";

/** Every chat component with invented data, for screenshots. Not served in production. */
export default function ChatComponents() {
  if (process.env.NODE_ENV === "production" && process.env.YGGDRAS_GALLERY !== "1") notFound();
  return <ComponentGallery />;
}

import type { PartialBlock } from "@blocknote/core";

export const DOCUMENT_MARKER = "<!-- yggdress:blocknote:v1 -->\n";
export type NoteDocument = {
  format: "yggdress.blocknote";
  version: 1;
  blocks: PartialBlock[];
  markdown: string;
  icon: string;
};
export function documentFrom(
  blocks: PartialBlock[],
  markdown: string,
  icon = "",
): NoteDocument {
  return { format: "yggdress.blocknote", version: 1, blocks, markdown, icon };
}
export function encodeDocument(document: NoteDocument): string {
  return DOCUMENT_MARKER + JSON.stringify(document);
}
export function decodeDocument(content: string): NoteDocument | null {
  if (!content.startsWith("<!-- yggdress:blocknote:")) return null;
  if (!content.startsWith(DOCUMENT_MARKER))
    throw new Error(
      "This document uses an unsupported editor format. Export the original; its content has not been changed.",
    );
  const value = JSON.parse(content.slice(DOCUMENT_MARKER.length));
  if (
    value?.format !== "yggdress.blocknote" ||
    value.version !== 1 ||
    !Array.isArray(value.blocks) ||
    typeof value.markdown !== "string" ||
    typeof value.icon !== "string"
  )
    throw new Error(
      "The saved rich document is unreadable. Its original content has been preserved.",
    );
  return value;
}
/** Conservative report. Saving always retains native JSON, including unknown attributes. */
export function markdownWarnings(blocks: PartialBlock[]): string[] {
  const warnings = new Set<string>();
  const visit = (value: unknown) => {
    if (!value || typeof value !== "object") return;
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    const v = value as Record<string, unknown>;
    if (
      typeof v.type === "string" &&
      ![
        "paragraph",
        "heading",
        "bulletListItem",
        "numberedListItem",
        "checkListItem",
        "quote",
        "codeBlock",
        "divider",
        "table",
        "text",
        "link",
        "tableContent",
        "tableCell",
      ].includes(v.type)
    )
      warnings.add("Some block types have no faithful Markdown equivalent.");
    if (v.type === "table")
      warnings.add(
        "Markdown tables cannot preserve all cell layout and formatting.",
      );
    if (v.styles && typeof v.styles === "object")
      for (const style of Object.keys(v.styles))
        if (!["bold", "italic", "strike", "code"].includes(style))
          warnings.add(
            "Underline, colors and other rich styles are preserved in JSON, not standard Markdown.",
          );
    const p = v.props as Record<string, unknown> | undefined;
    if (
      p &&
      ((p.textAlignment && p.textAlignment !== "left") ||
        (p.textColor && p.textColor !== "default") ||
        (p.backgroundColor && p.backgroundColor !== "default"))
    )
      warnings.add(
        "Block alignment and colors are preserved in JSON, not standard Markdown.",
      );
    Object.values(v).forEach(visit);
  };
  visit(blocks);
  return [...warnings];
}

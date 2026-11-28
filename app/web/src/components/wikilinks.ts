/** [[slug]] links in a note, shown as tappable note titles. A ProseMirror decoration only
 * changes how the text looks: the stored note keeps its [[slug]] exactly (D31 format).
 * While editing, the raw text shows (CSS: .wikilink-chip hides on an editable view). */
import { createExtension } from "@blocknote/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { Node } from "@tiptap/pm/model";

export const OPEN_NOTE_EVENT = "yggdras:open-note";
const LINK = /\[\[([A-Za-z0-9_-]{1,200})(?:\|([^\]\n]{1,200}))?\]\]/g;

export type Wikilink = {
  from: number;
  to: number;
  slug: string;
  label?: string;
};

/** Every [[slug]] or [[slug|label]] in a text, with offsets. */
export function findWikilinks(text: string): Wikilink[] {
  return [...text.matchAll(LINK)].map((m) => ({
    from: m.index ?? 0,
    to: (m.index ?? 0) + m[0].length,
    slug: m[1],
    label: m[2],
  }));
}

function decorate(doc: Node, titleOf: (slug: string) => string | undefined) {
  const decorations: Decoration[] = [];
  doc.descendants((node, pos) => {
    if (!node.isText || !node.text) return;
    for (const link of findWikilinks(node.text)) {
      const from = pos + link.from,
        to = pos + link.to;
      decorations.push(Decoration.inline(from, to, { class: "wikilink-raw" }));
      decorations.push(
        Decoration.widget(
          from,
          () => {
            const chip = document.createElement("button");
            chip.type = "button";
            chip.className = "wikilink-chip";
            chip.dataset.slug = link.slug;
            chip.textContent = link.label || titleOf(link.slug) || link.slug;
            chip.setAttribute("aria-label", `Open note ${chip.textContent}`);
            chip.addEventListener("click", (event) => {
              event.preventDefault();
              event.stopPropagation();
              window.dispatchEvent(
                new CustomEvent(OPEN_NOTE_EVENT, {
                  detail: { slug: link.slug },
                }),
              );
            });
            return chip;
          },
          {
            side: -1,
            key: `wikilink-${link.slug}-${from}`,
            ignoreSelection: true,
          },
        ),
      );
    }
  });
  return DecorationSet.create(doc, decorations);
}

/** The BlockNote extension. `titleOf` is read at render time, so titles stay current. */
export function wikilinkExtension(
  titleOf: (slug: string) => string | undefined,
) {
  const key = new PluginKey("yggdras-wikilinks");
  return createExtension({
    key: "yggdras-wikilinks",
    prosemirrorPlugins: [
      new Plugin({
        key,
        state: {
          init: (_, state) => decorate(state.doc, titleOf),
          apply: (tr, old) => (tr.docChanged ? decorate(tr.doc, titleOf) : old),
        },
        props: {
          decorations(state) {
            return key.getState(state);
          },
        },
      }),
    ],
  });
}

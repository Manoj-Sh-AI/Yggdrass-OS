/** A small, dependency-free Markdown view for agent replies: headings, bullet and
 * numbered lists, paragraphs, **bold**, *italic* and `code`; a link shows its text.
 * Nothing is executed or fetched, and there is no HTML: unknown syntax stays plain. */
import { Text, View } from "react-native";
import { colors, styles } from "./ui";

export type Inline = {
  text: string;
  bold?: boolean;
  italic?: boolean;
  code?: boolean;
};
export type Block =
  | { kind: "heading"; level: number; inline: Inline[] }
  | { kind: "bullet"; marker: string; inline: Inline[] }
  | { kind: "paragraph"; inline: Inline[] };

/** **bold**, *italic* / _italic_, `code`, [text](url) -> text. */
export function inline(source: string): Inline[] {
  const out: Inline[] = [];
  const pattern =
    /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\)|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;
  let last = 0;
  for (const match of source.matchAll(pattern)) {
    const at = match.index ?? 0;
    if (at > last) out.push({ text: source.slice(last, at) });
    const token = match[0];
    if (token.startsWith("**"))
      out.push({ text: token.slice(2, -2), bold: true });
    else if (token.startsWith("`"))
      out.push({ text: token.slice(1, -1), code: true });
    else if (token.startsWith("["))
      out.push({ text: token.slice(1, token.indexOf("]")) });
    else out.push({ text: token.slice(1, -1), italic: true });
    last = at + token.length;
  }
  if (last < source.length) out.push({ text: source.slice(last) });
  return out;
}

export function blocks(source: string): Block[] {
  const out: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length)
      out.push({ kind: "paragraph", inline: inline(paragraph.join(" ")) });
    paragraph = [];
  };
  for (const raw of source.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const numbered = /^\s*(\d+)[.)]\s+(.*)$/.exec(line);
    if (!line.trim()) flush();
    else if (heading) {
      flush();
      out.push({
        kind: "heading",
        level: heading[1].length,
        inline: inline(heading[2]),
      });
    } else if (bullet) {
      flush();
      out.push({ kind: "bullet", marker: "•", inline: inline(bullet[1]) });
    } else if (numbered) {
      flush();
      out.push({
        kind: "bullet",
        marker: `${numbered[1]}.`,
        inline: inline(numbered[2]),
      });
    } else paragraph.push(line.trim());
  }
  flush();
  return out;
}

function Spans({ parts, color }: { parts: Inline[]; color: string }) {
  return (
    <>
      {parts.map((p, i) => (
        <Text
          key={i}
          style={{
            fontWeight: p.bold ? "600" : undefined,
            fontStyle: p.italic ? "italic" : undefined,
            fontFamily: p.code ? "monospace" : undefined,
            backgroundColor: p.code ? colors.control : undefined,
            color,
          }}
        >
          {p.text}
        </Text>
      ))}
    </>
  );
}

export function Markdown({
  source,
  color = colors.text,
}: {
  source: string;
  color?: string;
}) {
  return (
    <View style={{ gap: 6 }}>
      {blocks(source).map((b, i) =>
        b.kind === "heading" ? (
          <Text
            key={i}
            selectable
            style={[styles.text, { fontWeight: "600", color }]}
          >
            <Spans parts={b.inline} color={color} />
          </Text>
        ) : b.kind === "bullet" ? (
          <View key={i} style={{ flexDirection: "row", gap: 8 }}>
            <Text style={[styles.text, { color }]}>{b.marker}</Text>
            <Text selectable style={[styles.text, { flex: 1, color }]}>
              <Spans parts={b.inline} color={color} />
            </Text>
          </View>
        ) : (
          <Text key={i} selectable style={[styles.text, { color }]}>
            <Spans parts={b.inline} color={color} />
          </Text>
        ),
      )}
    </View>
  );
}

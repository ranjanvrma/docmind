/**
 * A deliberately small Markdown subset for LLM answers.
 *
 * Answers are untrusted (they are influenced by uploaded documents), so the
 * output of this parser is plain data that React renders as escaped text:
 * no HTML, no links and no images can ever be produced. Supported: headings
 * (#, ##, ###), paragraphs, bullet and numbered lists, fenced code blocks,
 * **bold**, *italic*, `inline code` and citation markers.
 *
 * Citation markers follow the backend rule in app/qa.py: [1], [2, 3] and
 * [Source 4] with 1–2 digit numbers. Bracketed years such as [2024] stay text.
 */

export type Inline =
  | { type: "text"; value: string }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] }
  | { type: "code"; value: string }
  | { type: "citation"; numbers: number[] };

export type Block =
  | { type: "heading"; level: 1 | 2 | 3; inline: Inline[] }
  | { type: "paragraph"; inline: Inline[] }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "code"; value: string };

const CITATION = String.raw`\[(?:source\s*)?(\d{1,2}(?:\s*,\s*(?:source\s*)?\d{1,2})*)\]`;
const INLINE = new RegExp(
  [
    `(?<citation>${CITATION})`,
    "(?<code>`[^`\\n]+`)",
    String.raw`(?<strong>\*\*(?=\S)[^*\n]+?\*\*)`,
    String.raw`(?<em>(?<![\w*])\*(?=\S)[^*\n]+?\*(?![\w*]))`,
  ].join("|"),
  "gi",
);

export function citationNumbers(marker: string): number[] {
  return (marker.match(/\d+/g) ?? []).map(Number);
}

/** All citation numbers in a text, in order (duplicates kept). */
export function extractCitations(text: string): number[] {
  const re = new RegExp(CITATION, "gi");
  return [...text.matchAll(re)].flatMap((m) => citationNumbers(m[1]));
}

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0;
    if (index > last) out.push({ type: "text", value: text.slice(last, index) });
    const g = match.groups ?? {};
    if (g.citation) out.push({ type: "citation", numbers: citationNumbers(g.citation) });
    else if (g.code) out.push({ type: "code", value: g.code.slice(1, -1) });
    else if (g.strong) out.push({ type: "strong", children: parseInline(g.strong.slice(2, -2)) });
    else if (g.em) out.push({ type: "em", children: parseInline(g.em.slice(1, -1)) });
    last = index + match[0].length;
  }
  if (last < text.length) out.push({ type: "text", value: text.slice(last) });
  return out;
}

const HEADING = /^(#{1,3})\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d{1,3}[.)]\s+(.*)$/;
const FENCE = /^\s*```/;

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ type: "paragraph", inline: parseInline(paragraph.join(" ")) });
    paragraph = [];
  };
  const flushList = () => {
    if (list) blocks.push({ type: "list", ordered: list.ordered, items: list.items.map(parseInline) });
    list = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (FENCE.test(line)) {
      flushParagraph();
      flushList();
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !FENCE.test(lines[i])) code.push(lines[i++]);
      blocks.push({ type: "code", value: code.join("\n") });
      continue;
    }

    const heading = HEADING.exec(line);
    const bullet = BULLET.exec(line);
    const numbered = NUMBERED.exec(line);

    if (!line.trim()) {
      flushParagraph();
      flushList();
    } else if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: "heading", level: heading[1].length as 1 | 2 | 3, inline: parseInline(heading[2].trim()) });
    } else if (bullet || numbered) {
      flushParagraph();
      const ordered = Boolean(numbered && !bullet);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? numbered)![1].trim());
    } else if (list && /^\s{2,}\S/.test(line)) {
      // indented continuation of the previous list item
      list.items[list.items.length - 1] += ` ${line.trim()}`;
    } else {
      flushList();
      paragraph.push(line.trim());
    }
  }
  flushParagraph();
  flushList();
  return blocks;
}

import { describe, expect, it } from "vitest";

import { isAbstention } from "./citations";
import { extractCitations, parseInline, parseMarkdown } from "./markdown";

describe("citations", () => {
  it("parses the same marker formats as the backend", () => {
    expect(extractCitations("A [1]. B [2][3]. C [Source 4]. D [5, 6].")).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("does not treat bracketed years or values as citations", () => {
    expect(extractCitations("In [2024] revenue rose [1]; table value [1480].")).toEqual([1]);
    expect(extractCitations("Figures for [1999, 2000] are missing.")).toEqual([]);
  });

  it("keeps out-of-range two-digit markers so they can be flagged", () => {
    expect(extractCitations("See [12].")).toEqual([12]);
  });
});

describe("inline parsing", () => {
  it("produces citation tokens between text", () => {
    expect(parseInline("Refunds take 30 days [1].")).toEqual([
      { type: "text", value: "Refunds take 30 days " },
      { type: "citation", numbers: [1] },
      { type: "text", value: "." },
    ]);
  });

  it("supports bold, italic and inline code", () => {
    const tokens = parseInline("**Key** point with *emphasis* and `code` [2]");
    expect(tokens.map((t) => t.type)).toEqual(["strong", "text", "em", "text", "code", "text", "citation"]);
  });

  it("leaves links, images and HTML as literal text", () => {
    const text = '![x](https://attacker.example/?q=1) [click](javascript:alert(1)) <img src=x onerror=alert(1)>';
    const tokens = parseInline(text);
    expect(tokens.every((t) => t.type === "text")).toBe(true);
    expect(tokens.map((t) => (t.type === "text" ? t.value : "")).join("")).toBe(text);
  });

  it("does not treat list-like or arithmetic asterisks as emphasis", () => {
    expect(parseInline("2 * 3 * 4").every((t) => t.type === "text")).toBe(true);
  });
});

describe("block parsing", () => {
  it("parses headings, lists, paragraphs and code blocks", () => {
    const blocks = parseMarkdown("## Summary\n\n- first [1]\n- second\n\n1. one\n2. two\n\nPlain text\ncontinues.\n\n```\nx = 1\n```");
    expect(blocks.map((b) => b.type)).toEqual(["heading", "list", "list", "paragraph", "code"]);
    expect(blocks[1]).toMatchObject({ type: "list", ordered: false });
    expect(blocks[2]).toMatchObject({ type: "list", ordered: true });
    expect(blocks[4]).toEqual({ type: "code", value: "x = 1" });
  });

  it("joins soft-wrapped lines into one paragraph", () => {
    expect(parseMarkdown("line one\nline two")).toEqual([{ type: "paragraph", inline: [{ type: "text", value: "line one line two" }] }]);
  });

  it("handles empty input", () => {
    expect(parseMarkdown("")).toEqual([]);
  });
});

describe("abstention", () => {
  it("matches the backend rule: only at the start of the answer", () => {
    expect(isAbstention("I could not find the answer in the uploaded documents.")).toBe(true);
    expect(isAbstention('"I could not find the answer in the uploaded documents." The sources mention X.')).toBe(true);
    expect(isAbstention("X is 5 [1]. I could not find the answer in the uploaded documents for Y.")).toBe(false);
  });
});

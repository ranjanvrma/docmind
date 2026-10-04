import { Fragment, useMemo, type ReactNode } from "react";

import { CitationChip } from "@/components/citations/CitationChip";
import { parseMarkdown, type Inline } from "@/lib/markdown";
import type { Source } from "@/lib/types";

/**
 * Renders an LLM answer. The text goes through lib/markdown.ts, which only
 * produces plain data; React escapes everything, so no HTML, links or images
 * from the model (or from an injected document) can ever be rendered.
 */
export function AnswerContent({ answer, sources, onReveal }: { answer: string; sources: Source[]; onReveal?: (n: number) => void }) {
  const blocks = useMemo(() => parseMarkdown(answer), [answer]);
  const byNumber = useMemo(() => new Map(sources.map((s) => [s.source_number, s])), [sources]);

  const inline = (nodes: Inline[]): ReactNode =>
    nodes.map((node, i) => {
      switch (node.type) {
        case "text":
          return <Fragment key={i}>{node.value}</Fragment>;
        case "strong":
          return (
            <strong key={i} className="font-semibold text-fg">
              {inline(node.children)}
            </strong>
          );
        case "em":
          return <em key={i}>{inline(node.children)}</em>;
        case "code":
          return (
            <code key={i} className="rounded-md border border-line bg-surface-2 px-1.5 py-0.5 font-mono text-[0.86em]">
              {node.value}
            </code>
          );
        case "citation":
          return (
            <span key={i} className="whitespace-nowrap">
              {node.numbers.map((n, j) => (
                <CitationChip key={j} number={n} source={byNumber.get(n)} onReveal={onReveal} />
              ))}
            </span>
          );
      }
    });

  return (
    <div className="space-y-3 text-[15px] leading-relaxed text-fg/90">
      {blocks.map((block, i) => {
        switch (block.type) {
          case "heading": {
            const size = block.level === 1 ? "text-lg" : block.level === 2 ? "text-base" : "text-[15px]";
            return (
              <p key={i} role="heading" aria-level={block.level + 2} className={`${size} pt-1 font-semibold text-fg`}>
                {inline(block.inline)}
              </p>
            );
          }
          case "paragraph":
            return <p key={i}>{inline(block.inline)}</p>;
          case "list": {
            const List = block.ordered ? "ol" : "ul";
            return (
              <List key={i} className={`space-y-1.5 pl-5 ${block.ordered ? "list-decimal" : "list-disc"} marker:text-fg-faint`}>
                {block.items.map((item, j) => (
                  <li key={j}>{inline(item)}</li>
                ))}
              </List>
            );
          }
          case "code":
            return (
              <pre key={i} className="overflow-x-auto rounded-xl border border-line bg-bg-2 p-4 font-mono text-[13px] leading-relaxed">
                <code>{block.value}</code>
              </pre>
            );
        }
      })}
    </div>
  );
}

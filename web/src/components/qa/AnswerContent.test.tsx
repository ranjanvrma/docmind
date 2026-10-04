import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";

import { TooltipProvider } from "@/components/ui/overlays";
import type { Source } from "@/lib/types";
import { AnswerContent } from "./AnswerContent";

const source: Source = {
  rank: 1,
  score: 0.48,
  chunk_id: "abc:p3:c0",
  doc_id: "abc",
  doc_name: "policy.pdf",
  page_number: 3,
  text: "Lost or stolen devices must be reported within 24 hours.",
  source_number: 1,
  cited: true,
};

function renderAnswer(answer: string, sources: Source[] = [source]) {
  return render(
    <MemoryRouter>
      <TooltipProvider>
        <AnswerContent answer={answer} sources={sources} />
      </TooltipProvider>
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("AnswerContent", () => {
  it("renders citations as interactive source chips", () => {
    renderAnswer("Report it within 24 hours [1].");
    const chip = screen.getByRole("button", { name: "Source 1: policy.pdf, page 3" });
    expect(chip.textContent).toBe("1");
  });

  it("marks citations to sources that were never provided as invalid, without a link", () => {
    const { container } = renderAnswer("Something [7].");
    expect(screen.queryByRole("button", { name: /Source 7/ })).toBeNull();
    expect(container.textContent).toContain("7?");
  });

  it("never renders HTML, links or images from untrusted answer text", () => {
    const hostile = '<img src=x onerror="alert(1)"> ![pixel](https://attacker.example/x.png) [click](javascript:alert(1)) <script>alert(1)</script>';
    const { container } = renderAnswer(hostile);
    expect(container.querySelector("img, script, a, iframe")).toBeNull();
    expect(container.textContent).toContain("<img src=x");
  });

  it("renders lists and headings from the safe Markdown subset", () => {
    const { container } = renderAnswer("## Steps\n\n- Report the loss [1]\n- Contact IT");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Steps" })).toBeTruthy();
  });
});

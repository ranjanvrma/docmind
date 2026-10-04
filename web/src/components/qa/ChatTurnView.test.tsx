import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DocumentStatusBadge } from "@/components/documents/DocumentStatus";
import { isPendingStatus } from "@/lib/queries";
import type { AskResponse, Source } from "@/lib/types";
import { AnswerStatus, UnverifiedOutput } from "./ChatTurnView";

const source = (n: number, cited: boolean): Source => ({
  rank: n,
  score: 0.5,
  chunk_id: `d:p${n}:c0`,
  doc_id: "d",
  doc_name: "doc.pdf",
  page_number: n,
  text: "text",
  source_number: n,
  cited,
});

const response = (over: Partial<AskResponse>): AskResponse => ({
  question: "q",
  answer: "a",
  answered_from_documents: false,
  grounding: "grounded",
  sources: [],
  invalid_citations: [],
  unverified_answer: null,
  model: "m",
  ...over,
});

afterEach(cleanup);

describe("AnswerStatus (server-decided grounding)", () => {
  it("shows how many sources a grounded answer cites", () => {
    render(<AnswerStatus response={response({ grounding: "grounded", sources: [source(1, true), source(2, false), source(3, true)] })} />);
    expect(screen.getByText(/Grounded · 2 sources cited/)).toBeTruthy();
  });

  it("labels abstentions", () => {
    render(<AnswerStatus response={response({ grounding: "not_found" })} />);
    expect(screen.getByText(/Not found in your documents/)).toBeTruthy();
  });

  it("never labels an ungrounded reply as grounded", () => {
    render(<AnswerStatus response={response({ grounding: "ungrounded", answered_from_documents: false })} />);
    expect(screen.getByText(/Could not be verified/)).toBeTruthy();
    expect(screen.queryByText(/Grounded/)).toBeNull();
  });
});

describe("UnverifiedOutput", () => {
  it("is collapsed by default and renders hostile model output as plain text", () => {
    const hostile = '<img src=x onerror="alert(1)"> [click](javascript:alert(1)) <script>alert(1)</script>';
    const { container } = render(<UnverifiedOutput text={hostile} />);
    expect(screen.queryByText(hostile)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /unverified reply/i }));
    expect(screen.getByText(hostile)).toBeTruthy();
    expect(container.querySelector("img, script, a")).toBeNull();
  });
});

describe("processing status", () => {
  it("treats queued and processing as pending", () => {
    expect(isPendingStatus("queued")).toBe(true);
    expect(isPendingStatus("processing")).toBe(true);
    expect(isPendingStatus("processed")).toBe(false);
    expect(isPendingStatus("uploaded")).toBe(false);
  });

  it("shows a live badge while the server processes a document", () => {
    render(<DocumentStatusBadge status="processing" />);
    expect(screen.getByText(/Processing/)).toBeTruthy();
  });
});

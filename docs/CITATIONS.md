# Citations

Citations are how a DocMind answer can be checked: every claim should point at a numbered source, and every source is a real passage with a document name and page.

## Source numbering

`prompts.build_context` labels each passage that fits in the context budget `[Source 1]`, `[Source 2]`, … in rank order, with `(document: name, page: n)`. The list of **included** passages is kept. That list, and only that list, becomes the answer's `sources`.

## Document and page metadata

Each chunk carries `doc_id`, `doc_name`, `page_number`, `chunk_index` and `chunk_id` (`<doc_id>:p<page>:c<index>`). Chunks never cross pages, so a source maps to exactly one page. The UI links each source to `/documents/<doc_id>?page=<n>#page-<n>`, which opens the document's indexed content scrolled to and highlighting that page.

## Citation extraction

`qa.extract_citations` (and its twin `web/src/lib/markdown.ts`) recognises `[1]`, `[2, 3]` and `[Source 4]`. Numbers are limited to **one or two digits**, because a prompt never holds more than 20 sources. So bracketed years and values such as `[2024]` or `[1480]` are ordinary text, not citations.

## Citation validation

For each answer, `qa.answer_question` computes:

| Field | Meaning |
|---|---|
| `cited` (per source) | the answer contains `[n]` for this source |
| `invalid_citations` | numbers the answer cited that were **never provided** (e.g. `[9]` when there were 5 sources) |
| `grounding` | `grounded` (cites at least one provided source), `not_found` (starts with the exact sentence "I could not find the answer in the uploaded documents."), or `ungrounded` (neither) |
| `answered_from_documents` | `grounding == "grounded"` |
| `unverified_answer` | the model's raw reply, only when it stayed `ungrounded` after the retry (otherwise `null`) |

Citations that point only at non-existent source numbers count as `ungrounded`. Invalid citations are never shown as sources. The UI renders them as a dashed red "9?" marker with a warning explaining that the citation is not real.

## Ungrounded replies: one retry, then unverified

`qa.assess_answer` classifies every reply on the server. If the first reply is `ungrounded`, `answer_question` asks the model exactly once more, with a reminder of the rules (`RETRY_REMINDER`) appended to the user prompt. Abstentions (`not_found`) are not retried. If the second reply is still `ungrounded`, it is not presented as an answer: `answer` is set to the fixed text `UNVERIFIED_ANSWER` ("I could not produce an answer that is supported by citations to your documents. Try rephrasing the question, or check the retrieved sources below.") and the model's reply is returned separately in `unverified_answer`. The UI shows that reply only inside a collapsed "Show unverified reply" disclosure, as plain text.

## Why only context actually sent to the LLM can be cited

If DocMind showed passages the model never saw, a reader would assume the answer was based on them. Building `sources` from the prompt's included list makes "the model was given these passages" literally true, and validating numbers against that list stops a hallucinated source number from looking legitimate.

## In the UI

- **Inline chips.** Each `[n]` becomes a chip. Hover or focus shows a card with the document, page and passage; click pins it (works on touch). "Open in document" jumps to the page.
- **Sources used.** Below each answer, every passage sent to the model is listed, cited first ("2 cited of 5 retrieved"), expandable to the full passage with its similarity score.
- **Badges.** Taken from the server's `grounding`: "Grounded · N sources cited", "Not found in your documents", or "Could not be verified".

## Limits

DocMind verifies citation **numbers**, not **support**. A real source can be cited for a sentence it does not support. This was observed while testing with a scripted model: a claim about page 1 was attributed to the source for page 2. Claim-level verification (for example an entailment model checking each sentence against its cited passage) is not implemented.

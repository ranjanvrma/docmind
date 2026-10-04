/** Mirrors app/prompts.py:NOT_FOUND_ANSWER and app/qa.py:is_abstention. */
export const NOT_FOUND_ANSWER = "I could not find the answer in the uploaded documents.";

/** True if the answer starts with the not-found sentence (the prompt asks the model to begin with it). */
export function isAbstention(answer: string): boolean {
  return answer
    .trim()
    .replace(/^["'*]+/, "")
    .toLowerCase()
    .startsWith(NOT_FOUND_ANSWER.toLowerCase().replace(/\.$/, ""));
}

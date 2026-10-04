// Mirrors the Pydantic response models in app/models.py.

export interface Limits {
  max_upload_mb: number;
  max_request_mb: number;
  max_pages: number;
  max_files_per_upload: number;
  default_top_k: number;
  max_top_k: number;
}

export interface Health {
  status: "ok";
  version: string;
  embedding_model: string;
  llm_provider: string;
  llm_model: string;
  llm_configured: boolean;
  auth_required: boolean;
  documents: number;
  indexed_chunks: number;
  limits: Limits;
}

export interface Classification {
  label: string;
  method: "supervised" | "zero-shot" | string;
  scores: Record<string, number>;
}

/** queued/processing appear while the server processes a document in the background. */
export type DocumentStatus = "uploaded" | "queued" | "processing" | "processed" | "failed";

export interface DocumentInfo {
  doc_id: string;
  filename: string;
  size_bytes: number;
  uploaded_at: string;
  status: DocumentStatus;
  page_count: number;
  empty_pages: number[];
  chunk_count: number;
  warnings: string[];
  error: string | null;
  classification: Classification | null;
  processed_at: string | null;
}

export interface DocumentChunk {
  chunk_id: string;
  page_number: number;
  chunk_index: number;
  text: string;
}

export interface UploadItem {
  filename: string;
  status: "uploaded" | "duplicate" | "rejected";
  doc_id: string | null;
  detail: string | null;
}

export interface ProcessItem {
  doc_id: string;
  filename: string;
  status: DocumentStatus;
  chunk_count: number;
  skipped: boolean;
  detail: string | null;
}

export interface ProcessResponse {
  items: ProcessItem[];
  indexed_chunks: number;
}

export interface SearchHit {
  rank: number;
  score: number;
  chunk_id: string;
  doc_id: string;
  doc_name: string;
  page_number: number;
  text: string;
}

export interface SearchResponse {
  query: string;
  top_k: number;
  results: SearchHit[];
}

export interface Source extends SearchHit {
  source_number: number;
  cited: boolean;
}

export interface AskResponse {
  question: string;
  answer: string;
  answered_from_documents: boolean;
  /** grounded: cites provided sources · not_found: abstained · ungrounded: no valid citation even after a retry */
  grounding: "grounded" | "not_found" | "ungrounded";
  sources: Source[];
  invalid_citations: number[];
  /** Raw model reply when it could not be grounded; never shown as an answer. */
  unverified_answer: string | null;
  model: string | null;
}

export interface EditableSettings {
  llm_provider: "anthropic" | "openai";
  llm_model: string;
  llm_base_url: string;
  llm_effort: string;
  llm_max_tokens: number;
  llm_temperature: number;
  llm_timeout_seconds: number;
  max_context_chars: number;
  top_k: number;
  min_relevance: number;
  chunk_size: number;
  chunk_overlap: number;
  min_chars_per_page: number;
  max_upload_mb: number;
  max_request_mb: number;
  max_pages: number;
  classifier_labels: string[];
}

export interface SettingsView {
  values: EditableSettings;
  overridden: (keyof EditableSettings)[];
  llm_api_key: { configured: boolean; source: "settings" | "environment" | null; withheld: boolean };
  read_only: { embedding_model: string; auth_required: boolean; cors_origins: number };
}

export interface LlmTestResult {
  ok: boolean;
  message: string;
  latency_ms: number | null;
  model: string;
}

export interface EvaluationReport {
  run_at: string;
  dataset: string;
  dataset_description: string;
  n_queries: number;
  n_documents: number;
  indexed_chunks: number;
  settings: { embedding_model: string; chunk_size: number; chunk_overlap: number };
  metrics: { k: number; hit_rate: number; precision: number; recall: number }[];
  mrr: number;
  misses: { id: string; query: string; top1: string }[];
}

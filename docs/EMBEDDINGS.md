# Embeddings

An **embedding** is a fixed-length vector of numbers that a neural network assigns to a piece of text. The model is trained so that texts with similar meaning get vectors that point in similar directions. That is what lets "How do I get my money back?" match "Customers may request a refund within 30 days" even though they share almost no words.

## The model DocMind uses

| | |
|---|---|
| Model | `sentence-transformers/all-MiniLM-L6-v2` (configurable via `EMBEDDING_MODEL`) |
| Architecture | BERT-style encoder: 6 layers, 12 attention heads, hidden size 384, about 22.7M parameters (verified on the loaded model) |
| Pipeline | `Transformer → Pooling(mean) → Normalize` |
| Input | Text, lowercased and split into word-pieces by an uncased tokenizer, truncated at the model's `max_seq_length` (**256 tokens**) |
| Output | One **384-dimensional** float32 vector per text |
| Training | Pretrained and used as-is. DocMind does **no** fine-tuning. Per its model card, the publisher trained it contrastively on sentence pairs. |
| Runtime | The model's official ONNX export (`onnx/model.onnx`) on **ONNX Runtime** (CPU), with the `tokenizers` library. No PyTorch and no sentence-transformers at runtime. |

Code: `app/embeddings.py`. `load_encoder` is cached (`lru_cache`), so the model loads once per process. `Embedder.embed` encodes in batches of `EMBEDDING_BATCH_SIZE`.

## How the model runs (ONNX Runtime)

`OnnxSentenceEncoder` reproduces the sentence-transformers pipeline without PyTorch:

1. `download_model_files` fetches four files with `huggingface_hub`: `onnx/model.onnx`, `tokenizer.json`, `sentence_bert_config.json` and `1_Pooling/config.json`. The local Hugging Face cache is checked first, so a cached model causes no network call at startup. If a file cannot be loaded, `EmbeddingModelError` explains why.
2. WordPiece tokenisation with the model's `tokenizer.json`, truncated to `max_seq_length` from `sentence_bert_config.json` (256).
3. The transformer, run by an ONNX Runtime `InferenceSession` on the CPU.
4. Mean or CLS pooling, as configured in `1_Pooling/config.json`. Other pooling modes are rejected.
5. L2 normalisation (in `normalize_rows`).

Texts are sorted by length into batches so short texts are not padded to a long one; the vectors are returned in input order. ONNX Runtime's CPU memory arena is disabled so memory is released after a large batch instead of being held for the life of the process.

Any sentence-transformers model that ships `onnx/model.onnx` and uses mean or CLS pooling can be set through `EMBEDDING_MODEL`.

### Equivalence with sentence-transformers

The ONNX path was compared against `SentenceTransformer.encode` on 13 texts (the sample PDFs, a long text that hits truncation, and non-Latin text): cosine similarity **1.000000**, maximum absolute difference 1.3e-7. `tests/test_embeddings.py` repeats this check when sentence-transformers is installed (it is not a runtime dependency). Retrieval metrics on the sample evaluation set are identical to the previous PyTorch-based version (compared at the previous default chunk size, 800/150): Hit@1 0.70, Hit@3 0.95, Hit@5 1.00, MRR 0.838.

### Memory and load time

Measured on the development machine (Windows, the whole app imported, the same 300-chunk workload):

| | Model load | Working set after embedding | Peak |
|---|---|---|---|
| Previous PyTorch / sentence-transformers path | 15.3 s | 632 MB | 705 MB |
| ONNX Runtime path | 3.0 s (0.4 s from a warm cache) | 232 MB | 346 MB |

Linux numbers have not been measured.

## Why semantic similarity is useful

Keyword search fails on paraphrase: different words, same meaning. Embeddings place meaning, not spelling, into geometry, so ranking by vector similarity finds relevant passages written in different words. They do not understand your domain beyond what the model learned in pretraining, and they blur exact identifiers such as codes and part numbers.

## Why documents and queries must use the same model

Each model defines its own vector space; vectors from two different models are not comparable. DocMind enforces this: the index's `manifest.json` records the model name and dimension, and `FaissVectorStore.load_or_create` **refuses to load** an index built with a different model. That is why `EMBEDDING_MODEL` is environment-only and changing it means re-processing every document.

## Why vectors are normalised

Every vector is scaled to length 1 (L2 normalisation). For unit vectors, the dot product *equals* the cosine similarity:

```
cos(a, b) = (a · b) / (‖a‖ ‖b‖)  =  a · b      when ‖a‖ = ‖b‖ = 1
```

So the FAISS inner-product index returns cosine similarity directly, and the score shown in the UI is that cosine. The ONNX graph returns un-normalised token embeddings, so `normalize_rows` performs the normalisation after pooling; this also covers custom encoders (the tests use one).

## How dimensions are handled

`Embedder.dimension` asks the model for its output size (`get_embedding_dimension`, read from the ONNX graph's output shape), falling back to embedding a probe string. The vector store is created with that dimension, and every `add` and `search` checks that incoming vectors match it.

## Why ~600-character chunks

Text beyond 256 tokens is silently truncated by the model. The default of 600 characters (overlap 150) is roughly 110–150 English tokens, well below that limit. It replaced the previous default of 800 after a chunk-size sweep on the sample evaluation set, where smaller chunks retrieved better with this model (which was trained on short texts) and 600/150 had the best MRR; the dataset is small, so treat that as a weak signal ([EVALUATION.md](EVALUATION.md)). Chunk size is editable on the Settings page but capped at 1200 characters (`MAX_CHUNK_SIZE`), because 256 tokens is roughly 1000 characters of English and anything longer would be cut off before embedding; see [CONFIGURATION.md](CONFIGURATION.md).

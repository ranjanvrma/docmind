# Embeddings

An **embedding** is a fixed-length vector of numbers that a neural network assigns to a piece of text. The model is trained so that texts with similar meaning get vectors that point in similar directions. That is what lets "How do I get my money back?" match "Customers may request a refund within 30 days" even though they share almost no words.

## The model DocMind uses

| | |
|---|---|
| Model | `sentence-transformers/all-MiniLM-L6-v2` (configurable via `EMBEDDING_MODEL`) |
| Architecture | BERT-style encoder: 6 layers, 12 attention heads, hidden size 384, about 22.7M parameters (verified on the loaded model) |
| Pipeline | `Transformer → Pooling(mean) → Normalize` |
| Input | Text, lowercased and split into word-pieces by an uncased tokenizer, truncated at **256 tokens** |
| Output | One **384-dimensional** float32 vector per text |
| Training | Pretrained and used as-is. DocMind does **no** fine-tuning. Per its model card, the publisher trained it contrastively on sentence pairs. |
| Runtime | sentence-transformers on PyTorch (CPU). DocMind's own code never imports `torch`. |

Code: `app/embeddings.py`. `load_sentence_transformer` is cached, so the model loads once per process (about 5–15 s on first start). `Embedder.embed` encodes in batches of `EMBEDDING_BATCH_SIZE`.

## Why semantic similarity is useful

Keyword search fails on paraphrase: different words, same meaning. Embeddings place meaning, not spelling, into geometry, so ranking by vector similarity finds relevant passages written in different words. They do not understand your domain beyond what the model learned in pretraining, and they blur exact identifiers such as codes and part numbers.

## Why documents and queries must use the same model

Each model defines its own vector space; vectors from two different models are not comparable. DocMind enforces this: the index's `manifest.json` records the model name and dimension, and `FaissVectorStore.load_or_create` **refuses to load** an index built with a different model. That is why `EMBEDDING_MODEL` is environment-only and changing it means re-processing every document.

## Why vectors are normalised

Every vector is scaled to length 1 (L2 normalisation). For unit vectors, the dot product *equals* the cosine similarity:

```
cos(a, b) = (a · b) / (‖a‖ ‖b‖)  =  a · b      when ‖a‖ = ‖b‖ = 1
```

So the FAISS inner-product index returns cosine similarity directly, and the score shown in the UI is that cosine. The model's own `Normalize` layer already produces unit vectors; DocMind also passes `normalize_embeddings=True` and re-normalises in `normalize_rows`, which is redundant for this model but protects against custom encoders (the tests use one).

## How dimensions are handled

`Embedder.dimension` asks the model for its output size (supporting both the old and new sentence-transformers method names), falling back to embedding a probe string. The vector store is created with that dimension, and every `add` and `search` checks that incoming vectors match it.

## Why ~800-character chunks

Text beyond 256 tokens is silently truncated by the model. 800 characters is roughly 150–200 English tokens, comfortably below that limit. Chunk size is editable on the Settings page; see [CONFIGURATION.md](CONFIGURATION.md).

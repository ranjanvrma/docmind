# Vector search (FAISS)

[FAISS](https://github.com/facebookresearch/faiss) is a library for finding the nearest vectors to a query vector. It stores **vectors and integer IDs only**, never text. DocMind keeps the text and citation metadata in a separate store keyed by the same IDs. Code: `app/vector_store.py`.

## Index type

```python
faiss.IndexIDMap2(faiss.IndexFlatIP(384))
```

- **`IndexFlatIP`**: exact inner-product search. The query is compared with every stored vector (O(n·d)), so results are exact and there is no training step. For tens of thousands of chunks this takes milliseconds; in local measurements a search over a small index took about 11 ms including embedding the query.
- **`IndexIDMap2`**: lets DocMind assign its own 64-bit IDs (`add_with_ids`) and remove vectors by ID (`remove_ids`), which deleting and re-processing documents need.
- **Why not approximate indexes (IVF, HNSW)?** They trade a little recall for speed, and only pay off at hundreds of thousands to millions of vectors. Exact search keeps results deterministic and easy to reason about.

## Vector IDs and metadata mapping

`FaissVectorStore` holds `_metadata: dict[int, dict]`, keyed by the same IDs as the FAISS index, with `chunk_id`, `doc_id`, `doc_name`, `page_number`, `chunk_index` and `text`. IDs come from a counter (`_next_id`) that **never goes backwards**, so a deleted ID can never be reused and attached to the wrong text.

Search: `index.search(query, k)` returns `(scores, ids)`; IDs of `-1` are padding and skipped; each ID is mapped back to its metadata to build a `Chunk`. With a document filter, the store searches everything and filters afterwards (for a flat index this costs the same).

## Similarity scores

Because all vectors are unit length, the inner product is the **cosine similarity**, in [−1, 1]. Higher means closer in meaning. Scores are relative to the model and the corpus: in this project's tests, correct top matches scored roughly 0.3–0.6, so there is no universal "relevant" threshold. DocMind ranks rather than thresholds. The UI labels the score **"Similarity"**, never "accuracy" or "confidence".

## Persistence

`save()` writes three files atomically (temp file + rename), with the manifest last:

| File | Contents |
|---|---|
| `index.faiss` | `faiss.serialize_index` bytes (avoids FAISS's own file I/O, which fails on non-ASCII Windows paths) |
| `metadata.json` | ID → chunk metadata |
| `manifest.json` | embedding model, dimension, `next_id`, vector count |

## Consistency guarantees

On load, `load_or_create` raises a `VectorStoreError` (never a raw exception) with recovery instructions if:
- the manifest's model or dimension differs from the configured model;
- any file is missing, unreadable or corrupt;
- metadata entries lack required fields;
- the index size, metadata count and manifest count disagree.

The document registry is a third store. `DocMindService` saves the index **before** marking documents processed, rolls back on a failed save, and at startup reconciles the two: vectors of documents not marked processed are dropped, and "processed" documents with no vectors go back to `uploaded`. If loading fails, the API still starts and every endpoint returns `503` with the explanation ([TROUBLESHOOTING.md](TROUBLESHOOTING.md)).

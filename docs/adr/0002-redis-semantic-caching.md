# ADR 0002: Redis semantic caching for LLM and retrieval calls

- **Status:** accepted
- **Date:** 2026-06-20
- **Deciders:** robertjames
- **Change reference:** doc round; implementation tracked in `docs/gaps.md` (cache module)

## Context

Research and content runs repeatedly issue semantically similar questions and
retrieval queries. Each is a multi-second LLM or ANN round-trip and a billable API
call. We want lower latency and cost without changing answer quality, and we
already provision Azure Managed Redis for working memory.

## Decision

Add a **semantic cache in Azure Managed Redis** in front of LLM completions and
retrieval (`search_corpus_*`, `web_search`): embed the query, vector-search the
cache, and return a stored response on a high-similarity hit; otherwise compute,
then write through. Redis remains **ephemeral / TTL'd** - never a source of truth;
Cosmos holds durable records.

## Why

Semantic (embedding-similarity) caching catches paraphrases that exact-match
caching misses, cutting common-question latency toward a single vector lookup and
removing redundant inference cost. Redis is already in the data tier for memory,
so this adds a capability to an existing component rather than a new dependency.

## Alternatives considered

- **Exact-string cache** - rejected: misses paraphrases, low hit rate for
  natural-language queries.
- **Cache in Cosmos / Postgres** - rejected: Redis is the latency-optimized,
  TTL-native tier; durable stores are for records, not hot cache.

## Consequences

- Positive: lower latency and cost on repeated/similar queries; consistent
  answers across paraphrases.
- Negative / cost: a similarity threshold to tune (too low -> wrong cache hits);
  cache invalidation when the corpus or prompts change; embedding cost on lookups.
- Follow-ups: implement `src/store/cache.py`; choose similarity threshold + TTL;
  add cache hit/miss metrics to observability. See `docs/gaps.md`.

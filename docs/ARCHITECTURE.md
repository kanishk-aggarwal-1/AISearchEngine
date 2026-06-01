# SignalScope AI Architecture

## Overview

SignalScope AI is a full-stack retrieval and explanation platform that helps users search live information across tech news, research papers, sports coverage, and world news.

The system is organized as a production-style pipeline rather than a simple chat UI:

1. Ingest documents from multiple live sources
2. Normalize, enrich, deduplicate, and persist them
3. Retrieve relevant candidates at query time
4. Rank them with hybrid retrieval signals
5. Generate grounded answers and follow-up responses
6. Support saving, alerting, and admin operations around the same content graph

## Backend flow

### 1. Source ingestion

Source providers are grouped by category and managed through the source registry.

Inputs:
- RSS feeds
- arXiv and research-oriented APIs
- sports/event sources
- manual webhook-triggered topics
- scheduled seed topics

Operational controls:
- source health tracking
- enable/disable toggles
- retry/backoff on provider fetch
- source freshness summaries
- ingestion run history

### 2. Persistence

SignalScope AI now supports:
- Postgres for production-style deployments
- SQLite fallback for local development and tests

Persisted entities include:
- auth users and sessions
- verification and password reset tokens
- user profiles
- follows/watchlist
- documents
- document chunks
- bookmarks
- alerts and alert delivery settings
- search history
- saved sessions
- saved contexts
- source status
- ingestion runs
- fallback query cache

### 3. Retrieval

The retrieval stack combines:
- query rewriting
- query expansion
- live candidate fetch
- recent stored document retrieval
- optional vector retrieval
- chunk lookup for grounded support passages

Ranking signals include:
- semantic similarity
- lexical overlap
- recency
- source credibility
- personalization
- chunk support
- exact phrase match
- coverage scoring
- title overlap
- source diversity reranking

### 4. Explanation and grounding

When configured, the app uses:
- Gemini
- OpenAI

When they are not configured, the app uses deterministic fallback explanation behavior.

Answer generation is grounded in retrieved sources and supports:
- structured explanation modes
- structured explanation formats
- comparisons
- timelines
- follow-up responses over saved context

## Frontend flow

The primary workflow on the home page is:

1. Search for a topic
2. Read the grounded answer
3. Inspect sources and grounding snippets
4. Compare sources and related topics
5. Save context or bookmark sources
6. Ask follow-up questions
7. Create alerts

Supporting routes:
- category pages
- topic pages
- sports team pages
- research paper pages

## Operations and deployment

Operational readiness features include:
- lightweight `/health`
- deep `/health/deep`
- `/metrics`
- `/metrics/prometheus`
- admin dashboard
- manual reingest

Deployment assets include:
- backend Dockerfile
- frontend Dockerfile
- local and production-style Compose files
- nginx reverse proxy config
- GitHub Actions CI

## Retrieval evaluation

The repository includes an offline retrieval evaluation harness:
- dataset: `eval/eval_queries.json`
- runner: `scripts/run_eval.py`

It reports:
- Recall@5
- Recall@10
- MRR
- nDCG@10
- source diversity
- citation coverage
- no-result rate

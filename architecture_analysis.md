# Agent Architecture Analysis (Tokens and Optimization)

## Request

Analyze the agent architecture in general terms, explaining what type of agent it is, which tools it uses, and listing what consumes API tokens, to highlight optimization points. Present in diagram form.

## Result

### Agent Type

**Three-layer hybrid architecture**: Deterministic Router (LLM) → Route decides between General Agent (Direct Prompting) or PI Agent (ADK ReAct + MCP Tools).

### Tools (8 MCP Tools)

1. `consultar_tag` — current value + metadata of PI tags
2. `tag_statistics` — historical statistics (mean, max, min, sum, consumption)
3. `tag_calculus` — integral, derivative, rate of change
4. `status_pims_tool` — PI Web API health check (/dataservers)
5. `search_pi_points` — tag discovery by name/description
6. `tag_attributes_tool` — configuration attributes (compression, scan, etc.)
7. `generate_test_artifact_tool` (feature flag) — QA test file generation
8. `export_csv_to_drive_tool` (feature flag) — CSV export to Google Drive

### Flow Diagram and Token Consumers

```
POST /chat
  │
  ├─ 1. Load Memory (Redis — 0 LLM tokens)
  │
  ├─ 2. OCR (if images present)  ← CONSUMER #1
  │     LiteLLM multimodal acompletion (num_predict=512)
  │     1 call PER IMAGE (base64 image = many tokens)
  │     Retry: 3× | Gemini: fallback model
  │
  ├─ 3. Router (always)  ← CONSUMER #2
  │     LiteLLM acompletion (num_predict=128)
  │     1 call | ROUTER_PROMPT (~90 lines)
  │
  ├─ [if pims] 4. RAG Embedding  ← CONSUMER #3
  │     Embedding provider (Ollama/Gemini API)
  │     1 external call + Qdrant search (0 LLM tokens)
  │
  ├─ 5. Agent
  │    ├─ [conversa_comum] General Agent  ← CONSUMER #4
  │    │     LiteLLM acompletion (num_predict=1024)
  │    │     1 call | Retry: 3× | Gemini: fallback model
  │    │
  │    └─ [pims] PI Agent ADK  ← CONSUMER #5 (LARGEST)
  │          ADK Runner.run_async() — 2 to 8 iterations
  │          Each iteration = 1 LLM call (LiteLlm/Gemini)
  │          Context: system prompt (~175L) + memory (8 turns)
  │                    + RAG (CHUNK 01 + 3 chunks) + tool results
  │          External retry: 3× per model
  │          Gemini: fallback = 2 models × 3 retries = up to 6×
  │
  └─ 6. Save Memory (Redis — 0 LLM tokens)
```

### Consolidated Consumption Table per Request

| # | Consumer | Calls | num_predict | Retry | Context |
|---|---|---|---|---|---|
| 1 | OCR | N images | 512 | 3× | Prompt + base64 image |
| 2 | Router | 1 | 128 | 0 | ROUTER_PROMPT + message |
| 3 | Embedding | 1 (pims) | N/A | provider | Query text |
| 4 | General Agent | 1 (general) | 1024 | 3× | Prompt + memory + msg |
| 5 | PI Agent ADK | 2–8 (avg 2–4) | 1024 | 3× | System prompt + memory + RAG + msg + tool results |

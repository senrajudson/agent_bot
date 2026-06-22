# Agent Bot — Guia Completo do Projeto

> Documento gerado em 2026-06-22. Reflete o estado real do código-fonte
> neste commit.

---

## Sumário

| # | Seção |
|---|-------|
| 1 | [Visão Geral](#1-visão-geral) |
| 2 | [Stack Tecnológica](#2-stack-tecnológica) |
| 3 | [Arquitetura](#3-arquitetura) |
| 4 | [Fluxo Principal](#4-fluxo-principal-request-lifecycle) |
| 5 | [LLM Provider](#5-llm-provider) |
| 6 | [RAG — Retrieval-Augmented Generation](#6-rag--retrieval-augmented-generation) |
| 7 | [Subsistema MCP Server](#7-subsistema-mcp-server) |
| 8 | [Math Tool Service](#8-math-tool-service) |
| 9 | [Bridge Google Chat](#9-bridge-google-chat) |
| 10 | [Observabilidade](#10-observabilidade) |
| 11 | [Tools do Agente PI](#11-tools-do-agente-pi) |
| 12 | [PI Web API Client](#12-pi-web-api-client) |
| 13 | [Memória de Conversa](#13-memória-de-conversa) |
| 14 | [OCR — Extração de Imagens](#14-ocr--extração-de-imagens) |
| 15 | [Schemas e Modelos](#15-schemas-e-modelos) |
| 16 | [Variáveis de Ambiente](#16-variáveis-de-ambiente) |
| 17 | [Comandos](#17-comandos) |
| 18 | [Endpoints e Entrypoints](#18-endpoints-e-entrypoints) |
| 19 | [Reg de Negócio](#19-regras-de-negócio) |
| 20 | [Utilitários](#20-utilitários) |
| 21 | [Estrutura de Testes](#21-estrutura-de-testes) |
| 22 | [Problemas Comuns](#22-problemas-comuns) |
| 23 | [Arquivo de Documentação RAG](#23-arquivo-de-documentação-rag) |

---

## 1. Visão Geral

O **Agent Bot** é uma API conversacional inteligente construída com FastAPI que opera como um agente especializado em consultas ao **PI System** (PIMS) via **PI Web API**. O sistema interpreta perguntas em linguagem natural, rota automaticamente para o agente correto, recupera contexto via **RAG** de documentação técnica, e executa tools especializadas para retornar dados reais de tags industriais.

### Domínio de Atuação

- Consulta de valores atuais de tags do PI System
- Consulta de metadados (descrição, unidade, tipo, digital set, instrumenttag, locations)
- Estatísticas históricas (média, máximo, mínimo, soma, desvio padrão, consumo)
- Cálculos temporais (integralização, derivada, taxa de variação)
- Consulta de digital states e digital sets
- Status operacional do PIMS via logs Grafana/Loki

### Subsistemas do Monorepo

O projeto é organizado como um **monorepo** contendo 4 componentes que rodam como processos separados:

| Componente | Tipo | Porta (local) | Porta (Docker) | Descrição |
|---|---|---|---|---|
| **app** | FastAPI | 8002 | 8002 | API principal: `/chat`, `/health` |
| **mcp_server** | FastMCP | 8003 | 8005 | Servidor de tools via protocolo MCP |
| **calc** | FastAPI | 8001 | 8001 | Math Tool: `/calculate`, `/stats`, `/calculus` |
| **bridge** | Worker | — | — | Google Chat Bridge (Pub/Sub → Agent Bot) |

---

## 2. Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Framework HTTP | FastAPI + uvicorn |
| LLM | Groq (padrão), com suporte a Ollama, Gemini, OpenAI-compatible |
| Agent Framework | **Google ADK** (`google-adk[mcp]` v2.2.0+) com `LlmAgent` + `McpToolset` |
| Tool Protocol | **FastMCP** (`fastmcp>=2.0.0`) via Model Context Protocol (Streamable HTTP) |
| LLM direto (router/ocr/general) | LiteLLM (`litellm`) — chamadas `acompletion` diretas |
| Vector Store | Qdrant (`pi_web_api_guide` collection, 768-dim, cosine) |
| Embeddings | Ollama `nomic-embed-text-v2-moe` |
| Memória de Conversa | Redis |
| Observabilidade | Phoenix (Arize) via OpenTelemetry + SpanProcessor customizado |
| Bridge | Google Cloud Pub/Sub → Google Chat API |
| Containerização | Docker Compose |

---

## 3. Arquitetura

```
agent_bot/                              # monorepo
├── app/                                # API FastAPI principal (porta 8002)
│   ├── main.py                         # /chat, /health
│   ├── core/
│   │   └── config.py                   # Pydantic Settings (carrega .env)
│   ├── agent/
│   │   ├── orchestrator.py             # Orquestrador: roteamento → RAG → agente → memória
│   │   ├── router.py                   # Classificador de intenção via LiteLLM
│   │   ├── general_agent.py            # Agente de conversa geral via LiteLLM
│   │   └── pi_agent.py                 # Agente PI System via Google ADK + McpToolset
│   ├── clients/
│   │   ├── provider_client.py          # Factory de ADK BaseLlm (Groq, Ollama, Gemini, OpenAI)
│   │   ├── qdrant_client.py            # RAG: busca semântica + Chunk 20 fixo
│   │   ├── pi_web_api_client.py        # Cliente HTTP PI Web API (batch, streams, enumeration)
│   │   ├── redis_client.py             # Cliente Redis (memória)
│   │   ├── grafana_loki_client.py      # Cliente Grafana/Loki
│   │   └── math_tool_client.py         # Cliente HTTP Math Tool
│   ├── schemas/
│   │   ├── chat.py                     # ChatRequest, ChatResponse, ChatImage, OcrResult
│   │   ├── llm.py                      # LLMParams + AGENT_DEFAULT
│   │   └── math_tool.py                # Enums: StatsOperation, CalculusOperation, etc.
│   ├── prompts/
│   │   ├── pi_agent_prompt.py          # System prompt do agente PI (com timestamp dinâmico)
│   │   ├── router_prompt.py            # Prompt de classificação de rota
│   │   ├── general_agent_prompt.py     # Prompt do agente de conversa geral
│   │   └── ocr_query_prompt.py         # Prompt de OCR de imagens
│   ├── services/
│   │   ├── consultar_tag_service.py    # Lógica de consulta de tags (batch + digital states)
│   │   ├── math_tool_service.py        # Lógica de estatísticas e cálculos temporais
│   │   ├── status_pims_service.py      # Lógica de consulta de logs PIMS
│   │   └── chat_memory_service.py      # Lógica de memória Redis
│   ├── tasks/
│   │   └── ocr_query.py                # OCR de imagens via LiteLLM multimodal
│   ├── utils/
│   │   ├── tag_extractor.py            # Regex de tags + merge_unique_tags
│   │   ├── digital_states.py           # Enriquecimento com digital states
│   │   ├── pi_response_formatter.py    # Formatação de batch response do PI Web API
│   │   ├── math_expression.py          # Limpeza de expressões aritméticas
│   │   ├── math_pi_series.py           # Extração de séries temporais do PI
│   │   ├── math_time_unit.py           # Detecção de unidade temporal
│   │   ├── math_units.py               # Inferência de unidade temporal por eng unit
│   │   ├── ocr_treatment.py            # Tratamento e normalização de saída OCR
│   │   ├── time_context.py             # Helpers de tempo
│   │   └── google_chat_format.py       # Normalização markdown para Google Chat
│   ├── bridge/
│   │   └── google_chat/
│   │       ├── worker.py               # Worker Pub/Sub → Agent Bot
│   │       ├── agent_adapter.py        # Adaptador HTTP para process_message
│   │       ├── chat_client.py          # Cliente Google Chat API (envio de mensagens)
│   │       ├── parser.py               # Parse de eventos Google Chat
│   │       ├── media_downloader.py     # Download de anexos (PNG/JPEG/WEBP)
│   │       ├── dedupe_store.py         # Deduplicação (Redis com in-memory fallback)
│   │       ├── pubsub_subscriber.py    # Assinante Pub/Sub
│   │       ├── config.py               # Configuração específica da bridge
│   │       └── models.py               # Modelos da bridge
│   └── observability/
│       └── phoenix.py                  # Setup Phoenix + _TokenDedupSpanProcessor
│
├── mcp_server/                         # Subsistema MCP (porta 8003 local / 8005 Docker)
│   ├── server.py                       # FastMCP server: 4 tools
│   ├── core/
│   │   └── config.py                   # Configuração MCP (separate .env)
│   ├── clients/
│   │   ├── pi_web_api_client.py        # Pi Web API client (duplicado do app/)
│   │   ├── grafana_loki_client.py      # Grafana/Loki client
│   │   ├── math_tool_client.py         # Math Tool client
│   │   └── redis_client.py             # Redis client
│   ├── services/
│   │   ├── consultar_tag_service.py    # Consulta de tags
│   │   ├── math_tool_service.py        # Estatísticas e cálculos
│   │   └── status_pims_service.py      # Status PIMS
│   ├── utils/                          # Espelha app/utils (sem observability)
│   ├── schemas/
│   │   └── math_tool.py
│   └── Dockerfile
│
├── calc/                               # Subsistema Math Tool (porta 8001)
│   ├── app/
│   │   └── main.py                     # FastAPI: /calculate, /stats, /calculus
│   ├── mathtool.Dockerfile
│   └── requirements.txt
│
├── scripts/
│   ├── ingest_pi_guide.py              # Ingestão RAG (CHUNK → Qdrant)
│   └── clean_polluted_memory.py        # Manutenção Redis
│
├── tests/                              # Diretório vazio (estrutura preparada)
│   ├── unit/
│   ├── integration/
│   └── agent/
│
├── docs/
│   └── BRIDGE_GOOGLE_CHAT.md           # Doc completa da bridge (912 linhas)
│
├── PI_WEB_API_AGENT_GUIDE.md           # Fonte RAG (22 CHUNKs)
├── pyproject.toml
├── docker-compose.yaml                 # 4 serviços
├── Dockerfile                          # Build do app principal
└── secrets/                            # Credenciais GCP (não versionadas)
```

---

## 4. Fluxo Principal (Request Lifecycle)

```
POST /chat  (FastAPI, porta 8002)
  │
  ▼
process_message(ChatRequest)
  │
  ├─→ Extrai: message, images, user_id
  │     conversation_id = user_id (derivado, não é input do cliente)
  │
  ├─→ _load_memory()
  │     └─→ Redis: lrange pi_chat:memory:{user_id}:turns  (últimos 8 turns)
  │
  ├─→ _ocr_step()
  │     └─→ se há images: litellm.acompletion() multimodal (uma por imagem)
  │         ├─→ texto extraído via LLM
  │         ├─→ tags extraídas via TAG_REGEX
  │         └─→ resultado injetado no contexto
  │
  ├─→ route_message()
  │     └─→ litellm.acompletion(format=json, num_predict=128)
  │         └─→ classifica: conversa_comum | calculadora | pims
  │
  ├─→ _run_selected_agent(route)
  │     │
  │     ├─→ "conversa_comum" → run_general_agent()
  │     │     └─→ litellm.acompletion(general_agent_prompt, num_predict=1024)
  │     │         → resposta direta, sem tools
  │     │
  │     └─→ "pims" → run_pi_agent()
  │           ├─→ build_rag_context()
  │           │     ├─→ CHUNK 20 (fixo, sempre injetado)
  │           │     └─→ top-3 chunks do Qdrant (Ollama embeddings)
  │           │
  │           ├─→ monta LlmAgent(instruction=AGENT_SYSTEM_PROMPT)
  │           │     └─→ tools: McpToolset(url=MCP_SERVER_URL)
  │           │
  │           ├─→ Runner.run_async()   ← até MAX_AGENT_STEPS=8
  │           │     │
  │           │     ├─→ [iteração 1] ADK → LiteLlm → acompletion
  │           │     │     └─→ decide chamar tool
  │           │     │
  │           │     ├─→ [iteração 2] ADK → execute_tool → MCP server
  │           │     │     └─→ mcp_server/services/ → pi_web_api_client ou math_tool
  │           │     │
  │           │     ├─→ [iteração 3+] LLM processa resultado da tool
  │           │     │
  │           │     └─→ final_output (resposta final do agente)
  │           │
  │           └─→ detecta loops: _detect_repeated_tool_calls() ≥ 3 repetições → aborta
  │
  ├─→ _save_memory()
  │     └─→ Redis: rpush + ltrim + expire (TTL 7 dias, max 16 entradas)
  │
  └─→ ChatResponse
```

---

## 5. LLM Provider

O sistema suporta múltiplos provedores LLM, configuráveis via `LLM_PROVIDER` no `.env`.

### Provedores

| Provider | Config | Biblioteca |
|----------|--------|-----------|
| `groq` | `GROQ_API_KEY`, `GROQ_MODEL` | LiteLLM via ADK `LiteLlm` |
| `ollama` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | LiteLLM via ADK `LiteLlm` |
| `gemini` | `GEMINI_API_KEY`, `GEMINI_MODEL` | ADK `Gemini` (nativo) |
| `openai_compatible` | `OPENAI_COMPATIBLE_API_KEY`, `_BASE_URL`, `_MODEL` | LiteLLM via ADK `LiteLlm` |

### Factory

`app/clients/provider_client.py` → `get_llm(params)` retorna uma instância de `google.adk.models.base_llm.BaseLlm`:

- **Gemini**: retorna `Gemini` (nativo Google GenAI)
- **Demais**: retorna `LiteLlm` (wrapper ADK que internamente usa LiteLLM)

Isso significa que o **openinference-instrumentation-litellm** instrumenta todas as chamadas LLM do ADK (via spans `acompletion`), mesmo quando o provedor não é LiteLLM.

### Parâmetros por Uso

| Uso | Arquivo | temp | num_ctx | num_predict | top_p | extras |
|-----|---------|------|---------|-------------|-------|--------|
| **Router** | `router.py` | 0 | 8192 | 128 | 0.1 | format=json, think=False |
| **General Agent** | `general_agent.py` | 0 | 8192 | 1024 | 0.1 | — |
| **PI Agent** | `pi_agent.py` | 0 | 8192 | 1024 | 0.1 | — |
| **OCR** | `ocr_query.py` | 0 | 8192 | 512 | 0.1 | — |

### AGENT_DEFAULT (Ollama)

Dicionário de defaults aplicado em chamadas Ollama (`provider_client.py`):

```python
AGENT_DEFAULT = {
    "temperature": 0,
    "top_p": 0.1,
    "repeat_penalty": 1.1,
    "keep_alive": "1000h",
    "num_ctx": 8192,
}
```

---

## 6. RAG — Retrieval-Augmented Generation

### Componentes

| Componente | Valor |
|---|---|
| Documento fonte | `PI_WEB_API_AGENT_GUIDE.md` (22 CHUNKs) |
| Vector Store | Qdrant (`pi_web_api_guide`, 768-dim, cosine) |
| Embeddings | Ollama `nomic-embed-text-v2-moe` (via `POST /api/embed`) |
| Ingestão | `scripts/ingest_pi_guide.py` |
| CHUNK fixo | CHUNK 20 (sempre injetado, excluído do Qdrant) |

### Como funciona

1. O documento é dividido em **22 CHUNKs** por headers (`# CHUNK 01`, `# CHUNK 02`, ..., `# CHUNK 22`)
2. Cada CHUNK (exceto o 20) é embedded e armazenado no Qdrant com metadados (`chunk_number`, `title`, `content`)
3. **CHUNK 20** ("Seleção de tool e resumo operacional") é sempre injetado como contexto fixo
4. A cada query, o texto do usuário é embedded e busca os top-3 chunks mais similares
5. O contexto final = **CHUNK 20** (fixo) + **top-3 chunks** (retrieved)

### Fluxo RAG

```
build_rag_context(query, top_k=3)
  ├─→ _load_chunk_20()              ← Lê CHUNK 20 do .md (cached, regex por header)
  ├─→ retrieve_relevant_chunks()    ← Embed query → Qdrant search
  └─→ Retorna string com contexto concatenado
```

### CHUNK 20 — Contexto Fixo

O CHUNK 20 contém o resumo operacional mínimo da PI Web API:
- Fluxo de 2 passos: path → WebId → stream endpoints
- Lista de campos importantes (WebId, Name, Descriptor, PointType, etc.)
- Todos os endpoints de stream (value, recorded, interpolated, summary)
- Orientação de seleção de tool

### Ingestão

```bash
# Deletar collection antiga e reingestir
curl -X DELETE http://10.247.179.197:6333/collections/pi_web_api_guide
poetry run python scripts/ingest_pi_guide.py
```

Regex de chunks no script: `^#\s+CHUNK\s+(\d+)\s*-\s*(.+)$`

---

## 7. Subsistema MCP Server

O **MCP Server** (`mcp_server/`) é um servidor FastMCP standalone que expõe as 4 tools do agente PI via protocolo **Model Context Protocol** (Streamable HTTP).

### Por que existe

O Google ADK consome tools via `McpToolset`, que se conecta a um servidor MCP remoto. O MCP server roda em processo separado para isolar o deploy e permitir escala independente do app principal.

### Arquitetura

```
PI Agent (app/agent/pi_agent.py)
  └─→ McpToolset(url=MCP_SERVER_URL)
        └─→ MCP Server (mcp_server/server.py, porta 8005)
              ├─→ consultar_tag()      → services/consultar_tag_service.py
              ├─→ tag_statistics()     → services/math_tool_service.py
              ├─→ tag_calculus()       → services/math_tool_service.py
              └─→ status_pims()       → services/status_pims_service.py
```

### Tools Expostas

| Tool | Parâmetros | Descrição |
|------|-----------|-----------|
| `consultar_tag` | `tags: list[str]`, `pergunta_usuario: str \| None` | Valor atual e metadados de tags |
| `tag_statistics` | `tags, operation, start_time, end_time, data_method, interval, summary_type, summary_duration, calculation_basis, context_text, max_count` | Estatísticas históricas |
| `tag_calculus` | `tags, operation, start_time, end_time, data_method, interval, summary_type, summary_duration, calculation_basis, time_unit, context_text, max_count` | Integralização e derivada |
| `status_pims` | `pergunta_usuario: str \| None`, `lookback_minutes: int \| None` | Status via Grafana/Loki |

### Configuração

- **MCP_HOST**: `0.0.0.0`
- **MCP_PORT**: `8003` (local) / `8005` (Docker)
- **MCP_SERVER_URL**: `http://localhost:8015/mcp` (local default no app) / `http://mcp_server:8005/mcp` (Docker)
- Possui `.env` próprio em `mcp_server/.env`

### Reuso de Código

O MCP server **duplica** intentionalmente os clients e services do `app/`:
- `pi_web_api_client.py`, `math_tool_client.py`, `grafana_loki_client.py`, `redis_client.py`
- `consultar_tag_service.py`, `math_tool_service.py`, `status_pims_service.py`
- Utilitários em `mcp_server/utils/`

Isso permite deploy e restart independentes.

---

## 8. Math Tool Service

O **Math Tool** (`calc/`) é um serviço FastAPI puro (sem LLM) que executa cálculos matemáticos em dados de tags.

### Endpoints

| Endpoint | Modelo de Entrada | Descrição |
|----------|-------------------|-----------|
| `POST /calculate` | `CalculateRequest { expression: str }` | Expressão aritmética simples |
| `POST /stats` | `StatsRequest { values: list[float], operations: list[str] }` | Estatísticas sobre lista de valores |
| `POST /calculus` | `CalculusRequest { operation, time_unit, points: list[TimePoint] }` | Integral e derivada temporal |

### Limites

- Máximo de **100.000 valores** por request
- Python puro: `statistics`, `math`, `ast` (sem dependências externas)

### Modelos Pydantic

```python
class TimePoint(BaseModel):
    timestamp: Union[str, datetime]
    value: float

class CalculusRequest(BaseModel):
    operation: str          # "integral" ou "derivative"
    time_unit: str = "second"  # "second", "minute", "hour"
    points: list[TimePoint]
```

### Configuração

- **MATH_TOOL_BASE_URL**: `http://math_tool:8001` (Docker) / `http://localhost:8001` (local)
- **MATH_TOOL_TIMEOUT_SECONDS**: 120

---

## 9. Bridge Google Chat

A **Google Chat Bridge** (`app/bridge/google_chat/`) é um adaptador que conecta o Agent Bot ao Google Chat via Google Cloud Pub/Sub.

### Documentação Completa

A doc detalhada (912 linhas) está em `docs/BRIDGE_GOOGLE_CHAT.md`.

### Fluxo de Mensagens

```
Google Chat (usuário envia mensagem)
  └─→ Google Cloud Pub/Sub → Subscription
        └─→ Bridge Worker (app.bridge.google_chat.worker)
              ├─→ DedupeStore (Redis, TTL 86400s)
              ├─→ parser.py → parse_google_chat_event()
              ├─→ media_downloader.py → download imagens anexas
              ├─→ agent_adapter.py → POST http://localhost:8002/chat
              │     └─→ process_message(ChatRequest)
              └─→ chat_client.py → Google Chat API
                    └─→ envia resposta como reply
```

### Funcionalidades

- Recebe mensagens assincronamente via Pub/Sub (pull/push subscription)
- Parse de payloads Google Chat em objetos Python
- Download de anexos (PNG, JPEG, WEBP) para OCR
- Deduplicação via Redis (com in-memory fallback)
- Mensagem "thinking" temporária enquanto processa
- Erros tratados sem causar loops de retry

### Configuração (Env Vars)

| Variável | Descrição |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | ID do projeto GCP |
| `GOOGLE_APPLICATION_CREDENTIALS` | Caminho para `chat_secret.json` |
| `GOOGLE_CHAT_SUBSCRIPTION` | Caminho completo da subscription Pub/Sub |
| `GOOGLE_CHAT_SCOPES` | Escopos OAuth (`chat.bot`, `chat.messages.readonly`) |
| `AGENT_INTERNAL_URL` | URL interna do `/chat` (ex: `http://localhost:8002/chat`) |
| `GOOGLE_CHAT_SEND_THINKING_MESSAGE` | `true` para enviar mensagem temporária |
| `GOOGLE_CHAT_THINKING_TEXT` | Texto da mensagem "pensando" (default: "Um momento...") |
| `GOOGLE_CHAT_DEDUPE_TTL_SECONDS` | TTL da deduplicação (default: 86400) |

### Execução

```bash
# Local
python -m app.bridge.google_chat.worker --send

# Docker (container agent_bot_chat_bridge)
# Comando: python -m app.bridge.google_chat.worker --send
```

---

## 10. Observabilidade

### Stack

| Componente | Função |
|---|---|
| **Phoenix** (Arize) | UI de traces + collector |
| **OpenTelemetry** | Instrumentação automática (FastAPI, httpx) |
| **openinference-instrumentation-litellm** | Instrumenta `litellm.acompletion` → span `acompletion` |
| **Google ADK telemetry** | Cria spans `call_llm`, `generate_content`, `invoke_agent`, `execute_tool` |

### Instrumentadores Ativos

1. **FastAPI** (`FastAPIInstrumentor.instrument_app`) — spans HTTP request/response
2. **LiteLLM** (`LiteLLMInstrumentor.instrument`) — spans de chamadas LLM
3. **Google ADK** (nativo) — spans de agente, tools e inferência

### _TokenDedupSpanProcessor

**SpanProcessor customizado** que resolve a duplicação de tokens no Phoenix:

- O Google ADK grava `gen_ai.usage.input_tokens` e `gen_ai.usage.output_tokens` nos spans `call_llm` e `generate_content`
- O openinference-instrumentation-litellm grava `llm.token_count.*` no span `acompletion` (mais profundo)
- O Phoenix UI soma todos os descendentes, inflando o total (3x)

**Solução**: `_TokenDedupSpanProcessor` (em `phoenix.py`) remove os atributos de token dos spans ADK (identificados por `gcp.vertex.agent.invocation_id`), preservando-os apenas no `acompletion`.

**Detalhe crítico**: o processor é registrado com `add_span_processor(..., replace_default_processor=False)` para preservar o `SimpleSpanProcessor` padrão do Phoenix (que é o exportador real). Sem `replace_default_processor=False`, o exportador é removido e nenhum trace chega ao Phoenix.

### Configuração

| Variável | Padrão | Descrição |
|---|---|---|
| `PHOENIX_ENABLED` | `false` | Habilitar tracing |
| `PHOENIX_PROJECT_NAME` | `pi-chat-api` | Nome do projeto no Phoenix |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006/v1/traces` | Endpoint OTLP |
| `PHOENIX_PROTOCOL` | `http/protobuf` | Protocolo de transporte |

### Traces

Enviados via OTLP HTTP (`/v1/traces`, protobuf) para o Phoenix collector.

---

## 11. Tools do Agente PI

As 4 tools do agente PI vivem no **MCP Server** (não mais em `app/tools/`). O agente ADK consome-as via `McpToolset`.

### 11.1 consultar_tag

**Propósito**: Consulta valor atual e metadados de tags do PI System.

**Parâmetros**:
- `tags`: Lista de nomes de tags (preservar exatamente)
- `pergunta_usuario`: Pergunta original (opcional)

**Retorna**: Valor atual, descriptor, unidade, tipo, digital set, instrumenttag, locations, digital states.

**Fluxo interno**:
1. Monta batch request com `/points?path=...` + `/streams/{webId}/value` + attributes
2. Executa batch via `POST /batch`
3. Enriquece com digital states (se `PointType == "Digital"`)
4. Formata resposta com metadados + valor

### 11.2 tag_statistics

**Propósito**: Estatísticas históricas (média, máximo, mínimo, soma, contagem, mediana, amplitude, variância, desvio padrão, consumo total).

**Parâmetros**:
- `tags`: Lista de tags
- `operation`: Operação estatística (mean, max, min, sum, count, etc.)
- `start_time`, `end_time`: Período
- `data_method`: `recorded`, `interpolated` ou `summary`
- `interval`: Para `interpolated` (ex: `1m`, `5m`, `1h`)
- `summary_type`, `summary_duration`, `calculation_basis`: Para `summary`
- `context_text`: Pergunta original
- `max_count`: Limite de valores (recorded)

**Fluxo interno**:
1. Busca dados temporais via PI Web API (`buscar_serie_pi`)
2. Envia dados para Math Tool Service (`/stats`)
3. Retorna resultado formatado com unidade inferida

### 11.3 tag_calculus

**Propósito**: Integralização e derivada temporal.

**Parâmetros**:
- Mesmos temporais do statistics
- `operation`: `integral` ou `derivative`
- `time_unit`: Unidade temporal do cálculo final (`second`, `minute`, `hour`, `none`)
- `context_text`: Pergunta original (para detectar unidade desejada)

**Fluxo interno**:
1. Busca dados temporais via PI Web API
2. Detecta unidade temporal via `detectar_time_unit()` e `inferir_time_unit_por_unidade()`
3. Envia dados para Math Tool Service (`/calculus`)
4. Retorna resultado formatado

### 11.4 status_pims

**Propósito**: Status operacional do PIMS via logs Grafana/Loki.

**Parâmetros**:
- `pergunta_usuario`: Pergunta original
- `lookback_minutes`: Janela de tempo (default: 20 min; 60=status atual, 120=2h, 1440=hoje)

**Fluxo interno**:
1. Consulta Grafana/Loki via `query_loki_range`
2. Filtra linhas de erro/aviso por keywords
3. Retorna resumo do status (total logs, erros, alertas, recentes)

---

## 12. PI Web API Client

Cliente HTTP assíncrono (`app/clients/pi_web_api_client.py`) para comunicação com a PI Web API.

### Funcionalidades Principais

| Função | Endpoint | Descrição |
|--------|----------|-----------|
| `get_point_by_tag(tag)` | `GET /points?path=\\PIMS\{tag}` | Busca PI Point por path |
| `get_recorded_values_by_tag()` | `GET /streams/{webId}/recorded` | Dados históricos brutos |
| `get_interpolated_values_by_tag()` | `GET /streams/{webId}/interpolated` | Dados interpolados |
| `get_summary_values_by_tag()` | `GET /streams/{webId}/summary` | Agregações |
| `buscar_dados_temporais_tag()` | Qualquer endpoint temporal | Dispatcher unificado |
| `get_tags_data(tags)` | `POST /batch` | Batch: metadados + valor + attributes |
| `get_digital_set_states(digital_set)` | Enumeration Sets API | Estados digitais de um Digital Set |
| `get_data_server()` | `GET /dataservers` | Busca data server (cacheado) |
| `get_all_enumeration_sets()` | `GET /enumerationsets` | Lista todos os digital sets |

### Batch Request

O endpoint `/batch` permite buscar metadados + valor atual + attributes de múltiplas tags em uma única chamada:

```python
batch_request = {
    "point_0": {"Method": "GET", "Resource": "/points?path=\\PIMS\\TAG1&selectedFields=..."},
    "value_0": {"Method": "GET", "ParentIds": ["point_0"], "Resource": "/streams/{0}/value"},
    "instrumenttag_0": {"Method": "GET", "ParentIds": ["point_0"],
                        "Resource": "/points/{0}/attributes?name=instrumenttag"},
    # + engunits, pointtype, digitalset, location1..location5
}
POST /batch
```

### Selected Fields

```python
POINT_SELECTED_FIELDS = (
    "WebId;Name;Descriptor;EngineeringUnits;PointType;DigitalSet"
)
```

### Atributos Buscados por Tag

`instrumenttag`, `engunits`, `pointtype`, `digitalset`, `location1` a `location5`

### Caches

- **`_DATASERVER_CACHE`**: cacheia o data server por nome (escopo de processo)
- **`_ENUM_SET_CACHE`**: cacheia digital set states por nome lowercase

### Digital States

Fluxo para consultar estados digitais:
1. Buscar PI Point → ler `DigitalSetName` (via `get_point_by_tag`)
2. Listar Data Servers → encontrar WebId do PIMS (via `get_data_server`, cacheado)
3. Listar Enumeration Sets → encontrar o set com mesmo nome (via `find_enumeration_set`)
4. Consultar Enumeration Values → retorna `{Value, Name, Description}`

### Formatação

`app/utils/pi_response_formatter.py`:
- `format_pi_batch_response()`: parseia batch → lista `resultados_pi` + `mensagem_final`
- `formatar_mensagem_tags()`: gera texto legível com nome, descrição, valor, tipo, locations, digital states

---

## 13. Memória de Conversa

| Parâmetro | Valor |
|---|---|
| Storage | Redis (`REDIS_URL`) |
| TTL | `CHAT_MEMORY_TTL_SECONDS` (default: 604800 = 7 dias) |
| Max turns | `CHAT_MEMORY_MAX_TURNS` (default: 8) |
| Chave Redis | `pi_chat:memory:{conversation_id}:turns` |
| conversation_id | Derivado de `user_id` (não é input do cliente) |

### Fluxo

1. **`_load_memory()`**: `redis.lrange(key, -max_turns, -1)` → lista de `ChatMemoryTurn`
2. **`format_memory_for_prompt()`**: Formata turns como `> Usuário: ... / > Assistente: ...`
3. **`_save_memory()`**: `rpush` user + assistant turn, `ltrim` para max_items (`max_turns * 2`), `expire` com TTL

### Schema

```python
class ChatMemoryTurn(BaseModel):
    role: str           # "user" ou "assistant"
    content: str
    created_at: str     # ISO format, timezone America/Sao_Paulo
    metadata: dict      # { user_id, categoria, next_action, tool_name }
```

### Configuração

- **Timezone padrão**: `America/Sao_Paulo`
- **Prefixo da chave**: `pi_chat:memory`

---

## 14. OCR — Extração de Imagens

Quando o usuário envia imagens no `ChatRequest.images`:

1. **Download de imagens**: `ChatImage.image_base64` (base64 direto, sem download externo)
2. **Extração via LLM**: `litellm.acompletion()` multimodal (uma chamada por imagem)
3. **Saída LLM**: texto extraído + tags encontradas no formato `{texto_ocr: "...", tags: [...]}`
4. **Regex de tags**: `(UTI|ACI|RED|LFS|LFI|CPD|LTQ)(?:_[A-Z0-9_]+)|(SIN|CDT)[A-Z0-9_]+`
5. **Tratamento**: `tratar_saida_ocr()` normaliza e extrai tags
6. **Contexto**: texto OCR é injetado no contexto do agente

### Configuração

- **Imagens**: campos `image_base64` + `mime_type` (default `image/png`) + `file_name`
- **Formatos suportados**: PNG, JPEG, WEBP
- **OCR_LLM_PARAMS**: `num_predict=512`

### Prompt

Sistema e usuário definidos em `app/prompts/ocr_query_prompt.py`.

---

## 15. Schemas e Modelos

### ChatRequest

```python
class ChatRequest(BaseModel):
    message: str = ""                                   # Mensagem do usuário
    user_id: str | None = None                          # ID do usuário
    images: list[ChatImage] = Field(default_factory=list) # Imagens em base64
```

> **Nota**: `conversation_id` **não** é campo do request. É derivado de `user_id`
> no orchestrator: `conversation_id = user_id`.

### ChatImage

```python
class ChatImage(BaseModel):
    image_base64: str = Field(..., min_length=1)
    mime_type: str = "image/png"
    file_name: str | None = None
    image_index: int | None = None
```

### ChatResponse

```python
class ChatResponse(BaseModel):
    ok: bool
    user_id: str | None = None
    message_original: str
    processed_message: str | None = None
    categoria: str | None = None          # "conversa_comum" | "pims"
    next_action: str | None = None        # "general_agent" | "pi_agent" | "orchestrator"
    has_image: bool
    skip_ocr: bool
    ocr_text: str | None = None
    tags_encontradas: list[str] = []      # Tags extraídas via OCR
    tags_consultadas: list[str] = []
    ocr_results: list[OcrResult] = []
    tool_name: str | None = None
    tool_result: dict[str, Any] | None = None
    agent_trace: list[dict[str, Any]] = []
    output: str | None = None             # Resposta final do agente
    answer_generation_error: str | None = None
```

### OcrResult

```python
class OcrResult(BaseModel):
    image_index: int
    file_name: str | None = None
    mime_type: str
    texto_ocr_original: str
    texto_ocr_normalizado: str
    tags_encontradas: list[str] = []
    resultado: str
```

### LLMParams

```python
class LLMParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temperature: float = 0
    num_ctx: int | None = None
    num_predict: int | None = None
    top_k: int | None = None
    top_p: float | None = None
    repeat_penalty: float | None = None
    seed: int | None = None
    format: str | None = None             # Ex: "json" para router
    keep_alive: str | int | None = None   # Ex: "1000h"
    think: bool | None = None             # False para router
    max_tokens: int | None = None
```

### Enums (math_tool.py)

- `StatsOperation`: mean, max, min, sum, count, median, range, variance_population, variance_sample, stddev_population, stddev_sample
- `CalculusOperation`: integral, derivative
- `TemporalDataMethod`: recorded, interpolated, summary
- `SummaryType`: Average, Minimum, Maximum, Range, StdDev, Total, Count
- `CalculationBasis`: TimeWeighted, EventWeighted
- `TimeUnit`: second, minute, hour, none

---

## 16. Variáveis de Ambiente

### App Principal (`app/.env`)

#### Obrigatórias

| Variável | Descrição |
|----------|-----------|
| `GRAFANA_LOKI_QUERY_RANGE_URL` | URL do endpoint query_range do Grafana/Loki |
| `GRAFANA_BEARER_TOKEN` | Token de autenticação do Grafana |

#### LLM

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `LLM_PROVIDER` | `ollama` | Provedor ativo: `groq`, `ollama`, `gemini`, `openai_compatible` |
| `GROQ_API_KEY` | — | Chave API do Groq |
| `GROQ_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Modelo Groq |
| `GEMINI_API_KEY` | — | Chave API do Google Gemini |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modelo Gemini |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL do Ollama |
| `OLLAMA_MODEL` | `gemma4:e4b` | Modelo Ollama |
| `OPENAI_COMPATIBLE_API_KEY` | — | Chave API OpenAI-compatible |
| `OPENAI_COMPATIBLE_BASE_URL` | — | URL base OpenAI-compatible |
| `OPENAI_COMPATIBLE_MODEL` | — | Modelo OpenAI-compatible |

#### PI System

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PI_WEB_API_BASE_URL` | `http://10.247.224.39/piwebapi` | URL base da PI Web API |
| `PI_SERVER_NAME` | `PIMS` | Nome do Data Server |
| `PI_WEB_API_USERNAME` | — | Usuário (opcional) |
| `PI_WEB_API_PASSWORD` | — | Senha (opcional) |
| `PI_WEB_API_VERIFY_SSL` | `false` | Verificar SSL |

#### Grafana / Loki

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PIMS_STATUS_LOKI_QUERY` | `{job="zabbix_proxy"}` | Query Loki |
| `PIMS_STATUS_LOOKBACK_MINUTES` | `20` | Janela de lookback (minutos) |
| `PIMS_STATUS_LIMIT` | `5000` | Limite de linhas |

#### Math Tool

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `MATH_TOOL_BASE_URL` | `http://math_tool:8001` | URL do Math Tool Service |
| `MATH_TOOL_TIMEOUT_SECONDS` | `120` | Timeout em segundos |

#### MCP

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `MCP_SERVER_URL` | `http://localhost:8015/mcp` | URL do MCP Server |

#### Qdrant / RAG

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `QDRANT_URL` | `http://10.247.179.197:6333` | URL do Qdrant |
| `QDRANT_COLLECTION` | `pi_web_api_guide` | Nome da collection |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text-v2-moe` | Modelo de embeddings |

#### Redis / Memória

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `REDIS_URL` | `redis://127.0.0.1:6379/2` | URL do Redis |
| `CHAT_MEMORY_TTL_SECONDS` | `604800` | TTL da memória (7 dias) |
| `CHAT_MEMORY_MAX_TURNS` | `8` | Máximo de turns por conversa |

#### Phoenix / Observabilidade

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PHOENIX_ENABLED` | `false` | Habilitar tracing |
| `PHOENIX_PROJECT_NAME` | `pi-chat-api` | Nome do projeto Phoenix |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006/v1/traces` | Endpoint Phoenix |
| `PHOENIX_PROTOCOL` | `http/protobuf` | Protocolo OTLP |

#### API

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `API_NAME` | `Bot Chat API` | Nome da API |
| `API_PORT` | `8002` | Porta da API |

#### Google Chat Bridge

| Variável | Descrição |
|----------|-----------|
| `GOOGLE_CLOUD_PROJECT` | ID do projeto GCP |
| `GOOGLE_APPLICATION_CREDENTIALS` | Caminho para `chat_secret.json` |
| `GOOGLE_CHAT_SUBSCRIPTION` | Caminho completo da subscription Pub/Sub |
| `GOOGLE_CHAT_SCOPES` | Escopos OAuth |
| `AGENT_INTERNAL_URL` | URL interna do `/chat` |
| `GOOGLE_CHAT_SEND_THINKING_MESSAGE` | Enviar msg "pensando" |
| `GOOGLE_CHAT_THINKING_TEXT` | Texto da msg temporária |
| `GOOGLE_CHAT_DEDUPE_TTL_SECONDS` | TTL da deduplicação |

### MCP Server (`mcp_server/.env`)

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PI_WEB_API_BASE_URL` | `http://10.247.224.39/piwebapi` | URL base PI Web API |
| `PI_SERVER_NAME` | `PIMS` | Nome do Data Server |
| `GRAFANA_LOKI_QUERY_RANGE_URL` | — | URL query_range Loki |
| `GRAFANA_BEARER_TOKEN` | — | Token Grafana |
| `MATH_TOOL_BASE_URL` | `http://math_tool:8001` | URL Math Tool |
| `MATH_TOOL_TIMEOUT_SECONDS` | `120` | Timeout Math Tool |
| `MCP_HOST` | `0.0.0.0` | Host do MCP server |
| `MCP_PORT` | `8003` | Porta do MCP server |

---

## 17. Comandos

### Instalação e Dependências

```bash
poetry install
```

### Rodar o App Principal (porta 8002)

```bash
poetry run uvicorn app.main:app --reload --port 8002
```

### Rodar o MCP Server (porta 8003 local)

```bash
cd mcp_server && poetry run uvicorn server:app --reload --port 8003
# ou
cd mcp_server && python server.py
```

### Rodar o Math Tool (porta 8001)

```bash
cd calc && poetry run uvicorn app.main:app --reload --port 8001
```

### Rodar a Bridge Google Chat

```bash
python -m app.bridge.google_chat.worker --send
```

### Docker Compose (todos os serviços)

```bash
docker-compose up -d
# Serviços: math_tool (8001), mcp_server (8005), agent_bot (8002), agent_bot_chat_bridge
```

### Reingestir Documento RAG

```bash
curl -X DELETE http://10.247.179.197:6333/collections/pi_web_api_guide
poetry run python scripts/ingest_pi_guide.py
```

### Limpar Memória Poluída

```bash
poetry run python scripts/clean_polluted_memory.py
```

### Health Check

```bash
curl http://localhost:8002/health
```

---

## 18. Endpoints e Entrypoints

### HTTP Endpoints (FastAPI, porta 8002)

| Método | Path | Descrição |
|--------|------|-----------|
| `GET` | `/health` | Health check com status dos serviços |
| `POST` | `/chat` | Endpoint principal — recebe `ChatRequest`, retorna `ChatResponse` |

### MCP Endpoints (FastMCP, porta 8005 Docker / 8003 local)

| Protocolo | Path | Descrição |
|-----------|------|-----------|
| Streamable HTTP | `POST /mcp` | Executa tools MCP (consultar_tag, tag_statistics, tag_calculus, status_pims) |

### Math Tool Endpoints (porta 8001)

| Método | Path | Descrição |
|--------|------|-----------|
| `POST` | `/calculate` | Expressão aritmética simples |
| `POST` | `/stats` | Estatísticas sobre lista de valores |
| `POST` | `/calculus` | Integral/derivada temporal |

### Worker Entrypoints

| Comando | Descrição |
|---------|-----------|
| `python -m app.bridge.google_chat.worker --send` | Bridge Google Chat com envio de respostas |

---

## 19. Regras de Negócio

### Names das Tags

- **Sempre** preservar o nome exato da tag informada pelo usuário
- **Nunca** traduzir, abreviar, corrigir ou escape de underscores
- Tags são identificadas por padrão regex específico:

```
(UTI|ACI|RED|LFS|LFI|CPD|LTQ)(?:_[A-Z0-9_]+)|(SIN|CDT)[A-Z0-9_]+
```

- Apenas tags com prefixos `UTI`, `ACI`, `RED`, `LFS`, `LFI`, `CPD`, `LTQ`, `SIN`, `CDT` são reconhecidas pelo extrator automático

### Qualidade de Dados

- Se `Good = false`, não tratar valor como confiável
- Se `Questionable = true`, avisar ao usuário
- Se `Value` vier como objeto, verificar campos internos (`Name`, `Value`)
- Não inventar valores quando dados estiverem indisponíveis

### Consumption Calculation

Para consumo de vazão em Nm3:
1. Usar `summary` com `summaryType=Average`
2. Usar `summaryDuration=1h`
3. Usar `calculationBasis=TimeWeighted`
4. Usar `operation='sum'` para totalizar
5. Cada hora em Nm3/h = 1 Nm3

### Digital States

- Verificar `PointType == "Digital"` e `DigitalSet` válido
- `INVALID_DIGITAL_SETS`: `n/a`, `não cadastrado`, `não se aplica`, `null`, `undefined`, vazio
- Consultar `Enumeration Sets` → `Enumeration Values` para mapear índices
- Estados retornados: `{indice, nome, descricao}`

### Detecção de Loops

- `_detect_repeated_tool_calls()` detecta se a mesma tool (mesma combinação `name + args`) é chamada 3+ vezes
- Se detectado, o agente aborta com mensagem de erro
- `MAX_AGENT_STEPS = 8`: limite máximo de iterações do ADK Runner

### Tratamento de Erros (PI Agent)

- `RecursionError` / `recursion_limit`: "excedeu o número máximo de etapas"
- `RateLimitError` / `429`: "Serviço temporariamente sobrecarregado"
- `AuthenticationError` / `401`: "Chave de API inválida ou expirada"
- `ClosedResourceError` / `Mcp*`: "Conexão com o servidor MCP foi fechada"

### Conversão de Unidades

- `detectar_time_unit()`: detecta unidade temporal a partir do texto do usuário
- `inferir_time_unit_por_unidade()`: infere unidade temporal baseado na unidade de engenharia da tag

### Formato do Google Chat

`app/utils/google_chat_format.py` normaliza markdown para o formato aceito pelo Google Chat (remove `***triple asterisks***`, etc.)

---

## 20. Utilitários

| Arquivo | Função principal |
|---|---|
| `tag_extractor.py` | `extract_tags_from_text()` — regex de tags; `merge_unique_tags()` — merge e deduplica |
| `digital_states.py` | `enricher_com_digital_states()` — busca digital states para tags digitais; `tag_eh_digital()` — verifica se tag é digital |
| `pi_response_formatter.py` | `format_pi_batch_response()` — parseia batch do PI Web API; `formatar_mensagem_tags()` — gera texto formatado com metadados + valor + locations + digital states |
| `math_expression.py` | `limpar_expressao_basica()` — sanitiza expressões aritméticas |
| `math_pi_series.py` | `buscar_serie_pi()` — busca série temporal; `extrair_values()` / `extrair_points()` / `extrair_point_metadata()` — extração de dados |
| `math_time_unit.py` | `detectar_time_unit()` — detecta unidade temporal a partir do texto |
| `math_units.py` | `inferir_time_unit_por_unidade()` — infere time_unit pela eng unit da tag |
| `ocr_treatment.py` | `tratar_saida_ocr()` — normaliza e extrai tags do texto OCR |
| `time_context.py` | Helpers de tempo (resolução de expressões relativas como "ontem", "semana passada") |
| `google_chat_format.py` | Normalização de markdown para Google Chat |

---

## 21. Estrutura de Testes

O diretório `tests/` existe com subdiretórios preparados mas **vazio de arquivos `.py`**:

```
tests/
├── unit/
├── integration/
└── agent/
```

Todos contêm apenas `__pycache__/`. Não há suíte de testes atualmente.

---

## 22. Problemas Comuns

| Problema | Solução |
|----------|---------|
| LLM não responde | Verificar `LLM_PROVIDER`, chave API (`GROQ_API_KEY`, etc.), e se o serviço LLM está acessível |
| Tags não encontradas | Verificar `PI_WEB_API_BASE_URL`, `PI_SERVER_NAME`, e se a tag segue o regex `(UTI\|ACI\|RED\|LFS\|LFI\|CPD\|LTQ\|SIN\|CDT)_...` |
| RAG sem contexto | Verificar Qdrant acessível em `QDRANT_URL`, `QDRANT_COLLECTION=pi_web_api_guide`, reingerir com `scripts/ingest_pi_guide.py` |
| Memória não persiste | Verificar `REDIS_URL`, `CHAT_MEMORY_MAX_TURNS`, e que `conversation_id` = `user_id` |
| OCR falhando | Validar `image_base64` não-vazio e `mime_type` suportado (png/jpeg/webp) |
| Phoenix não aparece | `PHOENIX_ENABLED=true` + endpoint acessível; **atenção**: o SpanProcessor custom DEVE usar `replace_default_processor=False` |
| Math Tool timeout | Verificar `MATH_TOOL_BASE_URL` e `MATH_TOOL_TIMEOUT_SECONDS` (default 120s) |
| MCP server inacessível | Verificar `MCP_SERVER_URL` (porta 8005 Docker / 8015 local default) e se `mcp_server` está rodando |
| Tokens inflados no Phoenix | Confirmar que `phoenix.py` tem `_TokenDedupSpanProcessor` + `replace_default_processor=False` |
| Bridge não recebe mensagens | Verificar credenciais GCP, `GOOGLE_CHAT_SUBSCRIPTION`, `secrets/chat_secret.json` |
| `MAX_AGENT_STEPS=8` atingido | Reformular pergunta; pode indicar prompt vago ou tool com erro |
| Loop de tool calls | Sistema aborta após 3 repetições da mesma chamada (`_detect_repeated_tool_calls`) |
| Erro "ClosedResourceError" | Conexão MCP fechada; reiniciar mcp_server ou retry |

---

## 23. Arquivo de Documentação RAG

O arquivo `PI_WEB_API_AGENT_GUIDE.md` é a fonte de verdade para o RAG. Contém **22 CHUNKs**:

| CHUNK | Conteúdo |
|-------|----------|
| 01 | Fluxo base: tag para WebId |
| 02 | Valor atual de uma tag |
| 03 | Metadados: unidade, descriptor, tipo, span, step |
| 04 | Atributos: instrumenttag, location, atributos clássicos |
| 05 | DigitalSetName e Digital States |
| 06 | Histórico bruto: recorded values |
| 07 | Valores interpolados |
| 08 | Summary: média, mínimo, máximo, total, percent good |
| 09 | Consumo de vazão em Nm3 usando médias horárias |
| 10 | Múltiplas tags: streamsets e batch |
| 11 | Buscar tag quando o nome não é exato |
| 12 | Tratamento de erros e qualidade |
| 13 | Strings de tempo e timezone |
| 14 | Codificação de URL |
| 15 | Respostas finais do agente |
| 16 | Decisão rápida de endpoint |
| 17 | Exemplo Python: valor atual |
| 18 | Exemplo Python: metadados e atributos |
| 19 | Diretrizes de qualidade e anti-padrões |
| 20 | **FIXO** — Seleção de tool e resumo operacional (sempre injetado) |
| 21 | Cálculos temporais: integral e derivada |
| 22 | RAG e recuperação recomendada |

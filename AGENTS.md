# Agent Bot — Guia Completo do Projeto

> Documento atualizado em 2026-06-23. Reflete o estado atual do código-fonte
> após refatoração arquitetural (Etapas 0-8).

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
| 19 | [Regras de Negócio](#19-regras-de-negócio) |
| 20 | [Utilitários](#20-utilitários) |
| 21 | [Estrutura de Testes](#21-estrutura-de-testes) |
| 22 | [Problemas Comuns](#22-problemas-comuns) |
| 23 | [Arquivo de Documentação RAG](#23-arquivo-de-documentação-rag) |
| 24 | [Refatoração Arquitetural (Etapas 0-8)](#24-refatoração-arquitetural-etapas-0-8) |
| 25 | [Arquitetura em Camadas (DDD/CQRS/ES)](#25-arquitetura-em-camadas-dddcqres) |
| 26 | [Domain Layer Detalhado](#26-domain-layer-detalhado) |
| 27 | [Application Layer Detalhado](#27-application-layer-detalhado) |
| 28 | [Infrastructure Layer Detalhado](#28-infrastructure-layer-detalhado) |
| 29 | [ConversationSaga — Fluxo Detalhado](#29-conversationsaga--fluxo-detalhado) |
| 30 | [Ambientes (Local / QA / PRD)](#30-ambientes-local--qa--prd) |
| 31 | [Regras de Negócio Detalhadas](#31-regras-de-negócio-detalhadas) |
| 33 | [PostgreSQL Event Store opcional](#33-postgresql-event-store-opcional) |

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
| Observabilidade | Phoenix (Arize) via OpenTelemetry + SpanExporter customizado |
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
│   │   └── agent.py                    # Agente LLM via Google ADK + McpToolset
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
│   │   ├── agent_prompt.py             # System prompt do agente (com timestamp dinâmico)
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
│       └── phoenix.py                  # Setup Phoenix + _TokenDedupSpanExporter
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
├── PI_WEB_API_AGENT_GUIDE.md           # Fonte RAG (21 CHUNKs)
├── pyproject.toml
├── docker-compose.yaml                 # 4 serviços principais + 1 opcional (profile events)
├── Dockerfile                          # Build do app principal
└── secrets/                            # Credenciais GCP (não versionadas)
```

---

> **Nota arquitetural — pacote `domain/`**:
> O pacote `domain/` raiz funciona hoje como pacote técnico compartilhado, com características de shared kernel, mas ainda contém dívida arquitetural e não deve ser descrito como domínio puro. Veja também a seção 24 e a seção 33.

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
  │     └─→ "pims" → run_agent()
  │           ├─→ build_rag_context()
  │           │     ├─→ CHUNK 01 (fixo, sempre injetado)
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
| **PI Agent** | `agent.py` | 0 | 8192 | 1024 | 0.1 | — |
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
| Documento fonte | `PI_WEB_API_AGENT_GUIDE.md` (21 CHUNKs) |
| Vector Store | Qdrant (`pi_web_api_guide`, 768-dim, cosine) |
| Embeddings | Ollama `nomic-embed-text-v2-moe` (via `POST /api/embed`) |
| Ingestão | `scripts/ingest_pi_guide.py` |
| CHUNK fixo | CHUNK 01 (sempre injetado, excluído do Qdrant) |

### Como funciona

1. O documento é dividido em **21 CHUNKs** por headers (`# CHUNK 01`, `# CHUNK 02`, ..., `# CHUNK 21`)
2. Cada CHUNK (exceto o 01) é embedded e armazenado no Qdrant com metadados (`chunk_number`, `title`, `content`)
3. **CHUNK 01** ("Seleção de tool e resumo operacional") é sempre injetado como contexto fixo
4. A cada query, o texto do usuário é embedded e busca os top-3 chunks mais similares
5. O contexto final = **CHUNK 01** (fixo) + **top-3 chunks** (retrieved)

### Fluxo RAG

```
build_rag_context(query, top_k=3)
  ├─→ _load_fixed_chunk()            ← Lê CHUNK 01 do .md (cached, regex por header)
  ├─→ retrieve_relevant_chunks()     ← Embed query → Qdrant search
  └─→ Retorna string com contexto concatenado
```

### CHUNK 01 — Contexto Fixo

O CHUNK 01 contém o resumo operacional mínimo da PI Web API:
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
Agent (app/agent/agent.py)
  └─→ McpToolset(url=MCP_SERVER_URL)
        └─→ MCP Server (mcp_server/server.py, porta 8005)
              ├─→ consultar_tag()      → services/consultar_tag_service.py
              ├─→ tag_statistics()     → services/math_tool_service.py
              ├─→ tag_calculus()       → services/math_tool_service.py
              └─→ status_pims_tool()  → services/status_pims_service.py
```

### Tools Expostas

| Tool | Parâmetros | Descrição |
|------|-----------|-----------|
| `consultar_tag` | `tags: list[str]`, `pergunta_usuario: str \| None` | Valor atual e metadados de tags |
| `tag_statistics` | `tags, operation, start_time, end_time, data_method, interval, summary_type, summary_duration, calculation_basis, context_text, max_count` | Estatísticas históricas |
| `tag_calculus` | `tags, operation, start_time, end_time, data_method, interval, summary_type, summary_duration, calculation_basis, time_unit, context_text, max_count` | Integralização e derivada |
| `status_pims_tool` | `pergunta_usuario: str \| None`, `lookback_minutes: int \| None` | Status via Grafana/Loki |

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

### _TokenDedupSpanExporter

**SpanExporter customizado** que resolve a duplicação de tokens no Phoenix:

- O Google ADK grava `gen_ai.usage.input_tokens` e `gen_ai.usage.output_tokens` nos spans `call_llm` e `generate_content`
- O openinference-instrumentation-litellm grava `llm.token_count.*` no span `acompletion` (mais profundo)
- O Phoenix UI soma todos os descendentes, inflando o total (3x)

**Solução**: `_TokenDedupSpanExporter` (em `phoenix.py`) remove os atributos de token dos spans ADK (identificados por `gcp.vertex.agent.invocation_id`), preservando-os apenas no `acompletion`.

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

### 11.4 status_pims_tool

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
    next_action: str | None = None        # "general_agent" | "agent" | "orchestrator"
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
poetry --directory mcp_server run python server.py
# ou, a partir da raiz do repo (recomendado)
poetry --directory mcp_server run python mcp_server/server.py
```

> **Nota**: o pacote `domain/` é uma *path dependency* compartilhada. Em Docker ele é
> copiado para `/app/domain/` dentro do WORKDIR, mas em local o Poetry não injeta o
> repositório raiz no `sys.path` automaticamente. Por isso o `server.py` adiciona o
> diretório pai ao `sys.path` ao iniciar.

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
| Streamable HTTP | `POST /mcp` | Executa tools MCP (consultar_tag, tag_statistics, tag_calculus, status_pims_tool) |

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

O projeto possui **317 testes** distribuídos em 7 suites.

### Mapeamento Suite → Arquivo → O que Valida

| Suite | Arquivo | Testes | O que valida |
|---|---|---|---|
| `tests/unit/` | `test_domain.py` | VOs, Enums, Protocols, Errors | Contratos do domain layer |
| `tests/unit/` | `test_events.py` | 23 Domain Events | Imutabilidade, serialização, payload |
| `tests/unit/` | `test_event_store.py` | EventStore InMemory + Redis | Append, replay, stream partitioning |
| `tests/unit/` | `test_projection.py` | ConversationMemoryProjection | Reconstrução de turns a partir de eventos |
| `tests/unit/` | `test_conversation_memory_v2.py` | RedisConversationMemory | Append, replay, max_turns, metadata |
| `tests/unit/` | `test_tag_extractor.py` | Regex de tags + merge | Extração, deduplicação, preservação de underscores |
| `tests/unit/` | `test_qdrant_client.py` | Qdrant RAG client | Embedding, busca, CHUNK 01 fixo |
| `tests/unit/` | `test_ingest_pi_guide.py` | Ingestão RAG | Chunking do documento PI Web API |
| `tests/application/` | `test_commands.py` | 6 Commands + Handlers | Extrair, route, run_agent, retrieve_rag, save_memory, invoke_mcp |
| `tests/application/` | `test_queries.py` | 5 Queries + Handlers | Memory, knowledge, PI tag, historical, PIMS status |
| `tests/application/` | `test_saga.py` | ConversationSaga (6 steps) | Fluxo completo: memory → ocr → route → rag → agent → save |
| `tests/application/` | `test_saga_with_events.py` | Saga + Event Publishing | Cada step publica evento correto |
| `tests/application/` | `test_saga_with_memory_v2.py` | Saga + Event Sourcing memory | Memory v2 com event replay |
| `tests/agent/` | `test_orchestrator_characterization.py` | Orchestrator (state dict) | 28 testes de caracterização (Etapa 0) |
| `tests/infrastructure/` | `test_distributed_lock.py` | DistributedLock (Redis + InMemory) | Acquire, release, TTL, atômico |
| `tests/infrastructure/` | `test_math_tool_client.py` | Math Tool client retry | Retry, timeout, erros retryáveis, API pública |
| `tests/bridge/` | `test_dedupe_store.py` | DedupeStore (Redis + InMemory) | Deduplicação, TTL, DistributedLock |
| `tests/integration/` | `test_integration_orchestrator.py` | Smoke test (@integration) | Orchestrator end-to-end (requer Docker) |

### Comandos

```bash
poetry run pytest tests/ -v                           # Suite completa (317 testes)
poetry run pytest tests/unit/ -v                      # Domain + utilitários
poetry run pytest tests/application/ -v               # Commands + Queries + Saga
poetry run pytest tests/agent/ -v                     # Caracterização orchestrator
poetry run pytest tests/infrastructure/ -v            # Lock + math_tool_client
poetry run pytest tests/bridge/ -v                    # Dedupe store
pytest -m integration                                 # Integração (requer Docker)
```

### Marcadores

| Marcador | Arquivo | Descrição |
|---|---|---|
| `@pytest.mark.integration` | `test_integration_orchestrator.py` | Smoke test end-to-end |

---

## 22. Problemas Comuns

| Problema | Solução |
|----------|---------|
| LLM não responde | Verificar `LLM_PROVIDER`, chave API (`GROQ_API_KEY`, etc.), e se o serviço LLM está acessível |
| Tags não encontradas | Verificar `PI_WEB_API_BASE_URL`, `PI_SERVER_NAME`, e se a tag segue o regex `(UTI\|ACI\|RED\|LFS\|LFI\|CPD\|LTQ\|SIN\|CDT)_...` |
| RAG sem contexto | Verificar Qdrant acessível em `QDRANT_URL`, `QDRANT_COLLECTION=pi_web_api_guide`, reingerir com `scripts/ingest_pi_guide.py` |
| Memória não persiste | Verificar `REDIS_URL`, `CHAT_MEMORY_MAX_TURNS`, e que `conversation_id` = `user_id` |
| OCR falhando | Validar `image_base64` não-vazio e `mime_type` suportado (png/jpeg/webp) |
| Phoenix não aparece | `PHOENIX_ENABLED=true` + endpoint acessível; **atenção**: o SpanExporter custom DEVE usar `replace_default_processor=False` |
| Math Tool timeout | Verificar `MATH_TOOL_BASE_URL` e `MATH_TOOL_TIMEOUT_SECONDS` (default 120s) |
| MCP server inacessível | Verificar `MCP_SERVER_URL` (porta 8005 Docker / 8015 local default) e se `mcp_server` está rodando |
| Tokens inflados no Phoenix | Confirmar que `phoenix.py` tem `_TokenDedupSpanExporter` + `replace_default_processor=False` |
| Bridge não recebe mensagens | Verificar credenciais GCP, `GOOGLE_CHAT_SUBSCRIPTION`, `secrets/chat_secret.json` |
| `MAX_AGENT_STEPS=8` atingido | Reformular pergunta; pode indicar prompt vago ou tool com erro |
| Loop de tool calls | Sistema aborta após 3 repetições da mesma chamada (`_detect_repeated_tool_calls`) |
| Erro "ClosedResourceError" | Conexão MCP fechada; reiniciar mcp_server ou retry |
| Math Tool `[Errno -3] Temporary failure in name resolution` | DNS intermitente no WSL2 para IPs da rede corporativa (`10.247.179.197`). O `math_tool_client` agora faz retry automático (3 tentativas, backoff 0.5/1/2s). Se persistir, verificar `MATH_TOOL_BASE_URL` em `mcp_server/.env` e conectividade de rede. |
| Math Tool `ConnectTimeout` em todo request | **Causa raiz**: `domain/core/config.py` não carrega `.env` e usa o default Docker `http://math_tool:8001` (hostname inacessível fora de Docker). **Correção**: `domain/core/config.py` agora carrega `mcp_server/.env` via `env_file`. Verificar que `MATH_TOOL_BASE_URL` aponta para IP correto no `.env`. |
| Phoenix exibe span órfão `GET` para `http://10.247.179.197:6333` | **Causa**: o `QdrantClient` faz health check no root durante init, e o `HTTPXClientInstrumentor` auto-instrumenta a chamada. **Correção**: `_configure_excluded_urls()` em `app/observability/phoenix.py` define `OTEL_PYTHON_HTTPX_EXCLUDED_URLS` com regex `^<QDRANT_URL>/?$` antes do `register()`. Spans de busca vetorial (`/collections/.../points/search`) permanecem rastreados. |

---

## 23. Arquivo de Documentação RAG

O arquivo `PI_WEB_API_AGENT_GUIDE.md` é a fonte de verdade para o RAG. Contém **21 CHUNKs**:

| CHUNK | Conteúdo |
|-------|----------|
| 01 | **FIXO** — Seleção de tool e resumo operacional (sempre injetado, excluído do Qdrant) |
| 02 | Fluxo base: tag para WebId |
| 03 | Valor atual de uma tag |
| 04 | Metadados: unidade, descriptor, tipo, span, step |
| 05 | Atributos: instrumenttag, location, atributos clássicos |
| 06 | DigitalSetName e Digital States |
| 07 | Histórico bruto: recorded values |
| 08 | Valores interpolados |
| 09 | Summary: média, mínimo, máximo, total, percent good |
| 10 | Consumo de vazão em Nm3 usando médias horárias |
| 11 | Múltiplas tags: streamsets e batch |
| 12 | Buscar tag quando o nome não é exato |
| 13 | Tratamento de erros e qualidade |
| 14 | Strings de tempo e timezone |
| 15 | Codificação de URL |
| 16 | Decisão rápida de endpoint |
| 17 | Exemplo Python: valor atual |
| 18 | Exemplo Python: metadados e atributos |
| 19 | Diretrizes de qualidade e anti-padrões |
| 20 | Cálculos temporais: integral e derivada |
| 21 | RAG e recuperação recomendada |

---

## 24. Refatoração Arquitetural (Etapas 0-8)

O projeto passou por uma refatoração gradual para **DDD + CQRS + Event Publishing** (com Event Log / Event Store preparation em andamento), implementada em 8 etapas incrementais. Cada etapa foi precedida de testes de caracterização e validada com suite completa.

> **Nota arquitetural**: o estado atual do projeto **não é Event Sourcing completo** — o Event Store não é fonte da verdade do estado. O `process_message` ainda instancia `InMemoryEventStore()` literal, sem consumir o factory. Veja a seção 33 para detalhes sobre o Event Store PostgreSQL opcional.

### Etapas executadas

| Etapa | Descrição | Testes |
|---|---|---|
| 0 | Testes de caracterização do orchestrator (`tests/agent/`) | 28 testes |
| 1 | Domain layer (`app/domain/`): VOs, Enums, Protocols, Errors | 46 testes |
| 2 | Application layer (`app/application/`): Commands/Queries + Handlers | 28 testes |
| 3 | ConversationSaga + ConversationContext (substitui state: dict) | 27 testes |
| 4 | Pacote `domain/` compartilhado (resolução de duplicação app ↔ mcp_server) | 0 (validação) |
| 5 | Domain Events (23 eventos) + EventStore (InMemory + Redis Streams) | 25 testes |
| 6 | ChatMemoryTurn → Event Sourcing (ConversationMemoryProjection) | 33 testes |
| 7 | Distributed Lock no DedupeStore (resolução P1 #11) | 35 testes |
| 8 | Polimento: consolidação `_build_completion_kwargs`, testes tag_extractor, AGENTS.md | 10 testes |

### Resultado

- **273+ testes** passando
- **0 duplicações** entre `app/` e `mcp_server/`
- **`domain/`** é pacote compartilhado via Poetry path dependency
- **23 Domain Events** (imutáveis, serializáveis)
- **ConversationSaga** orquestra 6 steps com event publishing
- **DistributedLock** substitui fallback in-memory no DedupeStore
- **10 Bounded Contexts** mapeados (Conversation, PIMS, Analytics, OCR, RAG, PIMS Ops, LLM Provider, MCP Gateway, Google Chat, Observability)

### Estrutura arquitetural atual

```
app/
├── domain/                          # Pacote técnico compartilhado (shared kernel / dívida arquitetural — ver seção 3)
│   ├── enums.py                     # 5 enums de domínio
│   ├── errors.py                    # 3 exceptions de domínio
│   ├── events.py                    # 23 Domain Events (frozen)
│   ├── projections.py               # ConversationMemoryProjection
│   └── value_objects.py             # 6 VOs imutáveis
├── application/                     # Camada de aplicação (orqueta)
│   ├── commands/                    # 6 Commands + Handlers
│   ├── queries/                     # 5 Queries + Handlers
│   └── sagas/                       # ConversationSaga + EventPublisher
├── infrastructure/                  # Camada de infraestrutura
│   ├── event_store/                 # EventStore (InMemory + Redis Streams)
│   ├── locking/                     # DistributedLock (Redis SET NX EX)
│   └── conversation/                # RedisConversationMemory (v2)
├── agent/                           # Orquestração (adaptadores)
│   ├── orchestrator.py              # process_message → Saga
│   ├── shared.py                    # build_completion_kwargs (único)
│   ├── router.py                    # Classificador de intenção
│   ├── general_agent.py             # Agente geral
│   └── agent.py                   # Agente (ADK + MCP)
└── bridge/google_chat/              # Bridge (DistributedLock)
```

### Bounded Contexts mapeados

| # | Bounded Context | Responsabilidade |
|---|---|---|
| 1 | Conversation/Chat | Lifecycle da mensagem, memória, turns |
| 2 | PIMS/Industrial Telemetry | Leitura de tags PI, metadados, digital states |
| 3 | Time-Series Analytics | Estatísticas e cálculos temporais |
| 4 | OCR/Image Understanding | Extração de texto de imagens |
| 5 | RAG/Knowledge Retrieval | Contexto de documentação |
| 6 | PIMS Operations | Status operacional via Grafana/Loki |
| 7 | LLM Provider | Abstração de provedores LLM |
| 8 | MCP Tool Gateway | Interface MCP sobre domínio |
| 9 | Google Chat Integration | ACL entre Chat API e Conversation |
| 10 | Observability | Cross-cutting (Phoenix, OTel) |

### Ubiquitous Language (termos de domínio)

| Termo | Significado |
|---|---|
| **PiTag** | Identificador de ponto industrial (ex: `LFI_RB3_VAZ_GN_TOTAL`) |
| **PiPoint** | Recurso de configuração (WebId, Descriptor, PointType, EngUnits) |
| **TimeWindow** | Par `(start, end)` para consultas temporais |
| **TimeSeriesMethod** | `recorded`, `interpolated`, ou `summary` |
| **AgentRoute** | Classificação: `GeneralChat`, `PiAssistant`, `Calculator` |
| **ConversationTurn** | Par user+assistant armazenado na memória |
| **AgentRun** | Execução do agente PI com tool calls |
| **ToolInvocation** | Chamada de tool pelo agente (name + args) |
| **KnowledgeContext** | CHUNK 01 fixo + top-3 retrieved chunks |
| **OcrExtraction** | Texto extraído + tags de imagem |
| **InboundMessage** | Mensagem recebida (texto + imagens) |
| **OutboundReply** | Resposta gerada pelo agente |
| **MessageDedupeEntry** | Estado de deduplicação de mensagem Google Chat |

### Domain Events (23)

| Evento | Quando é publicado |
|---|---|
| `InboundMessageReceived` | Mensagem recebida |
| `OcrExtractionCompleted` | OCR finalizado |
| `ConversationMemoryLoaded` | Memória carregada |
| `AgentRouteSelected` | Roteamento decidido |
| `RagContextRetrieved` | RAG recuperado |
| `AgentRunStarted` | Execução do agente iniciada |
| `AgentToolInvocationRequested` | Tool chamada |
| `AgentToolInvocationCompleted` | Tool retornou |
| `AgentRunCompleted` | Agente finalizou |
| `AgentRunAborted` | Agente abortado (loop/erro) |
| `PiTagQueried` | Tag consultada |
| `PiHistoricalSeriesRetrieved` | Série temporal recuperada |
| `StatisticsComputed` | Estatísticas calculadas |
| `CalculusComputed` | Calculus calculado |
| `PimsStatusChecked` | Status PIMS verificado |
| `OutboundReplyGenerated` | Resposta gerada |
| `ConversationMemorySaved` | Memória salva |
| `UserMessageRecorded` | Mensagem do usuário registrada (memory v2) |
| `AssistantMessageRecorded` | Resposta do assistente registrada (memory v2) |
| `GoogleChatEventReceived` | Evento Google Chat recebido |
| `GoogleChatDedupeStarted` | Dedupe iniciado |
| `GoogleChatReplySent` | Resposta Google Chat enviada |
| `GoogleChatDedupeCompleted` | Dedupe finalizado |
| `GoogleChatAttachmentDownloaded` | Anexo baixado |
| `MessageProcessingFailed` | Erro no processamento |

### Comandos (CQRS)

| Command | Handler | Descrição |
|---|---|---|
| `ExtractOcr` | `ExtractOcrHandler` | Extrai texto de imagens |
| `RouteMessage` | `RouteMessageHandler` | Classifica intenção |
| `RunAgentForMessage` | `RunAgentForMessageHandler` | Executa agente PI ou geral |
| `RetrieveKnowledgeContext` | `RetrieveKnowledgeContextHandler` | Recupera contexto RAG |
| `SaveConversationTurn` | `SaveConversationTurnHandler` | Salva turn na memória |
| `InvokeMcpTool` | `InvokeMcpToolHandler` | Invoca tool MCP (placeholder) |

### Queries (CQRS)

| Query | Handler | Descrição |
|---|---|---|
| `GetConversationMemory` | `GetConversationMemoryHandler` | Carrega turns da memória |
| `GetKnowledgeContext` | `GetKnowledgeContextHandler` | Recupera contexto RAG |
| `GetPiTagCurrentValue` | `GetPiTagCurrentValueHandler` | Valor atual de tag |
| `GetPiHistoricalSeries` | `GetPiHistoricalSeriesHandler` | Série temporal |
| `GetPimsStatus` | `GetPimsStatusHandler` | Status PIMS |

### DistributedLock (Etapa 7)

O `DedupeStore` da Bridge usa `DistributedLock` em vez de fallback in-memory:
- **RedisDistributedLock**: SET NX EX (acquire) + Lua script (release atômico)
- **InMemoryDistributedLock**: para testes
- **Sem fallback**: Redis indisponível → fail-fast (P1 #11 resolvido)

### Testes

| Suite | Testes | Cobertura |
|---|---|---|
| `tests/agent/` | 28 (caracterização) | Orchestrator: ≥60% |
| `tests/unit/` | 115 (domain, event_store, projection, etc.) | 100% em domain/ |
| `tests/application/` | 76 (commands, queries, saga, events, memory v2) | 100% em application/ |
| `tests/infrastructure/` | 12 (distributed lock) | 100% em locking/ |
| `tests/bridge/` | 10 (dedupe store) | 100% em dedupe |
| `tests/unit/test_tag_extractor.py` | 10 | 100% em tag_extractor |
| `tests/integration/` | 2 (marcados @pytest.mark.integration) | Smoke test |
| **Total** | **273+** | |

### Comandos úteis

```bash
# Rodar todos os testes
poetry run pytest tests/ -v

# Rodar testes de caracterização (Etapa 0)
poetry run pytest tests/agent/ -v

# Rodar testes de domain
poetry run pytest tests/unit/ -v

# Rodar testes de application (commands + queries + saga)
poetry run pytest tests/application/ -v

# Rodar testes de infrastructure
poetry run pytest tests/infrastructure/ -v

# Rodar testes de bridge
poetry run pytest tests/bridge/ -v

# Rodar testes de integração (requer Docker)
pytest -m integration

# Rodar suite completa
poetry run pytest tests/ -v
```

---

## 25. Arquitetura em Camadas (DDD/CQRS/ES)

O projeto segue **Domain-Driven Design** com **CQRS** (Command Query Responsibility Segregation) e **Event Publishing e Event Log / Event Store preparation** para observabilidade e rastreabilidade do ciclo de vida da conversa.

### Diagrama de Camadas

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT LAYER (entrypoints)                 │
│  orchestrator.py · router.py · general_agent.py · agent.py      │
├─────────────────────────────────────────────────────────────┤
│                 APPLICATION LAYER (orquestra)                │
│  commands/ · queries/ · sagas/ · events.py · projections.py │
├─────────────────────────────────────────────────────────────┤
│                INFRASTRUCTURE LAYER (adaptadores)            │
│  event_store/ · locking/ · conversation/ · clients/          │
├─────────────────────────────────────────────────────────────┤
│                  DOMAIN LAYER (parcialmente puro)            │
│                  Ver nota arquitetural na seção 3            │
│  enums.py · value_objects.py · errors.py · events.py         │
│  domain/{pims,analytics,pims_ops,conversation,shared}/       │
└─────────────────────────────────────────────────────────────┘
```

### Regra de Dependência

```
Domain ← Application ← Infrastructure ← Agent
```

- **Domain** não importa nada (puro)
- **Application** importa apenas Domain
- **Infrastructure** importa Domain + Application
- **Agent** importa tudo (entrypoint)

### Bounded Contexts

| # | Contexto | Pacote | Responsabilidade |
|---|---|---|---|
| 1 | Conversation/Chat | `domain/conversation/` | Lifecycle da mensagem, memória, turns |
| 2 | PIMS/Industrial Telemetry | `domain/pims/` | Leitura de tags PI, metadados, digital states |
| 3 | Time-Series Analytics | `domain/analytics/` | Estatísticas e cálculos temporais |
| 4 | OCR/Image Understanding | `app/tasks/` | Extração de texto de imagens |
| 5 | RAG/Knowledge Retrieval | `app/clients/qdrant_client.py` | Contexto de documentação |
| 6 | PIMS Operations | `domain/pims_ops/` | Status operacional via Grafana/Loki |
| 7 | LLM Provider | `app/clients/provider_client.py` | Abstração de provedores LLM |
| 8 | MCP Tool Gateway | `mcp_server/` | Interface MCP sobre domínio |
| 9 | Google Chat Integration | `app/bridge/` | ACL entre Chat API e Conversation |
| 10 | Observability | `app/observability/` | Cross-cutting (Phoenix, OTel) |

---

## 26. Domain Layer Detalhado

### Enums (`app/domain/enums.py`)

| Enum | Valores | Uso |
|---|---|---|
| `PointType` | `DIGITAL`, `ANALOG`, `STRING` | Tipo do PI Point |
| `TemporalDataMethod` | `RECORDED`, `INTERPOLATED`, `SUMMARY` | Método de busca temporal |
| `CalculusOperation` | `INTEGRAL`, `DERIVATIVE` | Operações de cálculo temporal |
| `StatisticalOperation` | `MEAN`, `MAX`, `MIN`, `SUM`, `COUNT`, `MEDIAN`, `RANGE`, `VARIANCE_POPULATION`, `VARIANCE_SAMPLE`, `STDDEV_POPULATION`, `STDDEV_SAMPLE` | Operações estatísticas |
| `AgentRoute` | `GENERAL_CHAT`, `CALCULATOR`, `PIMS` | Roteamento de intenção |

### Value Objects (`app/domain/value_objects.py`)

| VO | Tipo | Invariantes | Uso |
|---|---|---|---|
| `PiWebId` | `str` | Não-vazio | WebId do PI Web API |
| `EngineeringUnit` | `str` | Pode ser None | Unidade de engenharia (Nm3/h, °C) |
| `TimeWindow` | `(start, end)` | Ambos required, strings | Janela temporal para queries |
| `TimeUnit` | `TimeUnitValue` | `second`, `minute`, `hour`, `none` | Unidade temporal do cálculo |
| `SummaryType` | `SummaryTypeValue` | `Average`, `Minimum`, `Maximum`, `Range`, `StdDev`, `Total`, `Count` | Tipo de agregação |
| `CalculationBasis` | `CalculationBasisValue` | `TimeWeighted`, `EventWeighted` | Base de cálculo |

### Domain Errors (`app/domain/errors.py`)

| Exceção | Quando Levantada |
|---|---|
| `DomainError` | Base para todas as exceções de domínio |
| `TagNotFoundError` | PI tag não existe no servidor |
| `InvalidTimeWindowError` | Janela temporal inválida ou inconsistente |
| `MathToolTimeoutError` | Math Tool não respondeu dentro do timeout |

### Domain Events (`app/domain/events.py`)

23 eventos imutáveis (frozen dataclasses) com `event_id` (UUID), `occurred_at` (UTC), `conversation_id` (partição do stream).

| Evento | Payload Principal | Quando Publicado |
|---|---|---|
| `InboundMessageReceived` | `message_id`, `user_id`, `text`, `has_images` | Mensagem recebida |
| `OcrExtractionCompleted` | `image_count`, `tags_found`, `total_text_length` | OCR finalizado |
| `ConversationMemoryLoaded` | `turns_count`, `max_turns` | Memória carregada |
| `AgentRouteSelected` | `message_id`, `route`, `latency_ms` | Roteamento decidido |
| `RagContextRetrieved` | `query_length`, `chunks_retrieved`, `fixed_chunk_included` | RAG recuperado |
| `AgentRunStarted` | `run_id`, `agent_type`, `route` | Execução do agente iniciada |
| `AgentToolInvocationRequested` | `run_id`, `tool_name`, `args_keys` | Tool chamada |
| `AgentToolInvocationCompleted` | `run_id`, `tool_name`, `success`, `latency_ms` | Tool retornou |
| `AgentRunCompleted` | `run_id`, `output_length`, `total_tool_calls`, `total_steps` | Agente finalizou |
| `AgentRunAborted` | `run_id`, `reason`, `step_count` | Agente abortado (loop/erro) |
| `PiTagQueried` | `tag`, `web_id`, `point_type`, `eng_unit` | Tag consultada |
| `PiHistoricalSeriesRetrieved` | `tag`, `method`, `points_count` | Série temporal recuperada |
| `StatisticsComputed` | `tag`, `operation`, `result_value` | Estatísticas calculadas |
| `CalculusComputed` | `tag`, `operation`, `time_unit`, `result_value` | Calculus calculado |
| `PimsStatusChecked` | `total_logs`, `errors_count`, `warnings_count` | Status PIMS verificado |
| `OutboundReplyGenerated` | `message_id`, `output_length`, `route` | Resposta gerada |
| `ConversationMemorySaved` | `user_turn_saved`, `assistant_turn_saved`, `total_turns` | Memória salva |
| `GoogleChatEventReceived` | `external_event_id`, `space`, `has_attachments` | Evento Google Chat recebido |
| `GoogleChatDedupeStarted` | `external_event_id`, `ttl_seconds` | Dedupe iniciado |
| `GoogleChatReplySent` | `external_event_id`, `space`, `latency_ms` | Resposta Google Chat enviada |
| `GoogleChatDedupeCompleted` | `external_event_id`, `duration_ms` | Dedupe finalizado |
| `MessageProcessingFailed` | `message_id`, `error_class`, `error_message`, `stage` | Erro no processamento |
| `GoogleChatAttachmentDownloaded` | `external_event_id`, `attachment_name`, `mime_type` | Anexo baixado |

### Projections (`app/domain/projections.py`)

`ConversationMemoryProjection` reconstrói a lista de `ConversationTurn` a partir do EventStore. Cada turn é um dataclass `frozen` com `role`, `content`, `created_at`, `metadata`.

### domain/ Compartilhado

O pacote `domain/` na raiz do repo é compartilhado entre `app/` e `mcp_server/` via Poetry path dependency:

```
domain/
├── core/           config.py (Settings centralizado)
├── pims/           clients/, services/, utils/ (PI Web API)
├── analytics/      clients/, services/, utils/ (Math Tool)
├── pims_ops/       clients/, services/ (Grafana/Loki)
├── conversation/   clients/ (Redis)
└── shared/         schemas/ (math_tool.py)
```

---

## 27. Application Layer Detalhado

### Commands (`app/application/commands/`)

| Command | Handler | Input | Output | Side Effects |
|---|---|---|---|---|
| `ExtractOcr` | `ExtractOcrHandler` | `images`, `user_id` | `ocr_text`, `tags` | LitLLM call |
| `RouteMessage` | `RouteMessageHandler` | `message`, `memory` | `route` (str) | LiteLLM call |
| `RunAgentForMessage` | `RunAgentForMessageHandler` | `route`, `context`, `rag` | `agent_output`, `tool_name` | ADK Runner |
| `RetrieveKnowledgeContext` | `RetrieveKnowledgeContextHandler` | `query`, `top_k` | `knowledge_context` | Qdrant search |
| `SaveConversationTurn` | `SaveConversationTurnHandler` | `user_msg`, `assistant_msg` | `None` | append em `ConversationMemory` (abstrai backend de memória) |
| `InvokeMcpTool` | `InvokeMcpToolHandler` | `tool_name`, `args` | `result` | HTTP POST MCP |

### Queries (`app/application/queries/`)

| Query | Handler | Output |
|---|---|---|
| `GetConversationMemory` | `GetConversationMemoryHandler` | `list[ConversationTurn]` |
| `GetKnowledgeContext` | `GetKnowledgeContextHandler` | `str` (contexto RAG) |
| `GetPiTagCurrentValue` | `GetPiTagCurrentValueHandler` | `dict` (valor + metadados) |
| `GetPiHistoricalSeries` | `GetPiHistoricalSeriesHandler` | `dict` (série temporal) |
| `GetPimsStatus` | `GetPimsStatusHandler` | `dict` (resumo status) |

### EventPublisher (`app/application/sagas/event_publisher.py`)

- `EventPublisherImpl`: delega para o `EventStore` configurado (chama `append` no stream).
- `NullEventPublisher`: implementação no-op, usada quando a publicação de eventos está desabilitada.

> **Nota**: o estado real **não** inclui `InMemoryEventPublisher` nem `RedisStreamsEventPublisher`. A publicação é feita via `EventPublisherImpl` sobre qualquer `EventStore` (memory, redis_streams, ou postgres).

---

## 28. Infrastructure Layer Detalhado

### EventStore (`app/infrastructure/event_store/`)

| Implementação | Armazenamento | Uso |
|---|---|---|
| `InMemoryEventStore` | `dict[str, list[DomainEvent]]` | Testes unitários |
| `RedisStreamsEventStore` | Redis Streams (`XADD`/`XRANGE`) | Produção |

**Protocol**: `append(stream, event)`, `read(stream, from_id)`, `append_batch(stream, events)`. Não há `replay`/`replay_all` na interface atual.

### DistributedLock (`app/infrastructure/locking/`)

| Implementação | Mecanismo | Uso |
|---|---|---|
| `RedisDistributedLock` | `SET NX EX` + Lua script (release atômico) | Produção |
| `InMemoryDistributedLock` | `threading.Lock` | Testes |

**Protocol**: `acquire(name, ttl) -> bool`, `release(name)`.

### RedisConversationMemory v2 (`app/infrastructure/conversation/`)

Usa Event Log / memória baseada em eventos: cada turn é registrado como evento de memória (`UserMessageRecorded`, `AssistantMessageRecorded`), mas isso ainda não caracteriza Event Sourcing completo do sistema. A projeção (`ConversationMemoryProjection`) pode reconstruir os turns quando ativada.

**Chave Redis**: `pi_chat:memory:{conversation_id}:turns`
**TTL**: `CHAT_MEMORY_TTL_SECONDS` (default 7 dias)
**Max turns**: `CHAT_MEMORY_MAX_TURNS` (default 8)

---

## 29. ConversationSaga — Fluxo Detalhado

### Diagrama

```
POST /chat
    │
    ▼
┌─ ConversationContext (frozen) ─────────────────────────────┐
│                                                            │
│  Step 1: load_memory                                       │
│    ├─ Redis: lrange pi_chat:memory:{user_id}:turns         │
│    ├─ Event: ConversationMemoryLoaded                      │
│    └─ ctx.memory_turns, ctx.memory_context                 │
│                                                            │
│  Step 2: extract_ocr (se há images)                        │
│    ├─ LiteLLM: acompletion() multimodal (1 por imagem)     │
│    ├─ Event: OcrExtractionCompleted                        │
│    └─ ctx.ocr_text, ctx.ocr_extractions, ctx.tags          │
│                                                            │
│  Step 3: route                                             │
│    ├─ LiteLLM: acompletion(format=json, num_predict=128)   │
│    ├─ Event: AgentRouteSelected                            │
│    └─ ctx.agent_route ("pims" | "conversa_comum")          │
│                                                            │
│  Step 4: retrieve_rag (se route=pims)                      │
│    ├─ Qdrant: top-3 chunks + CHUNK 01 fixo                 │
│    ├─ Event: RagContextRetrieved                            │
│    └─ ctx.knowledge_context                                │
│                                                            │
│  Step 5: run_agent                                         │
│    ├─ route=pims → run_agent() (ADK + McpToolset)            │
│    ├─ route=conversa_comum → run_general_agent() (LiteLLM) │
│    ├─ Event: AgentRunStarted → AgentToolInvocation* →       │
│    │          AgentRunCompleted                             │
│    └─ ctx.agent_output, ctx.tool_name                      │
│                                                            │
│  Step 6: save_memory (SEMPRE, mesmo em erro)               │
│    ├─ Redis: rpush + ltrim + expire                        │
│    ├─ Event: ConversationMemorySaved                       │
│    └─ ctx.user_turn_saved, ctx.assistant_turn_saved        │
│                                                            │
└────────────────────────────────────────────────────────────┘
    │
    ▼
ChatResponse
```

### ConversationContext (7 subcontexts, ~18 campos totais)

```python
@dataclass(frozen=True)
class ConversationContext:
    # Identifiers
    user_id: str | None
    conversation_id: str | None
    # Input
    message_original: str
    images: list
    # OCR
    ocr_text: str | None
    ocr_extractions: list
    tags_encontradas: list[str]
    skip_ocr: bool
    # Memory
    memory_turns: list
    memory_context: str | None
    # Routing
    agent_route: str | None
    # RAG
    knowledge_context: str
    # Agent
    agent_output: str | None
    agent_error: str | None
    agent_messages: list[dict]
    tool_name: str | None
    # Error state
    error: str | None
```

### Backward Compatibility

O `orchestrator.py` mantém stubs deprecated que usam `state: dict` para compatibilidade com testes de caracterização (Etapa 0). O fluxo real usa a Saga.

---

## 30. Ambientes (Local / QA / PRD)

### Tabela Comparativa

| Aspecto | Local (dev) | QA (Poetry) | PRD (Docker) |
|---|---|---|---|
| **app** | `uvicorn app.main:app --port 8002` (default `Settings.API_PORT`) | `uvicorn app.main:app --port 8002` | Container `agent_bot` (8002) |
| **mcp_server** | `python mcp_server/server.py` (8015) | `python mcp_server/server.py` (8015) | Container `mcp_server` (8005) |
| **math_tool** | `cd calc && uvicorn app.main:app --port 8001` | `cd calc && uvicorn app.main:app --port 8001` | Container `math_tool` (8001) |
| **MCP_SERVER_URL** | `http://localhost:8015/mcp` | `http://localhost:8015/mcp` | `http://mcp_server:8005/mcp` |
| **MATH_TOOL_BASE_URL** | `http://10.247.179.197:8001` (via .env) | `http://10.247.179.197:8001` (via .env) | `http://math_tool:8001` (docker-compose) |
| **OLLAMA_BASE_URL** | `http://10.247.179.197:11434` | `http://10.247.179.197:11434` | `http://10.247.179.197:11434` |
| **PI_WEB_API_BASE_URL** | `http://10.247.224.39/piwebapi` | `http://10.247.224.39/piwebapi` | `http://10.247.224.39/piwebapi` |
| **REDIS_URL** | `redis://10.247.179.197:6379/2` | `redis://10.247.179.197:6379/2` | `redis://10.247.197:6379/2` |
| **QDRANT_URL** | `http://10.247.179.197:6333` | `http://10.247.179.197:6333` | `http://10.247.179.197:6333` |
| **PHOENIX** | `http://10.247.179.197:6006` | `http://10.247.179.197:6006` | `http://10.247.179.197:6006` |

### Como Rodar Cada Ambiente

```bash
# === LOCAL (desenvolvimento) ===
# Terminal 1: Math Tool
cd calc && poetry run uvicorn app.main:app --reload --port 8001

# Terminal 2: MCP Server
cd mcp_server && poetry run python server.py  # porta 8015

# Terminal 3: App principal
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8002

# === QA (validação) ===
# O mesmo que Local, mas usando porta 8002 para o app

# === PRD (produção) ===
docker-compose up -d
# Serviços: math_tool (8001), mcp_server (8005), agent_bot (8002), agent_bot_chat_bridge
```

### Notas sobre portas MCP

- Em ambiente **Local QA**: `MCP_SERVER_URL=http://localhost:8015/mcp` (definido em `app/.env:62`); `MCP_PORT=8015` (definido em `mcp_server/.env:37`).
- Em ambiente **PRD/Docker**: `MCP_PORT=8005` e `MCP_SERVER_URL=http://mcp_server:8005/mcp` (definidos em `docker-compose.yaml:27,47`).
- Referências a `MCP_PORT=8003` em `mcp_server/.env.local.example:8` são **template legado** e devem ser tratadas como dívida de configuração, não como recomendação ativa.

### Configuração por Ambiente

- **Local/QA**: `mcp_server/.env` define `MATH_TOOL_BASE_URL=http://10.247.179.197:8001`
- **PRD**: `docker-compose.yaml` sobrescreve com `MATH_TOOL_BASE_URL=http://math_tool:8001`
- **domain/core/config.py**: carrega `mcp_server/.env` via `env_file` (funciona em Local/QA; em PRD, env vars do docker-compose sobrescrevem)

### Startup Check do MCP Server

Ao iniciar, o `mcp_server` faz um probe HTTP não-bloqueante ao Math Tool:
```
2026-06-23 [INFO] mcp_server: Starting MCP Server on 0.0.0.0:8015 (Math Tool: http://10.247.179.197:8001)
2026-06-23 [INFO] core.startup_checks: Math Tool health check OK — http://10.247.179.197:8001 responded with HTTP 404
```

---

## 31. Regras de Negócio Detalhadas

### Regex de Tags

```python
TAG_REGEX = r"(UTI|ACI|RED|LFS|LFI|CPD|LTQ)(?:_[A-Z0-9_]+)|(SIN|CDT)[A-Z0-9_]+"
```

**Exemplos positivos**: `LFI_RB3_VAZ_GN_TOTAL`, `ACI_001_TEMP`, `SIN12345`, `CDT_ABC`

**Exemplos negativos**: `MINHA_TAG` (prefixo inválido), `Lfi_rb3` (case-insensitive aceita), `_LFI_` (precisa de pelo menos 1 char após underscore)

### Consumo de Vazão em Nm3

Para calcular consumo de vazão (Nm3):

1. Usar `data_method='summary'`
2. Usar `summary_type='Average'`
3. Usar `summary_duration='1h'`
4. Usar `calculation_basis='TimeWeighted'`
5. Usar `operation='sum'` para totalizar
6. Cada hora em Nm3/h = 1 Nm3 (média horária × 1h)

**Exemplo**: tag `LFI_RB3_VAZ_GN_TOTAL` com unit `Nm3/h`, período 1 mês:
```
consumo_total = sum(médias_horárias) × 1h = X Nm3
```

### Digital States

Fluxo completo:
1. Buscar PI Point → ler `PointType` e `DigitalSetName`
2. Se `PointType == "Digital"` e `DigitalSet` válido:
   a. Listar Data Servers → encontrar WebId do PIMS (cacheado)
   b. Listar Enumeration Sets → encontrar o set com mesmo nome
   c. Consultar Enumeration Values → retorna `{Value, Name, Description}`
3. Estados retornados: `{indice, nome, descricao}`

**`INVALID_DIGITAL_SETS`**: `n/a`, `não cadastrado`, `não se aplica`, `null`, `undefined`, vazio

### Detecção de Loops

O `_detect_repeated_tool_calls()` verifica se a mesma tool (mesma combinação `name + args`) é chamada 3+ vezes. Se detectado, aborta com mensagem de erro.

**`MAX_AGENT_STEPS = 8`**: limite máximo de iterações do ADK Runner.

### Tratamento de Erros do PI Agent

| Erro | Mensagem |
|---|---|
| `RecursionError` / `recursion_limit` | "excedeu o número máximo de etapas" |
| `RateLimitError` / `429` | "Serviço temporariamente sobrecarregado" |
| `AuthenticationError` / `401` | "Chave de API inválida ou expirada" |
| `ClosedResourceError` / `Mcp*` | "Conexão com o servidor MCP foi fechada" |

### Conversão de Unidades

- **`detectar_time_unit()`**: detecta unidade temporal a partir do texto do usuário
- **`inferir_time_unit_por_unidade()`**: infere time_unit pela unidade de engenharia da tag (Nm3/h → hour, kg/s → second)

### Formato Google Chat

`app/utils/google_chat_format.py` normaliza markdown para o formato Google Chat:
- Remove `***triple asterisks***`
- Converte listas markdown para bullets
- Limita tamanho de mensagens (4096 chars)

---

## 33. PostgreSQL Event Store opcional

Esta seção documenta o estado real do **PostgresEventStore** como backend opcional nesta fase. Não é backend padrão, e o fluxo principal atual **não** o consome.

- `PostgresEventStore` existe em `app/infrastructure/event_store/postgres_event_store.py` e é instanciável sem abrir conexão (pool asyncpg é lazy).
- É **backend opcional** — não é backend padrão obrigatório. O backend padrão é `InMemoryEventStore` (em memória).
- `factory.get_event_store()` pode selecionar `postgres` via env var `EVENT_STORE_BACKEND=postgres` + `EVENT_STORE_POSTGRES_DSN`. Sem o DSN, levanta `ValueError`.
- `process_message` (`app/agent/orchestrator.py:209`) instancia `InMemoryEventStore()` **diretamente**, sem consumir o factory. A env var `EVENT_STORE_BACKEND` não tem efeito no `/chat` hoje.
- Não há teste contra Postgres real nesta fase. O arquivo `tests/unit/test_postgres_event_store.py` é 100% unitário (sem rede, sem Docker, sem testcontainers).
- O DDL append-only está em `app/infrastructure/event_store/sql/001_create_event_store_events.sql`. Aplicação do schema é externa ao código.
- O serviço `event_store_postgres` no `docker-compose.yaml` está sob `profiles: [events]` e não sobe por padrão.

### Dívidas de configuração relacionadas

- **4 Settings coexistentes** em módulos diferentes: `app/core/config.py`, `mcp_server/core/config.py`, `app/bridge/google_chat/config.py`, `domain/core/config.py`. Dívida de configuração/boundary a ser consolidada futuramente.
- `mcp_server/.env.local.example:8` (`MCP_PORT=8003`) é template obsoleto; o `.env` real usa `8015`.
- Testes pré-existentes em `tests/unit/test_event_store_in_memory_v2.py` falham por usarem interface v2 (`append_to_stream`/`load_stream`/`load_by_*`) que não existe no `InMemoryEventStore` atual. Pré-existente, fora do escopo desta task.

> **Não é Event Sourcing completo**: o Event Store ainda não é fonte da verdade do estado. Veja seção 24.

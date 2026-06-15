# Agent Bot — Guia Completo do Projeto

## 1. Visão Geral

O **Agent Bot** é uma API conversacional inteligente construída com FastAPI que atua como um agente especializado em consultas ao **PI System** (PIMS) via **PI Web API**. O sistema interpreta perguntas em linguagem natural, rota automaticamente para o agente correto, recupera contexto via **RAG** (Retrieval-Augmented Generation) de documentação técnica, e executa tools especializadas para retornar dados reais de tags industriais.

### Domínio de Atuação
- Consulta de valores atuais de tags do PI System
- Consulta de metadados (descrição, unidade, tipo, digital set, instrumenttag, locations)
- Estatísticas históricas (média, máximo, mínimo, soma, desvio padrão, consumo)
- Cálculos temporais (integralização, derivada, taxa de variação)
- Consulta de digital states e digital sets
- Status operacional do PIMS via logs Grafana/Loki

---

## 2. Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Framework | FastAPI |
| LLM | Groq (padrão), com suporte a Ollama, Gemini, OpenAI-compatible |
| Agent Framework | LangChain (`create_agent`) |
| Vector Store | Qdrant (RAG para documentação PI Web API) |
| Embeddings | Ollama `nomic-embed-text-v2-moe` (768-dim) |
| Memória de Conversa | Redis |
| Observabilidade | Phoenix (Arize) via OpenTelemetry |
| Background Tasks | OCR para extração de texto de imagens |
| Containerização | Docker Compose |

---

## 3. Arquitetura

```
app/
├── main.py                          # FastAPI entrypoint, /chat e /health
├── core/
│   └── config.py                    # Pydantic Settings (carrega .env)
├── agent/
│   ├── orchestrator.py              # Orquestrador principal: roteamento → RAG → agente → memória
│   ├── router.py                    # Classificador de intenção via LLM
│   ├── general_agent.py             # Agente de conversa geral
│   ├── pi_agent.py                  # Agente especializado em PI System
│   ├── calculator_agent.py          # Agente de cálculos (desativado)
│   └── tools_registry.py            # Registro de tools por agente
├── clients/
│   ├── provider_client.py           # Factory de LLMs (Groq, Ollama, Gemini, OpenAI)
│   ├── qdrant_client.py             # Cliente RAG: busca semântica + Chunk 20 fixo
│   ├── pi_web_api_client.py         # Cliente HTTP para PI Web API (batch, streams, enumeration)
│   ├── redis_client.py              # Cliente Redis (memória de conversa)
│   ├── grafana_loki_client.py       # Cliente Grafana/Loki (logs operacionais)
│   └── math_tool_client.py          # Cliente HTTP para Math Tool Service
├── tools/
│   ├── consultar_tag.py             # Tool: valor atual e metadados de tags
│   ├── tag_statistics.py            # Tool: estatísticas históricas
│   ├── tag_calculus.py              # Tool: integralização e derivada
│   ├── status_pims.py               # Tool: status operacional via Grafana/Loki
│   └── calculator.py                # Tool: calculadora (desativada)
├── services/
│   ├── consultar_tag_service.py     # Lógica de consulta de tags (batch + formatação)
│   ├── math_tool_service.py         # Lógica de estatísticas e cálculos
│   ├── status_pims_service.py       # Lógica de consulta de logs PIMS
│   └── chat_memory_service.py       # Lógica de memória Redis
├── schemas/
│   ├── chat.py                      # Modelos ChatRequest e ChatResponse
│   ├── llm.py                       # Modelo LLMParams + defaults
│   └── math_tool.py                 # Enums: StatsOperation, CalculusOperation, etc.
├── prompts/
│   ├── pi_agent_prompt.py           # System prompt do agente PI
│   ├── router_prompt.py             # Prompt de classificação de rota
│   ├── general_agent_prompt.py      # Prompt do agente de conversa geral
│   └── math_tool_parser_prompt.py   # Prompt de parsing de cálculos
├── tasks/
│   └── ocr_query.py                 # OCR de imagens via LLM
├── utils/
│   ├── math.py                      # Helpers matemáticos
│   ├── time.py                      # Helpers de tempo
│   ├── formatting.py                # Helpers de formatação
│   └── google_chat_format.py        # Normalização de markdown para Google Chat
└── observability/
    └── phoenix.py                   # Setup de tracing Phoenix
```

---

## 4. Fluxo Principal (Request Lifecycle)

```
POST /chat
  │
  ▼
process_message(ChatRequest)
  │
  ├─→ Extrair: message, images, user_id, conversation_id
  │
  ├─→ _load_memory()              ← Redis: carrega turns anteriores
  │
  ├─→ _ocr_step()                 ← Se houver imagens, extrai texto via LLM
  │
  ├─→ build_router_message()      ← Monta texto para classificação
  │
  ├─→ route_message()             ← LLM classifica: "conversa_comum" ou "pims"
  │
  ├─→ _run_selected_agent()
  │     │
  │     ├─→ "conversa_comum" → _run_general_route()
  │     │     └─→ run_general_agent(llm, message)
  │     │
  │     └─→ "pims" → _run_pims_route()
  │           ├─→ build_rag_context()    ← RAG: Chunk 20 + top-3 chunks do Qdrant
  │           ├─→ Enriquecer mensagem com contexto RAG
  │           └─→ run_pi_agent(llm, enriched_message)
  │                 └─→ create_agent(tools, system_prompt) → ainvoke()
  │
  ├─→ _save_memory()              ← Redis: salva turn atual
  │
  └─→ ChatResponse
```

---

## 5. LLM Provider

O sistema suporta múltiplos provedores LLM, configuráveis via `LLM_PROVIDER` no `.env`:

| Provider | Config | Biblioteca |
|----------|--------|-----------|
| `groq` | `GROQ_API_KEY`, `GROQ_MODEL` | `langchain_groq` |
| `ollama` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | `langchain_ollama` |
| `gemini` | `GEMINI_API_KEY`, `GEMINI_MODEL` | `langchain_google_genai` |
| `openai_compatible` | `OPENAI_COMPATIBLE_API_KEY`, `_BASE_URL`, `_MODEL` | `langchain_openai` |

**Factory**: `app/clients/provider_client.py` → `get_llm(params)` retorna um `BaseChatModel`.

Cada rota do agente usa `LLMParams` diferentes:
- **Router**: `temperature=0, num_predict=512`
- **Agent (geral/pims)**: `temperature=0, num_predict=1024`

---

## 6. RAG — Retrieval-Augmented Generation

### Componentes
- **Documento fonte**: `PI_WEB_API_AGENT_GUIDE.md` (1824 linhas, 20 CHUNKs)
- **Vector Store**: Qdrant (`pi_web_api_guide` collection, 768-dim, cosine)
- **Embeddings**: Ollama `nomic-embed-text-v2-moe`
- **Ingestão**: `scripts/ingest_pi_guide.py`

### Como funciona
1. O documento é dividido em **CHUNKs** por headers (`# CHUNK 01`, `# CHUNK 02`, etc.)
2. Cada CHUNK é embedded e armazenado no Qdrant com metadados (`chunk_number`, `title`, `content`)
3. **CHUNK 20** é excluído do Qdrant — é um chunk fixo sempre injetado no contexto
4. A cada query, o texto do usuário é embedded e busca os top-3 chunks mais similares
5. O contexto final = **CHUNK 20** (fixo) + **top-3 chunks** (retrieved)

### Fluxo RAG
```
build_rag_context(query, top_k=3)
  ├─→ _load_chunk_20()              ← Lê CHUNK 20 do .md (cached)
  ├─→ retrieve_relevant_chunks()    ← Embed query → Qdrant search
  └─→ Retorna string com contexto concatenado
```

### CHUNK 20 — Contexto Fixo
O CHUNK 20 contém o resumo operacional mínimo da PI Web API:
- Fluxo de 2 passos: path → WebId → stream endpoints
- Lista de campos importantes (WebId, Name, Descriptor, PointType, etc.)
- Todos os endpoints de stream (value, recorded, interpolated, summary)

### Ingestão
```bash
# Deletar collection antiga e reingestir
curl -X DELETE http://10.247.179.197:6333/collections/pi_web_api_guide
poetry run python scripts/ingest_pi_guide.py
```

---

## 7. Tools do Agente PI

### 7.1 consultar_tag_tool
**Propósito**: Consulta valor atual e metadados de tags do PI System.

**Parâmetros**:
- `tags`: Lista de nomes de tags (preservar exatamente)
- `pergunta_usuario`: Pergunta original (opcional)

**Retorna**: Valor atual, descriptor, unidade, tipo, digital set, instrumenttag, locations.

**Fluxo interno**:
1. Monta batch request com `/points?path=...` + `/streams/{webId}/value` + attributes
2. Executa batch via `POST /batch`
3. Formata resposta com metadados + valor

### 7.2 tag_statistics_tool
**Propósito**: Estatísticas históricas (média, máximo, mínimo, soma, contagem, mediana, amplitude, variância, desvio padrão, consumo total).

**Parâmetros**:
- `tags`: Lista de tags
- `operation`: Operação estatística final (mean, max, min, sum, count, etc.)
- `start_time`, `end_time`: Período
- `data_method`: `recorded`, `interpolated` ou `summary`
- `interval`: Para `interpolated` (ex: `1m`, `5m`, `1h`)
- `summary_type`, `summary_duration`, `calculation_basis`: Para `summary`
- `context_text`: Pergunta original
- `max_count`: Limite de valores (recorded)

**Fluxo interno**:
1. Busca dados temporais via PI Web API (`buscar_dados_temporais_tag`)
2. Envia dados para Math Tool Service (`/stats`)
3. Retorna resultado formatado

### 7.3 tag_calculus_tool
**Propósito**: Integralização e derivada temporal.

**Parâmetros**:
- `tags`, `start_time`, `end_time`, `data_method`, `interval`, `summary_type`, `summary_duration`, `calculation_basis`: Idênticos ao statistics
- `operation`: `integral` ou `derivative`
- `time_unit`: Unidade temporal do cálculo final (`second`, `minute`, `hour`, `none`)

**Fluxo interno**:
1. Busca dados temporais via PI Web API
2. Envia dados para Math Tool Service (`/calculus`)
3. Retorna resultado formatado

### 7.4 status_pims_tool
**Propósito**: Status operacional do PIMS via logs Grafana/Loki.

**Parâmetros**:
- `pergunta_usuario`: Pergunta original
- `lookback_minutes`: Janela de tempo para consulta (padrão: 20 min)

**Fluxo interno**:
1. Consulta Grafana/Loki via `query_loki_range`
2. Filtra linhas de erro/aviso
3. Retorna resumo do status

---

## 8. PI Web API Client

Cliente HTTP assíncrono para comunicação com a PI Web API.

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

### Batch Request
O endpoint `/batch` permite buscar metadados + valor atual + attributes de múltiplas tags em uma única chamada:

```python
batch_request = {
    "point_0": {"Method": "GET", "Resource": "/points?path=\\PIMS\TAG1&selectedFields=..."},
    "value_0": {"Method": "GET", "ParentIds": ["point_0"], "Resource": "/streams/{0}/value"},
    "instrumenttag_0": {"Method": "GET", "ParentIds": ["point_0"], "Resource": "/points/{0}/attributes?name=instrumenttag"},
    ...
}
POST /batch
```

### Digital States
Fluxo para consultar estados digitais:
1. Buscar PI Point → ler `DigitalSetName`
2. Listar Data Servers → encontrar WebId do PIMS
3. Listar Enumeration Sets → encontrar o set com mesmo nome
4. Consultar Enumeration Values → retorna `{Value, Name, Description}`

---

## 9. Memória de Conversa

- **Storage**: Redis (`redis://10.247.179.197:6379/2`)
- **TTL**: 7 dias (604800 segundos)
- **Max turns**: 8 por conversa
- **Chave**: `conversation_id`

**Fluxo**:
1. `_load_memory()`: Carrega turns anteriores do Redis
2. `format_memory_for_prompt()`: Formata para injetar no contexto do agente
3. `_save_memory()`: Salva turn atual (user + assistant) com metadata

---

## 10. OCR (Extração de Imagens)

Quando o usuário envia imagens, o sistema:
1. Envia cada imagem para o LLM com prompt de extração
2. O LLM retorna texto extraído + tags encontradas
3. Tags são extraídas via regex (`[A-Z][A-Z0-9_]+`)
4. Texto OCR é injetado no contexto do agente

**Configuração**: As imagens são enviadas como base64 no campo `images` do `ChatRequest`.

---

## 11. Observabilidade

- **Phoenix** (Arize): Tracing de todas as chamadas LLM e chains
- **OpenTelemetry**: Instrumentação automática do FastAPI e httpx
- **Endpoint**: `http://10.247.179.197:6006` (Phoenix UI)
- **Traces**: Enviados via OTLP HTTP (`/v1/traces`)

---

## 12. Schemas e Modelos

### ChatRequest
```python
class ChatRequest(BaseModel):
    message: str                    # Mensagem do usuário
    images: list[str] | None        # Imagens em base64
    user_id: str | None             # ID do usuário
    conversation_id: str | None     # ID da conversa
```

### ChatResponse
```python
class ChatResponse(BaseModel):
    ok: bool                        # Sucesso da operação
    output: str                     # Resposta final do agente
    categoria: str                  # "conversa_comum" ou "pims"
    tool_name: str                  # Tool utilizada
    tool_result: dict               # Resultado bruto da tool
    agent_trace: list               # Trace de execução do agente
    tags_encontradas: list          # Tags extraídas de OCR
    ...
```

### LLMParams
```python
class LLMParams(BaseModel):
    temperature: float = 0
    num_ctx: int | None = None
    num_predict: int | None = None
    top_k: int | None = None
    top_p: float | None = None
    repeat_penalty: float | None = None
    seed: int | None = None
    keep_alive: str | int | None = None
    max_tokens: int | None = None
```

### Enums (math_tool.py)
- `StatsOperation`: mean, max, min, sum, count, median, range, variance_population, variance_sample, stddev_population, stddev_sample
- `CalculusOperation`: integral, derivative
- `TemporalDataMethod`: recorded, interpolated, summary
- `SummaryType`: Average, Maximum, Minimum, Total, Count, Range, StdDev
- `CalculationBasis`: TimeWeighted, EventWeighted
- `TimeUnit`: second, minute, hour, none

---

## 13. Variáveis de Ambiente (.env)

### Obrigatórias
| Variável | Descrição |
|----------|-----------|
| `GRAFANA_LOKI_QUERY_RANGE_URL` | URL do endpoint query_range do Grafana/Loki |
| `GRAFANA_BEARER_TOKEN` | Token de autenticação do Grafana |

### LLM
| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `LLM_PROVIDER` | `groq` | Provedor ativo: `groq`, `ollama`, `gemini`, `openai_compatible` |
| `GROQ_API_KEY` | — | Chave API do Groq |
| `GROQ_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Modelo Groq |
| `GEMINI_API_KEY` | — | Chave API do Google Gemini |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modelo Gemini |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL do Ollama |
| `OLLAMA_MODEL` | `gemma4:e4b` | Modelo Ollama |

### PI System
| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `PI_WEB_API_BASE_URL` | `http://10.247.224.39/piwebapi` | URL base da PI Web API |
| `PI_SERVER_NAME` | `PIMS` | Nome do Data Server |
| `PI_WEB_API_USERNAME` | — | Usuário (opcional) |
| `PI_WEB_API_PASSWORD` | — | Senha (opcional) |

### Infraestrutura
| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `REDIS_URL` | `redis://127.0.0.1:6379/2` | URL do Redis |
| `QDRANT_URL` | `http://10.247.179.197:6333` | URL do Qdrant |
| `QDRANT_COLLECTION` | `pi_web_api_guide` | Nome da collection |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text-v2-moe` | Modelo de embeddings |
| `MATH_TOOL_BASE_URL` | `http://localhost:8001` | URL do Math Tool Service |
| `PHOENIX_ENABLED` | `false` | Habilitar tracing |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006/v1/traces` | Endpoint Phoenix |

---

## 14. Comandos

```bash
# Instalar dependências
poetry install

# Rodar API (porta 8002)
poetry run uvicorn app.main:app --reload --port 8002

# Rodar Math Tool Service (porta 8001, separado)
cd calc && poetry run uvicorn app.main:app --reload --port 8001

# Subir serviços Docker (Phoenix)
docker-compose up -d

# Reingestir documento RAG
curl -X DELETE http://10.247.179.197:6333/collections/pi_web_api_guide
poetry run python scripts/ingest_pi_guide.py

# Health check
curl http://localhost:8002/health
```

---

## 15. Endpoints

| Método | Path | Descrição |
|--------|------|-----------|
| `GET` | `/health` | Health check com status dos serviços |
| `POST` | `/chat` | Endpoint principal — recebe mensagem e retorna resposta |

---

## 16. Dependências Externas

| Serviço | URL | Uso |
|---------|-----|-----|
| Groq API | `https://api.groq.com` | LLM (padrão) |
| PI Web API | `http://10.247.224.39/piwebapi` | Dados de tags PIMS |
| Qdrant | `http://10.247.179.197:6333` | Vector store RAG |
| Redis | `redis://10.247.179.197:6379/2` | Memória de conversa |
| Grafana/Loki | `http://grafana.acesita.com.br:3000` | Logs operacionais |
| Phoenix | `http://10.247.179.197:6006` | Observabilidade/tracing |
| Math Tool | `http://localhost:8001` | Cálculos estatísticos |
| Ollama | `http://10.247.179.197:11434` | Embeddings (RAG) |

---

## 17. Regras de Negócio

### Names das Tags
- **Sempre** preservar o nome exato da tag informada pelo usuário
- **Nunca** traduzir, abreviar, corrigir ou escape de underscores
- Tags são identificadas por padrão regex: `[A-Z][A-Z0-9_]+`

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
4. Somar as médias horárias no cliente (cada hora em Nm3/h = 1 Nm3)

### Digital States
- Verificar `DigitalSetName` no PI Point
- Se vazio, a tag não é digital
- Consultar `Enumeration Sets` → `Enumeration Values` para mapear índices

---

## 18. Arquivo de Documentação RAG

O arquivo `PI_WEB_API_AGENT_GUIDE.md` é a fonte de verdade para o RAG. Contém 20 CHUNKs:

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
| 18 | Exemplo Python: metadados e instrumenttag |
| 19 | O que não fazer |
| 20 | **FIXO** — Resumo operacional mínimo (sempre injetado) |

---

## 19. Estrutura de Testes

Não existe suíte de testes atualmente. Se necessário, adicionar em `tests/`.

---

## 20. Problemas Comuns

| Problema | Solução |
|----------|---------|
| LLM não responde | Verificar se o provedor está configurado e com chave válida |
| Tags não encontradas | Verificar se `PI_WEB_API_BASE_URL` e `PI_SERVER_NAME` estão corretos |
| RAG não retorna contexto | Verificar se Qdrant está acessível e collection existe |
| Memória não persiste | Verificar se Redis está acessível em `REDIS_URL` |
| OCR não funciona | Verificar se imagens estão em base64 válido |
| Phoenix não aparece | Verificar se `PHOENIX_ENABLED=true` e endpoint acessível |
| Math Tool timeout | Verificar se serviço está rodando em `MATH_TOOL_BASE_URL` |

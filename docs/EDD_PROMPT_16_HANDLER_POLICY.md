# EDD Prompt 16 — Política de Handlers Reais da Outbox

> **Status**: Documento de governança aprovado via `/analyze`, `/clarify` e `/plan`.
> **Data**: 2026-07-06
> **Escopo**: Política formal para `consumer_name`, idempotência, replay e critérios de ativação de handlers reais da outbox.

---

## Sumário

| # | Seção |
|---|-------|
| 1 | Objetivo |
| 2 | Estado atual da arquitetura EDD |
| 3 | Estado atual do dispatcher, router e fallback |
| 4 | Event types cobertos |
| 5 | Risco de duplicidade com a Saga |
| 6 | Política de `consumer_name` |
| 7 | Política de idempotência |
| 8 | Política de replay/reprocessamento |
| 9 | Dispatched técnico vs side effect real |
| 10 | Critérios para criar handler real |
| 11 | Definition of Done para handler real |
| 12 | Regras para handlers futuros |
| 13 | Regras para worker contínuo futuro |
| 14 | Fora do escopo |
| 15 | Roadmap recomendado |
| 16 | Checklist de aprovação para Prompt 17 |

---

## 1. Objetivo

Este documento define a política formal para a criação e operação de handlers reais da outbox do sistema Agent Bot. Ele responde às seguintes perguntas:

- Quando um handler real pode ser criado?
- Qual naming convention deve ser usada para `consumer_name`?
- Como preservar idempotência?
- Como tratar replay/reprocessamento?
- O que significa `dispatched` quando o consumer é log-only?
- Como evitar duplicidade com a Saga?
- Quais event_types existem e qual o estado atual deles?
- Qual é o Definition of Done para um handler real?
- O que ainda está fora do escopo?
- Qual é a sequência recomendada dos próximos prompts?

**Nota**: Este documento é exclusivamente de governança. Não inclui SQL executável, código de produção, scripts, fixtures, migrations, CLI, handler real, worker contínuo, ou atualização de `AGENTS.md`.

---

## 2. Estado atual da arquitetura EDD

### 2.1. Fluxo de eventos

```
POST /chat
  → ConversationSaga (6 steps)
    → EventPublisherImpl
      → TransactionalPostgresEventStore
        → INSERT event_store_events (Event Log)
        → INSERT outbox_events (Outbox, status='pending')
```

- A Saga publica 8+ eventos por request.
- A outbox permanece com `status='pending'` **sem dispatcher automático**.
- O dispatcher é acionado exclusivamente via CLI one-shot.

### 2.2. Gate de ativação

| Variável | Default | Onde é checada |
|---|---|---|
| `EVENT_DRIVEN_ENABLED` | `false` | `app/core/lifespan.py:92` |
| `EVENT_STORE_BACKEND` | `in_memory` | `app/core/config.py` |
| `EVENT_STORE_POSTGRES_DSN` | (vazio) | `app/core/lifespan.py:105` |
| `OUTBOX_DISPATCHER_ENABLED` | (vazio) | `scripts/run_outbox_dispatcher_once.py:102-128` |

### 2.3. Componentes ativos

- `/chat` (FastAPI, porta 8002) — recebe `ChatRequest`, delega ao `process_message`.
- `ConversationSaga` (`app/application/sagas/conversation_saga.py:302`) — 6 steps; publica eventos.
- `EventPublisherImpl` (`app/application/sagas/event_publisher.py:20`) — wrapped em `TransactionalPostgresEventStore` quando `EVENT_DRIVEN_ENABLED=true`.
- `TransactionalPostgresEventStore` (`app/infrastructure/event_store/transactional_postgres_event_store.py`) — grava em `event_store_events` + `outbox_events` na mesma transação.

---

## 3. Estado atual do dispatcher, router e fallback

### 3.1. Componentes

- **`OutboxDispatcher`** (`app/infrastructure/outbox/outbox_dispatcher.py:128`): `SKIP LOCKED`, retry com backoff, DLQ após `attempts >= max_attempts`.
- **`EventTypeRouterConsumer`** (`app/infrastructure/outbox/event_type_router_consumer.py:26`): roteia por `event_type`; aceita `handlers={}`.
- **`LoggingOutboxConsumer`** (`app/infrastructure/outbox/logging_consumer.py:10`): fallback atual; log estruturado stderr.
- **CLI one-shot** (`scripts/run_outbox_dispatcher_once.py`): gateado por `OUTBOX_DISPATCHER_ENABLED=true`; exit codes 0–5.

### 3.2. Configuração do CLI

| Parâmetro | Default | Descrição |
|---|---|---|
| `--batch-size` | `10` | Máximo de eventos por batch |
| `--consumer-name` | `outbox-logging-default` | Identificador do consumer |
| `--worker-id` | auto-gerado | Identificador do worker para lock |

### 3.3. Estado dos consumers

| Consumer | `event_type` alvo | Side effect | Status |
|---|---|---|---|
| `LoggingOutboxConsumer` (fallback) | Todos (via `EventTypeRouterConsumer`) | Log estruturado stderr | Ativo |

**Não há handler real.** O router opera com `handlers={}`. O fallback `LoggingOutboxConsumer` é o único consumer ativo. Qualquer evento ou é tratado pelo seu handler (se houver) ou cai no fallback.

### 3.4. O que não existe hoje

- Nenhum handler real.
- Nenhum worker contínuo, loop, scheduler, background task.
- Nenhum side effect externo (HTTP, Pub/Sub, Kafka, RabbitMQ, Redis-write, file-write).
- Nenhuma CLI de reprocessamento.
- Nenhum `consumer_name` próprio além de `outbox-logging-default`.
- Nenhuma tabela de auditoria/projeção externa.
- Nenhuma métrica de outbox (latência, throughput, DLQ rate).

---

## 4. Event types cobertos

### 4.1. Tabela completa (25 event_types)

| event_type | Categoria | No `DOMAIN_EVENTS_REGISTRY`? | Origem | Handler real atual | Recomendação atual |
|---|---|---|---|---|---|
| `InboundMessageReceived` | Lifecycle | Sim | Saga step 1 | — | Sem handler |
| `OcrExtractionCompleted` | Lifecycle | Sim | Saga step 2 | — | Candidato (auditoria) |
| `ConversationMemoryLoaded` | Lifecycle | Sim | Saga step 1 | — | Candidato (auditoria) |
| `AgentRouteSelected` | Routing | Sim | Saga step 3 | — | Candidato (auditoria) |
| `RagContextRetrieved` | Routing | Sim | Saga step 4 | — | Candidato (auditoria) |
| `AgentRunStarted` | Agent | Sim | Saga step 5 | — | Candidato (auditoria) |
| `AgentToolInvocationRequested` | Agent | Sim | ADK tool call | — | Candidato (auditoria) |
| `AgentToolInvocationCompleted` | Agent | Sim | ADK tool call | — | Candidato (auditoria) |
| `AgentRunCompleted` | Agent | Sim | Saga step 5 | — | Candidato (auditoria) |
| `AgentRunAborted` | Agent | Sim | Saga step 5 (erro) | — | Candidato (auditoria) |
| `OutboundReplyGenerated` | Lifecycle | Sim | Saga (pós step 5) | — | Candidato (auditoria) |
| `PiTagQueried` | Domínio PIMS | Sim | MCP tool call | — | Candidato (auditoria) |
| `PiHistoricalSeriesRetrieved` | Domínio PIMS | Sim | MCP tool call | — | Candidato (auditoria) |
| `StatisticsComputed` | Domínio PIMS | Sim | MCP tool call | — | Candidato (auditoria) |
| `CalculusComputed` | Domínio PIMS | Sim | MCP tool call | — | Candidato (auditoria) |
| `PimsStatusChecked` | Domínio PIMS | Sim | MCP tool call | — | Candidato (auditoria) |
| `ConversationMemorySaved` | Lifecycle | Sim | Saga step 6 | — | Candidato (auditoria) |
| `GoogleChatEventReceived` | Bridge | Sim | Bridge worker | — | Candidato (auditoria) |
| `GoogleChatDedupeStarted` | Bridge | Sim | Bridge dedupe | — | Candidato (auditoria) |
| `GoogleChatReplySent` | Bridge | Sim | Bridge chat client | — | Candidato (auditoria) |
| `GoogleChatDedupeCompleted` | Bridge | Sim | Bridge dedupe | — | Candidato (auditoria) |
| `GoogleChatAttachmentDownloaded` | Bridge | Sim | Bridge media | — | Candidato (auditoria) |
| `MessageProcessingFailed` | Erro | Sim | Saga erro path | — | Candidato (auditoria) |
| `UserMessageRecorded` | Projection | **Não** | Saga step 1 (extra) | — | **Não criar handler** |
| `AssistantMessageRecorded` | Projection | **Não** | Saga step 6 (extra) | — | **Não criar handler** |

### 4.2. Projection events (fora do registry)

| Característica | Valor |
|---|---|
| Path | `app/domain/projections.py:97-115` |
| Herança | `dataclass(frozen=True)` — não herdam de `DomainEvent` |
| Serialização | `to_dict()` próprio; não passam por `DomainEvent._payload()` |
| Stream | `conversation:{conversation_id}` |
| Publicador | Saga steps 1 e 6 (fire-and-forget) |
| Estado atual | Sem handler; sem projeção ativa |

### 4.3. Nota sobre a tabela

As recomendações nesta tabela refletem o estado de Prompt 16 e **não constituem autorização** para criar handlers. Mudanças exigem novo ciclo de `/analyze` + `/clarify`.

---

## 5. Risco de duplicidade com a Saga

### 5.1. Fato arquitetural

A Saga publica dois projection events **em paralelo** à gravação real da memória:

| Evento publicado | Gravação real | Caminho da gravação real |
|---|---|---|
| `UserMessageRecorded` (step 1) | `SaveConversationTurn` (step 6) | `SaveConversationTurnHandler` → `memory.append_turns()` → `rpush` em Redis |
| `AssistantMessageRecorded` (step 6) | `SaveConversationTurn` (step 6) | Mesmo path acima |

Fonte: `app/application/sagas/conversation_saga.py:414-421, 544-572`.

### 5.2. Consequência

| Cenário | Resultado |
|---|---|
| Handler real `UserMessageRecorded` → Redis write | Duplicação: Saga grava + handler grava = 2 gravações |
| Handler real `AssistantMessageRecorded` → Redis write | Mesma duplicação |
| Handler com `consumer_name` próprio | Idempotência em `processed_events` não evita a duplicação — só evita reprocessamento |
| Reprocessamento manual | Cada replay adiciona mais uma gravação (se handler grava) |

### 5.3. Por que a idempotência do `processed_events` não basta

- `processed_events` controla `(consumer_name, event_id)`.
- Idempotência = "não processar o mesmo par duas vezes".
- Não garante que "processar o mesmo evento não causará efeito duplicado".
- O side effect do handler é responsabilidade do handler, não do dispatcher.

### 5.4. Pré-condições para reversão

Qualquer handler real para `UserMessageRecorded`/`AssistantMessageRecorded` exige **pelo menos uma** das duas:

1. A Saga deixa de publicar esses eventos (decisão arquitetural via novo `/analyze`).
2. O handler grava em **destino diferente** da Saga (ex.: tabela de auditoria read-only, métrica, log estruturado) e prova formalmente que não duplica estado.

### 5.5. Regra explícita

> **Prompt 16 não autoriza handler real para `UserMessageRecorded` ou `AssistantMessageRecorded`.** A permissão requer Prompt 17 (ou superior) com análise específica.

---

## 6. Política de `consumer_name`

### 6.1. Convenção obrigatória

```
outbox-{purpose}-v{n}
```

Componentes:

| Componente | Regra | Exemplos válidos | Exemplos inválidos |
|---|---|---|---|
| Prefixo fixo | `outbox-` | — | `Outbox-`, `OB-`, `consumer-` |
| `{purpose}` | kebab-case, lowercase, ≤ 32 caracteres | `logging`, `memory-projection`, `audit-projection`, `google-chat-reply` | `Logging`, `x` |
| `-v{n}` | Versão semântica inteira; primeira versão = `v1` | `-v1`, `-v2`, `-v10` | `-V1`, `-v1.0`, `-rc1` |

### 6.2. Exemplos válidos

| consumer_name | Propósito | Quando usar |
|---|---|---|
| `outbox-logging-default` | Fallback log-only atual | Estado atual; não muda neste ciclo |
| `outbox-memory-projection-v1` | Projeção de memória | Prompt 17 condicional |
| `outbox-audit-projection-v1` | Projeção de auditoria | Prompt 17 condicional |
| `outbox-google-chat-reply-v1` | Side effect de reply Google Chat | Prompt 18+, requirement explícito |

### 6.3. Imutabilidade

- `consumer_name` **não** é renomeado em produção.
- Mudança de propósito = novo `consumer_name` + novo namespace em `processed_events`.
- Reprocessamento manual = `outbox-{purpose}-v{n}-replay-{YYYYMMDD}`.

### 6.4. Casos especiais reservados

| Prefixo | Reservado para |
|---|---|
| `outbox-replay-` | Reprocessamento manual |
| `outbox-test-` | Testes automatizados (apenas CI/staging) |
| `outbox-shadow-` | Consumer sombra para validação paralela (futuro) |

### 6.5. Validação futura (não implementada neste ciclo)

- Regex proposta: `^outbox-[a-z][a-z0-9-]{0,30}-v[0-9]+$`.
- Aplicação: PR review + teste unitário.

---

## 7. Política de idempotência

### 7.1. Idempotência primária (já implementada pelo dispatcher)

- `processed_events.PRIMARY KEY (consumer_name, event_id)`.
- Verificação: `is_processed(consumer_name, event_id)` antes de `consumer.handle`.
- Marcação: `mark_dispatched(consumer_name, event_id, ...)` após sucesso.
- Falha controlada: `mark_retry` ou `move_to_dlq`.

### 7.2. Idempotência secundária (responsabilidade do handler real)

Se o handler tem side effect externo:

- Deve usar chave de idempotência própria (ex.: `event_id`, `conversation_id + stream_version`).
- Deve tolerar execução duplicada: nenhum side effect irreversível sem proteção.
- Deve logar quando já executou (idempotência verificada pelo handler).

### 7.3. Restrições

- Um handler **não pode** usar `consumer_name` de outro handler.
- Um handler **não pode** gravar em `processed_events` (responsabilidade do dispatcher).
- Um handler **não pode** alterar `outbox_events` (responsabilidade do dispatcher).

### 7.4. Verificação manual

```text
SELECT count(*) FROM processed_events WHERE consumer_name = 'outbox-{purpose}-v{n}';
```

O contador deve crescer monotonicamente. Re-execução do CLI com mesmo `consumer_name`: `already_processed_count > 0`, `processed_count = 0`.

---

## 8. Política de replay/reprocessamento

### 8.1. Princípio

> **Reprocessamento é manual, explícito e reversível.** Não há reprocessamento automático.

### 8.2. Quando reprocessar

| Caso | Recomendação |
|---|---|
| Eventos em `outbox_events.status='pending'` legados | Aguardar dispatcher manual com mesmo `consumer_name` |
| Eventos em `status='locked'` expirados | Dispatcher recupera no próximo `claim_batch` |
| Eventos em `outbox_dlq` | Investigar erro; reprocessar requer reset manual |
| Replay intencional de auditoria | Usar `consumer_name` dedicado com sufixo `-replay-YYYYMMDD` |

### 8.3. O que reprocessamento **não** é

- Não é agendado (cron, scheduler).
- Não é ativado por métrica.
- Não é transparente para o operador.
- Não é parte do CLI padrão.

### 8.4. Pré-condições para reprocessamento

1. Backup do banco (Postgres + Redis).
2. Lista de `event_id` a reprocessar.
3. `consumer_name` dedicado com sufixo `-replay-YYYYMMDD`.
4. Reset controlado de `outbox_events.status` para o subset alvo.
5. Remoção de `processed_events` para o `consumer_name` dedicado.

### 8.5. Auditoria de reprocessamento

- Cada reprocessamento deve ter registro externo (log de operador, ticket).
- O `consumer_name` dedicado com timestamp garante rastreabilidade.
- `outbox_dlq` é a fonte histórica de eventos que esgotaram tentativas.

**Nota**: Este documento não contém SQL executável. Comandos de reset são conceituais e não devem ser aplicados diretamente sem procedimento operacional separado.

---

## 9. Dispatched técnico vs side effect real

### 9.1. Definições

| Conceito | Significado |
|---|---|
| `outbox_events.status='dispatched'` | Linha marcada como despachada pelo dispatcher; entrada em `processed_events` |
| Side effect real | Mutação fora do banco `event_store_postgres` (Redis write, HTTP, Pub/Sub, file, etc.) |
| Consumer log-only | Consumer cujo único side effect é log estruturado em stderr |
| Consumer real | Consumer com side effect além de log |

### 9.2. Estado atual

- **Todos os consumers ativos são log-only** (`LoggingOutboxConsumer`).
- `status='dispatched'` é puramente técnico.
- Não há side effect real na execução atual.

### 9.3. Consequência

- Métricas de "taxa de dispatch" **não** representam trabalho externo.
- A asserção "evento foi processado" deve ser qualificada: "foi logado" ≠ "teve side effect real".
- Documentação externa (relatórios, dashboards) deve qualificar.

### 9.4. Princípio de comunicação

> Nunca afirmar "evento processado" sem qualificar. Sempre: "foi despachado" (técnico) ou "foi consumido por handler X" (real).

---

## 10. Critérios para criar handler real

### 10.1. Pré-condições obrigatórias (6)

| # | Critério | Verificação |
|---|---|---|
| C1 | Requirement explícito documentado | PRD, ticket ou doc de feature |
| C2 | `consumer_name` próprio definido | Segue `outbox-{purpose}-v{n}` |
| C3 | Side effect analisado | Doc mostra onde grava, idempotência, replay |
| C4 | Schema/tabela validada em QA | Se grava em tabela: tabela existe; se log-only: explícito |
| C5 | Testes unitários ≥ 5 casos | Fakes para success, failure, idempotent, no-op, error |
| C6 | DoD cumprido | Checklist da seção 11 |

### 10.2. Bloqueios explícitos

- Sem C1 → handler não é criado.
- Sem C2 → handler não é registrado.
- Sem C3 → handler não é mergeado.
- Sem C4 → handler não é ativado.
- Sem C5 → regressões não detectadas.
- Sem C6 → handler incompleto.

---

## 11. Definition of Done para handler real

### 11.1. Checklist de 8 itens

- [ ] D1: Requirement explícito (link para ticket/PRD).
- [ ] D2: `consumer_name` segue `outbox-{purpose}-v{n}`.
- [ ] D3: Implementação em `app/infrastructure/outbox/handlers/{purpose}_handler.py`.
- [ ] D4: Implementa `OutboxConsumer` Protocol (`async def handle(self, event: OutboxEvent) -> None`).
- [ ] D5: Testes unitários com fakes (≥ 5 casos: success, failure, idempotent, no-op, error).
- [ ] D6: Doc de design (`docs/EDD_PROMPT_NN_{purpose}_handler.md`).
- [ ] D7: Validação manual contra Postgres local/QA via CLI (`--consumer-name outbox-{purpose}-v1`).
- [ ] D8: Sem regressão: testes da Saga + dispatcher + router permanecem verdes.

### 11.2. Bloqueio de merge

Qualquer item de D1–D8 não cumprido → handler **não** é mergeado na branch principal.

### 11.3. Exceções

Nenhuma. DoD é gate obrigatório.

---

## 12. Regras para handlers futuros

### 12.1. 7 regras de design

| # | Regra | Justificativa |
|---|---|---|
| R1 | Implementar `OutboxConsumer` Protocol | Duck typing; testabilidade |
| R2 | Erro em `handle()` → raise exception; não engolir | Dispatcher controla retry/DLQ |
| R3 | Não usar `asyncio.create_task` ou fire-and-forget | Side effect deve completar antes de `mark_dispatched` |
| R4 | Não bloquear > 5s sem progresso (ideal < 1s) | Backlog não pode estagnar |
| R5 | Log estruturado com `consumer_name`, `event_id`, `event_type` | Rastreabilidade |
| R6 | Idempotência interna se side effect externo | Replay não pode duplicar |
| R7 | Sem dependência de estado global mutável | Testes determinísticos |

### 12.2. Padrões proibidos

- Singleton com estado interno.
- Variáveis de ambiente lidas dentro do handler (devem vir do construtor).
- `print()` (usar `logger`).
- Conexão de rede aberta no construtor (lazy connect).
- Acesso direto ao `EventStore` ou `OutboxStore`.

---

## 13. Regras para worker contínuo futuro

> **Prospecção, não autorização.** Worker contínuo está fora do escopo de Prompt 16.

### 13.1. 5 regras

| # | Regra |
|---|---|
| W1 | Worker em processo separado, não em `lifespan.py` |
| W2 | Profile dedicado em `docker-compose.yaml` (não reusar profile `events`) |
| W3 | Gate `OUTBOX_WORKER_ENABLED` próprio, independente de `OUTBOX_DISPATCHER_ENABLED` |
| W4 | Política de erro explícita: falha de Postgres → fail-fast vs degrade (decisão do operador) |
| W5 | Observabilidade: span OTel por `dispatch_once`, métrica de `dispatched/retry/dlq` |

### 13.2. Bloqueios

- W1 falhando → worker não é mergeado.
- W2 falhando → worker só roda em local/QA.
- W3 falhando → worker pode ser ativado acidentalmente.
- W4 ausente → decisão de produção indefinida.
- W5 ausente → debugging inviável.

---

## 14. Fora do escopo

Os 10 itens abaixo estão **explicitamente fora** do escopo de Prompt 16:

1. Implementação de qualquer handler real.
2. Worker contínuo, loop, scheduler, background task.
3. Alteração em `app/infrastructure/outbox/`.
4. Alteração em `scripts/run_outbox_dispatcher_once.py`.
5. Alteração em schema SQL, `docker-compose.yaml`, `.env`, `.env.example`.
6. Alteração em `app/main.py`, `app/core/lifespan.py`, `app/core/config.py`.
7. Validador regex para `consumer_name`.
8. CLI de reprocessamento.
9. Métricas OTel para outbox.
10. Qualquer alteração em `AGENTS.md`, `README.md`, `pyproject.toml`, `poetry.lock`.

---

## 15. Roadmap recomendado

### 15.1. Marcos de maturidade

| Marco | Estado |
|---|---|
| M0 (atual) | Dispatcher CLI + router com fallback log-only |
| **M1 (Prompt 16)** | **Governance de handler documentada** |
| M2 (Prompt 17+, condicional) | Primeiro handler real em produção |
| M3 (futuro) | Worker contínuo |
| M4 (futuro) | Métricas de outbox |
| M5 (futuro) | Replay CLI |
| M6 (futuro) | Múltiplos handlers concorrentes |

### 15.2. Anti-roadmap (não fazer)

- Pular Prompt 16 e ir direto para handler real.
- Implementar worker contínuo sem handler real.
- Implementar handler real para `UserMessageRecorded`/`AssistantMessageRecorded` sem nova análise.
- Implementar replay automático.

---

## 16. Checklist de aprovação para Prompt 17

### 16.1. 6 perguntas obrigatórias

Antes de iniciar Prompt 17, o operador deve responder **sim** a todas:

1. O requirement do handler está documentado com pelo menos 1 caso de uso?
2. O `consumer_name` proposto segue `outbox-{purpose}-v{n}`?
3. O side effect está documentado (onde grava, idempotência, replay)?
4. O handler é log-only ou grava em tabela/schema já existente?
5. Os 8 itens de DoD (seção 11) são todos cumpríveis neste ciclo?
6. Nenhum dos 10 itens "fora do escopo" (seção 14) será tocado?

### 16.2. Bloqueio

Qualquer resposta "não" → Prompt 17 **não** inicia. Reabre `/clarify` ou `/analyze`.

---

Agora vou executar as verificações:

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="todowrite">
<｜｜DSML｜｜parameter name="todos" string="false">[{"content": "Criar docs/EDD_PROMPT_16_HANDLER_POLICY.md com 16 seções", "status": "completed", "priority": "high"}, {"content": "T7: Revisão semântica de SQL executável", "status": "in_progress", "priority": "medium"}, {"content": "T8: Verificações finais (git status, tamanho, secrets, AGENTS.md)", "status": "pending", "priority": "medium"}]
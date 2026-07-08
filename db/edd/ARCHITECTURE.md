# Arquitetura EDD — Event Driven Design com Postgres

> **Estado: implementado e validado (Prompts 12–27).**
> Este documento é a fonte da verdade arquitetural do bloco EDD.
> Para operação, consulte `db/edd/RUNBOOK.md`.
> Para governança do projeto, consulte `AGENTS.md` §§33–34.

---

## 1. Visão geral

O **Event Driven Design (EDD)** do Agent Bot utiliza **PostgreSQL** como **Event Store** e **Transactional Outbox** para persistência durável de eventos de domínio e dispatch assíncrono de efeitos colaterais. O sistema publica eventos durante o processamento de uma requisição `/chat` e um dispatcher/worker posterior os consome, garantindo idempotência, retry com backoff e dead-letter queue (DLQ).

O fluxo EDD atual é **pós-processamento do agente** — eventos são publicados depois que o agente gera a resposta, não antes. O caso real atual é salvar memória de conversa (`ConversationMemorySaveRequested`).

---

## 2. Objetivos

- Persistir eventos de domínio em `event_store_events` (append-only).
- Publicar eventos para processamento posterior via `outbox_events` (Transactional Outbox).
- Garantir **escrita atômica** em ambas as tabelas na mesma transação Postgres.
- Processar eventos da outbox com **locking concorrente** (`SELECT ... FOR UPDATE SKIP LOCKED`).
- Aplicar **retry exponencial** em falhas do consumer.
- Mover eventos para **DLQ** após exaustão de tentativas (`outbox_dlq`).
- Garantir **idempotência** por consumer via `processed_events(consumer_name, event_id)`.
- Prover **recovery auditável** com dry-run e execute controlado (`outbox_recovery_audit`).
- Oferecer **observabilidade segura** (logs estruturados, erros sanitizados, DSN redactado).

---

## 3. Não-objetivos

- **Não** é Event Sourcing completo — o Event Store não é fonte da verdade do estado do sistema (a fonte são Redis + PI Web API).
- **Não** é Kafka, broker distribuído ou sistema de mensageria com fan-out nativo.
- **Não** implementa guardrails bloqueante — se implementado no futuro, deve entrar no caminho crítico do `/chat`, não ser apenas consumer outbox.
- **Não** substitui o processamento síncrono do agente — a outbox é para efeitos **posteriores**.
- **Não** oferece múltiplos consumers independentes completos — `processed_events` dá base, mas suporte a deliveries/subscriptions é futuro.

---

## 4. Fluxo EDD do `/chat`

O fluxo EDD ocorre **depois** que o agente processa a mensagem e gera a resposta:

1. O agente processa a mensagem do usuário e gera uma resposta.
2. A saga (`ConversationSaga`) decide salvar o turno na memória.
3. Quando `EVENT_DRIVEN_ENABLED=true`, a saga publica `ConversationMemorySaveRequested` **em vez de** salvar diretamente.
4. `EventPublisherImpl` delega para `TransactionalPostgresEventStore.append()`.
5. O Event Store escreve em `event_store_events` e `outbox_events` **na mesma transação**.
6. O `OutboxDispatcher` (one-shot ou worker) posteriormente consome o evento da outbox.
7. `EventTypeRouterConsumer` roteia pelo `event_type`.
8. `ConversationMemorySaveOutboxHandler` processa a requisição de salvamento.
9. `SaveConversationTurnHandler` persiste no Redis via Lua atômico com idempotência.

---

## 5. Diagrama textual ASCII

```text
/chat
  |
  v
ConversationSaga / Orchestrator
  |
  v
Agent gera resposta
  |
  v
Saga publica ConversationMemorySaveRequested
  |
  v
TransactionalPostgresEventStore
  |
  v
event_store_events + outbox_events  (mesma transação)
  |
  v
OutboxDispatcher / worker / one-shot
  |
  v
EventTypeRouterConsumer
  |
  v
ConversationMemorySaveOutboxHandler
  |
  v
SaveConversationTurnHandler
  |
  v
Memory saver / Redis adapter
```

**Notas importantes:**

- A outbox fica **depois** do processamento do agente, não antes.
- A outbox é para **efeitos colaterais posteriores**, não para o fluxo principal de resposta.
- Guardrails bloqueante não faz parte deste fluxo — se implementado, deve ser síncrono no `/chat`.
- O dispatcher/worker é desacoplado — o `/chat` não espera o dispatch para responder.

---

## 6. Componentes e responsabilidades

| Componente | Arquivo | Responsabilidade |
|---|---|---|
| `TransactionalPostgresEventStore` | `app/infrastructure/event_store/transactional_postgres_event_store.py` | Persiste eventos em `event_store_events` + `outbox_events` na mesma transação |
| `PostgresOutboxStore` | `app/infrastructure/outbox/outbox_dispatcher.py` | Implementa `OutboxStore`: claim, mark_dispatched, mark_retry, move_to_dlq sobre Postgres |
| `OutboxDispatcher` | `app/infrastructure/outbox/outbox_dispatcher.py` | Orquestra dispatch: claim → is_processed → consumer.handle → mark_dispatched/retry/DLQ |
| `EventTypeRouterConsumer` | `app/infrastructure/outbox/event_type_router_consumer.py` | Roteia por `event_type` para handler específico ou fallback |
| `ConversationMemorySaveOutboxHandler` | `app/infrastructure/outbox/handlers/conversation_memory_save_handler.py` | Handler real: processa `ConversationMemorySaveRequested`, chama `SaveConversationTurnHandler` |
| `LoggingOutboxConsumer` | `app/infrastructure/outbox/logging_consumer.py` | Fallback para event_types sem handler (usado no one-shot) |
| `FailingOutboxConsumer` | `scripts/run_outbox_worker.py` | Fallback seguro no worker — força DLQ em event_types sem handler |
| `build_runtime_event_publisher` | `app/core/runtime_publisher.py` | Constrói `EventPublisher` com 5 ramos de decisão (R1–R5) |
| `event_driven_lifespan` | `app/core/lifespan.py` | Cria/fecha pool asyncpg sob gates G0–G3 |
| `EventPublisherImpl` | `app/application/sagas/event_publisher.py` | Wrapper que delega publish para o EventStore, com log de falhas |
| `NullEventPublisher` | `app/application/sagas/event_publisher.py` | **Fallback produtivo** — no-op quando EDD está desabilitado |

---

## 7. Tabelas e schemas

O schema EDD utiliza **5 tabelas**:

| Ordem | Schema | Tabela | Finalidade |
|---|---|---|---|
| 001 | `app/infrastructure/event_store/sql/001_create_event_store_events.sql` | `event_store_events` | Event Log append-only com `UNIQUE(stream_id, stream_version)` |
| 002 | `db/edd/002_create_outbox_events.sql` | `outbox_events` | Fila de dispatch com status, retry, locking e auditoria |
| 003 | `db/edd/003_create_processed_events.sql` | `processed_events` | Idempotência por consumer — `PRIMARY KEY (consumer_name, event_id)` |
| 004 | `db/edd/004_create_outbox_dlq.sql` | `outbox_dlq` | Dead-letter queue separada com snapshot do payload final |
| 005 | `db/edd/005_create_outbox_recovery_audit.sql` | `outbox_recovery_audit` | Auditoria append-only de operações de recovery |

Todas as DDLs são idempotentes (`CREATE TABLE IF NOT EXISTS`). Não há FK física entre as tabelas — a integridade é mantida pela aplicação.

---

## 8. Eventos publicados

Atualmente, **um evento real passa pela outbox**:

| Evento | Tipo | Propósito |
|---|---|---|
| `ConversationMemorySaveRequested` | Domain Event | Solicita persistência assíncrona de um turno de conversa no Redis |

**Demais eventos** (ex: `InboundMessageReceived`, `AgentRouteSelected`, `AgentRunCompleted`) são publicados no `event_store_events` mas **não passam pela outbox** — servem para observabilidade e rastreabilidade.

O allowlist de recovery (`scripts/recover_outbox_event.py:54-56`) reflete essa realidade: apenas `ConversationMemorySaveRequested` é elegível para recovery.

---

## 9. Consumers e handlers

| Consumer | Contexto | Comportamento |
|---|---|---|
| `ConversationMemorySaveOutboxHandler` | Real (EVENT_DRIVEN_ENABLED=true) | Processa `ConversationMemorySaveRequested`: valida payload, chama `SaveConversationTurnHandler` com `idempotency_key=event_id` |
| `LoggingOutboxConsumer` | Fallback (one-shot dispatcher) | Loga o evento e retorna sucesso — usado quando não há handler registrado |
| `FailingOutboxConsumer` | Fallback (worker contínuo) | **Força DLQ** — levanta `RuntimeError` para event_types sem handler, garantindo que não sejam silenciosamente ignorados |

A diferença entre os fallbacks é intencional: no one-shot o operador quer visibilidade via log; no worker contínuo o comportamento seguro é forçar DLQ para investigação posterior.

---

## 10. Idempotência

O sistema implementa **duas camadas de idempotência**:

### 10.1 Idempotência de infraestrutura (`processed_events`)

O `PostgresOutboxStore.mark_dispatched` insere em `processed_events` com `ON CONFLICT (consumer_name, event_id) DO NOTHING`. Antes de executar o consumer, o dispatcher verifica `is_processed()` — se já existe, marca como `dispatched` sem executar o handler.

### 10.2 Idempotência de negócio (Redis Lua)

O `SaveConversationTurnHandler` (via `append_memory_turns`) aceita `idempotency_key` opcional (o `event_id` do `OutboxEvent`). Um script Lua atômico verifica se a chave de dedupe `pi_chat:memory:{conversation_id}:dedupe:{event_id}` existe:

- **Se existe**: no-op success (não duplica o turno).
- **Se não existe**: executa `RPUSH` + `LTRIM` + `EXPIRE` + `SET EX` atomicamente.

TTL da dedupe key: `CHAT_MEMORY_TTL_SECONDS` (7 dias por default).

---

## 11. Retry, locking e DLQ

### 11.1 Modelo de retry

Não há status `failed`. A falha retentável é representada por:

- `status = 'pending'`
- `attempts` incrementado
- `available_at` no futuro (backoff exponencial)
- `last_error` e `last_error_class` preenchidos (com conteúdo sanitizado)

### 11.2 Locking concorrente

`PostgresOutboxStore.claim_batch` usa:

```sql
SELECT ... FROM outbox_events
WHERE status = 'pending' AND available_at <= NOW()
   OR status = 'locked' AND locked_until < NOW()
ORDER BY available_at ASC, outbox_id ASC
LIMIT N
FOR UPDATE SKIP LOCKED
```

Após o SELECT, os eventos são atualizados para `status='locked'` com `locked_by` e `locked_until`. Eventos com lock expirado são automaticamente reivindicados.

### 11.3 Dead-letter queue

Após `attempts >= max_attempts`, o dispatcher chama `PostgresOutboxStore.move_to_dlq()`:

1. `INSERT INTO outbox_dlq ... ON CONFLICT (outbox_id) DO UPDATE` — upsert permite que um evento vá para DLQ múltiplas vezes sem colisão UNIQUE.
2. Atualiza `outbox_events` para `status='dead_letter'` com `dead_lettered_at`.

---

## 12. Recovery e auditoria

### 12.1 Dry-run

`scripts/recover_outbox_event.py` sem `--execute`:

- Apenas `SELECT` — read-only.
- Valida V3–V8: outbox existe, status=dead_letter, event_type na allowlist (`ConversationMemorySaveRequested`), attempts >= max_attempts, DLQ snapshot existe, processed_events sem linha.
- Retorna `eligible=true/false` com `reason_code`.

### 12.2 Execute

`scripts/recover_outbox_event.py --execute --yes-i-confirm-recovery`:

1. Abre transação Postgres.
2. `SELECT ... FOR UPDATE` na linha alvo.
3. Revalida V4–V8 (dentro da transação, sob lock).
4. Insere em `outbox_recovery_audit` (`operation='recovery_execute'`).
5. Atualiza `outbox_events`: `status='pending'`, `attempts=0`, limpa erros.
6. Commit.

**Limitações do execute:**

- Single `outbox_id` — bulk recovery proibido.
- Local/QA only — PRD bloqueado neste ciclo.
- Não processa o evento — só requeue. Operador roda worker/one-shot separadamente.
- Confirmação textual obrigatória `--yes-i-confirm-recovery`.

### 12.3 Auditoria (`outbox_recovery_audit`)

- **Append-only**: trigger `BEFORE UPDATE OR DELETE` bloqueia alterações. `TRUNCATE` não é bloqueado.
- **Sem PII**: não armazena `event_payload`, `user_message`, `conversation_id`, `user_id`.
- **CHECK constraints**: operation, command_source, ticket/reason, attempts >= 0.
- **FK**: `outbox_id` referencia `outbox_events(outbox_id) ON DELETE RESTRICT`.

---

## 13. Observabilidade e logs seguros

Todo o fluxo EDD emite logs estruturados via `logger.<nível>("evento", extra={...})` (sem `logger.exception`).

### 13.1 Eventos de log

| Evento | Nível | Onde |
|---|---|---|
| `outbox_event_retry_scheduled` | WARNING | `OutboxDispatcher.dispatch_once` |
| `outbox_event_dead_lettered` | ERROR | `OutboxDispatcher.dispatch_once` |
| `outbox_worker_iteration` | INFO | `scripts/run_outbox_worker.py` |
| `outbox_worker_error` | WARNING | `scripts/run_outbox_worker.py` |
| `outbox_recovery_execute_started/finished/blocked` | INFO/WARNING | `scripts/recover_outbox_event.py` |
| `outbox_inspect_started/finished/failed` | INFO/ERROR | `scripts/inspect_outbox.py` |

### 13.2 Campos proibidos em logs

Nunca aparecem em `extra={}`:

- `event_payload`, `payload`
- `user_message`, `assistant_message`
- `conversation_id`, `user_id`, `aggregate_id`
- DSN bruto, `token`, `password`, `secret`, `api_key`, `authorization`, `Bearer`

### 13.3 Sanitização de erros

`app/infrastructure/outbox/_error_redaction.py` redige automaticamente:

- `user_message`, `assistant_message`
- `token`, `password`, `passwd`, `secret`, `api_key`
- `authorization: Bearer ...`
- Trunca mensagens com `...[truncated]`

### 13.4 DSN

Em nenhum ponto o DSN bruto é logado. Todos os helpers usam `_dsn_host_for_log()`, `_mask_dsn_host()` ou `redact_dsn()` para extrair apenas `host:port`.

---

## 14. Configuração e flags

### 14.1 Variáveis de ambiente

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `EVENT_DRIVEN_ENABLED` | Sim (para EDD) | `false` | Habilita publicação de eventos EDD no `/chat` |
| `EVENT_STORE_BACKEND` | Sim (para EDD) | `memory` | Deve ser `transactional_postgres` para o caminho EDD real |
| `EVENT_STORE_POSTGRES_DSN` | Sim (para Postgres) | `None` | DSN de conexão ao Postgres (`postgresql://user:pass@host:port/db`) |
| `OUTBOX_DISPATCHER_ENABLED` | Sim (scripts) | lida via env var | Habilita `scripts/run_outbox_dispatcher_once.py` |
| `OUTBOX_WORKER_ENABLED` | Sim (worker) | lida via env var | Habilita `scripts/run_outbox_worker.py` |
| `CHAT_MEMORY_TTL_SECONDS` | Não | `604800` | TTL da dedupe key no Redis (idempotência de memória) |

### 14.2 Fallback produtivo

Quando `EVENT_DRIVEN_ENABLED=false` ou `EVENT_STORE_BACKEND != transactional_postgres` ou pool é `None`, o `build_runtime_event_publisher` retorna **`NullEventPublisher`** (no-op). **Nunca retorna `InMemoryEventStore`** como fallback. Esta é uma decisão arquitetural deliberada (D14).

### 14.3 Caminho de decisão (R1–R5)

```
R1 — EVENT_DRIVEN_ENABLED=false          → NullEventPublisher
R2 — backend != transactional_postgres   → NullEventPublisher (log: backend_mismatch)
R3 — pool is None                         → NullEventPublisher (log: pool_missing)
R4 — pré-requisitos ok                    → EventPublisherImpl(TransactionalPostgresEventStore(pool))
R5 — exceção inesperada                   → NullEventPublisher (log: creation_failed)
```

---

## 15. Operação e scripts

Para operação detalhada, consulte **`db/edd/RUNBOOK.md`**, que cobre:

- Aplicação e validação do schema (`scripts/apply_edd_schema.sh`, `scripts/validate_edd_schema.sh`)
- Dispatcher one-shot (`scripts/run_outbox_dispatcher_once.py`) com exit codes
- Worker contínuo controlado (`scripts/run_outbox_worker.py`) com gates e shutdown
- Inspeção da outbox (`scripts/inspect_outbox.py`) com subcomandos read-only
- Recovery dry-run e execute (`scripts/recover_outbox_event.py`)
- Auditoria de recovery (`outbox_recovery_audit`)
- Política de retenção de DLQ
- O que **não** fazer manualmente
- Logs estruturados e eventos de log

---

## 16. Testes e evidências

### 16.1 Testes E2E (requer Postgres real)

| Arquivo | O que valida |
|---|---|
| `tests/integration/edd/test_e2e_chat_outbox_flow.py` | Happy path: `/chat` real → Event Store → Outbox → dispatch_once com handler real → processed_events; e DLQ + recovery dry-run + execute + audit + reprocess + idempotência |

### 16.2 Testes de integração (requer Postgres real)

| Arquivo | O que valida |
|---|---|
| `tests/integration/edd/test_transactional_postgres_event_store_integration.py` | Escrita atômica em ambas tabelas |
| `tests/integration/edd/test_postgres_outbox_store_integration.py` | claim, mark_dispatched, mark_retry, move_to_dlq |
| `tests/integration/edd/test_outbox_dispatcher_integration.py` | Dispatcher com store real |
| `tests/integration/edd/test_recover_outbox_event_execute_integration.py` | Recovery execute |
| `tests/integration/edd/test_outbox_recovery_audit_integration.py` | Auditoria append-only |
| `tests/integration/edd/test_conversation_memory_save_handler_integration.py` | Handler real |
| `tests/integration/edd/test_conversation_memory_save_handler_dlq_integration.py` | Handler + DLQ |
| `tests/integration/edd/test_logging_consumer_integration.py` | Fallback logger |

### 16.3 Testes unitários (sem dependências externas)

| Arquivo | O que valida |
|---|---|
| `tests/unit/test_outbox_dispatcher.py` | 51 testes: dispatch_once, retry, DLQ, already_processed |
| `tests/unit/test_recover_outbox_event.py` | 41 testes: elegibilidade, execute, validações |
| `tests/unit/test_run_outbox_worker.py` | 24 testes: gates, shutdown, loop, argumentos |
| `tests/unit/test_inspect_outbox.py` | 46 testes: subcomandos, filtros, sanitização |
| `tests/unit/test_transactional_postgres_event_store.py` | 59 testes: append, append_batch, safe_payload |

---

## 17. Decisões arquiteturais, limitações e adiamentos

### 17.1 Decisões arquiteturais

| Decisão | Descrição |
|---|---|
| Postgres como fila, não Kafka | O projeto usa Postgres para persistência transacional + outbox. Kafka/broker distribuído estão fora do escopo. |
| `event_store_events` separado de `outbox_events` | Log puro vs. fila de dispatch. Concerns separados. |
| `processed_events` por `(consumer_name, event_id)` | Namespace de idempotência isolado por consumer. |
| DLQ como tabela separada | `outbox_dlq` tabela própria, não coluna de status. |
| Sem status `failed` | Falha retentável = `pending + attempts + available_at`. |
| Recovery execute não processa o evento | Só requeue (dead_letter → pending). Operador roda worker em seguida. |
| Fallback `NullEventPublisher`, não `InMemoryEventStore` | Decisão deliberada (D14): sem configuração EDD, eventos são descartados, não armazenados em memória. |
| DSN local-only em scripts | `127.0.0.1` ou `localhost` obrigatório. Proteção contra execução remota acidental. |
| Confirmação textual no recovery | `--yes-i-confirm-recovery` obrigatório. |
| Audit append-only com trigger | `outbox_recovery_audit` bloqueia UPDATE/DELETE. |
| `move_to_dlq` com upsert | `ON CONFLICT (outbox_id) DO UPDATE` — segunda ida para DLQ não colide. |

### 17.2 Limitações conhecidas

| Limitação | Detalhe |
|---|---|
| Single worker | Apenas um worker por vez (SKIP LOCKED multi-worker não testado). |
| Recovery PRD proibido | `--execute` permitido apenas em local/QA neste ciclo. |
| Exit codes não unificados | `run_outbox_dispatcher_once.py`, `run_outbox_worker.py`, `recover_outbox_event.py`, `inspect_outbox.py` têm conjuntos de exit codes diferentes. |
| Adapters de memória duplicados | `_CLIMemoryAdapter` (one-shot) e `_MemoryAdapter` (worker) com lógica quase idêntica. |
| `consumer_name` centralizado adiado | Valor hardcoded como `outbox-conversation-memory-save-v1` em múltiplos lugares. |
| Factory de handler adiada | `run_outbox_dispatcher_once.py` e `run_outbox_worker.py` constroem o handler inline. |
| `_check_eligibility` duplicado | Lógica de validação V3–V8 aparece em duas funções (`_check_eligibility` e `_check_eligibility_locked`). |
| Guardrails bloqueante não existe | Se implementado, deve ser síncrono no `/chat`, não consumer outbox. |
| Múltiplos consumers independentes | Modelo atual favorece consumer principal por evento; deliveries/subscriptions são futuras. |
| `build_runtime_event_publisher` por request | Chamado em cada `/chat`, não cacheado. |
| `_build_saga` settings fixo | A saga usa o settings global, não recebe settings injetado dinamicamente. |

---

## 18. Referências cruzadas

| Documento | Conteúdo |
|---|---|
| `db/edd/RUNBOOK.md` | Operação detalhada: schema, dispatcher, worker, inspect, recovery, segurança |
| `db/edd/README.md` | Índice do diretório `db/edd/` com lista de schemas |
| `docs/edd_schema.md` | Referência curta dos schemas 001–005 |
| `AGENTS.md` §§33–34 | Governança do projeto: estado e decisões arquiteturais |
| `app/infrastructure/event_store/transactional_postgres_event_store.py` | Implementação do Event Store transacional |
| `app/infrastructure/outbox/outbox_dispatcher.py` | OutboxDispatcher e PostgresOutboxStore |
| `scripts/run_outbox_worker.py` | Worker contínuo controlado |
| `scripts/run_outbox_dispatcher_once.py` | Dispatcher one-shot |
| `scripts/recover_outbox_event.py` | Recovery dry-run e execute |
| `scripts/inspect_outbox.py` | Inspeção read-only da outbox |

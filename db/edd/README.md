# db/edd/ — Schema EDD (Event Driven Design com Postgres)

> **Status: preparação.** Este diretório contém DDLs SQL futuros do bloco "Event Driven Design com Postgres" do agent_bot. Nenhum arquivo aqui é aplicado automaticamente. O `/chat` não depende dessas tabelas.

---

## 1. Visão geral

`db/edd/` contém o schema conceitual do bloco EDD — preparado para outbox, idempotência por consumer e dead-letter queue (DLQ). O schema é **idempotente** e **coexiste** com a tabela herdada `event_store_events`.

Este schema **não ativa runtime**. O Postgres continua sob ativação explícita no profile `events` do `docker-compose.yaml`.

## 2. Estado atual

- Todos os arquivos `.sql` são DDLs idempotentes (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`).
- Nenhum deles é aplicado automaticamente por nenhum script, hook ou startup.
- O `/chat` continua usando `InMemoryEventStore()` — sem conexão com essas tabelas.
- O Postgres continua sob `profiles: [events]` — não sobe por padrão.

## 3. Ordem futura de aplicação

| Ordem | Arquivo | Finalidade |
|---|---|---|---|
| 1 | `app/infrastructure/event_store/sql/001_create_event_store_events.sql` | Base: Event Log existente (já aplicado em ambiente de teste) |
| 2 | `002_create_outbox_events.sql` | Cria tabela `outbox_events` (fila de dispatch transacional) |
| 3 | `003_create_processed_events.sql` | Cria tabela `processed_events` (idempotência por consumer) |
| 4 | `004_create_outbox_dlq.sql` | Cria tabela `outbox_dlq` (dead-letter queue separada) |
| 5 | `005_create_outbox_recovery_audit.sql` | Cria tabela `outbox_recovery_audit` (auditoria append-only para operações de recovery) |

- `001` é a base conceitual do Event Store já existente. **Não re-aplicar** em ambiente produtivo.
- `002` cria a outbox transacional com campos para retry, locking e auditoria.
- `003` garante dedup de eventos por consumer (idempotência).
- `004` armazena eventos que esgotaram tentativas de dispatch (DLQ).
- `005` cria a tabela de auditoria append-only para operações de recovery.

Cada DDL pode ser aplicado isoladamente. Não há FK física entre tabelas.

## 4. Responsabilidade de cada tabela

### `event_store_events` (herdado — `001_create_event_store_events.sql`)

- Armazena **eventos** por stream (`stream_id`).
- Mantém `UNIQUE(stream_id, stream_version)` — garantia de append ordenado.
- **Não** recebe colunas de dispatch, retry, locking ou DLQ.
- **Não** é a fonte de verdade do estado do sistema (veja seção 33 do AGENTS.md).

### `outbox_events` (`002_create_outbox_events.sql`)

- Armazena eventos **pendentes de dispatch** futuro.
- Suporta **retry** (`attempts`, `max_attempts`, `available_at`, `last_error`, `last_error_class`).
- Suporta **lock concorrente** futuro (`locked_by`, `locked_until`).
- Suporta **auditoria** (`created_at`, `updated_at`, `dispatched_at`, `dead_lettered_at`).
- Usa `UNIQUE(event_id)` — previne duplicação.
- **Não** usa status `failed` (ver seção 5).

### `processed_events` (`003_create_processed_events.sql`)

- Garante **idempotência por consumer**.
- Usa `PRIMARY KEY (consumer_name, event_id)` — cada consumer tem namespace próprio.
- **Não** assume exactly-once — máximo realista é at-least-once com dedup.
- Permite investigação: `event_type`, `stream_id`, `stream_version`, `outbox_id`, `handler_name`.

### `outbox_dlq` (`004_create_outbox_dlq.sql`)

- Armazena eventos que **esgotaram tentativas** de dispatch.
- É **tabela separada** — não mistura com outbox principal.
- Usa `UNIQUE(outbox_id)` — 1 evento = 1 entrada na DLQ.
- Mantém snapshot do payload original (`event_payload`), estado final (`final_error`, `final_error_class`), e histórico de tentativas (`attempts`, `max_attempts`).

## 5. Estados da outbox

Estados persistentes na tabela `outbox_events`:

| Estado | Significado |
|---|---|
| `pending` | Aguardando dispatcher. Disponível para lock. |
| `locked` | Em processamento por um worker. Lock ativo. |
| `dispatched` | Despachado com sucesso. Terminal feliz. |
| `dead_letter` | Tentativas esgotadas. Movido para `outbox_dlq`. |

**`failed` NÃO é estado persistente.** A falha retentável é representada por:
- `status = 'pending'`
- `attempts` incrementado
- `available_at` no futuro (backoff)
- `last_error` e `last_error_class` preenchidos

Após `attempts >= max_attempts`, o evento é movido para `dead_letter` (INSERT em `outbox_dlq` + UPDATE status).

## 6. O que este diretório NÃO faz

- **Não** ativa Postgres no `/chat`.
- **Não** cria dispatcher.
- **Não** cria worker.
- **Não** implementa Event Sourcing completo.
- **Não** altera a `conversation_saga.py`.
- **Não** aplica SQL automaticamente.
- **Não** define secrets.
- **Não** substitui migrations futuras.
- **Não** altera `docker-compose.yaml` ou `.env`.
- **Não** altera `EventStore` ou `EventPublisher` Protocols.

## 7. Validação futura

A validação real em Postgres local/efêmero será feita em ciclo separado. A validação deve verificar:

- Tabelas existentes (`event_store_events`, `outbox_events`, `processed_events`, `outbox_dlq`).
- Constraints (CHECK, UNIQUE, PK).
- Índices (≥16 no total: 4 em `event_store_events`, 5 em `outbox_events`, 5 em `processed_events`, 6 em `outbox_dlq`).
- Idempotência: rodar os scripts 2 vezes sem erro.
- Ausência de impacto no runtime (`/chat` continua usando `InMemoryEventStore()`).

**Comandos de referência** (não executar automaticamente):

```bash
# Subir Postgres efêmero
docker compose --profile events up -d event_store_postgres

# Aplicar schema em ordem
psql "$EVENT_STORE_POSTGRES_DSN" -f db/edd/002_create_outbox_events.sql
psql "$EVENT_STORE_POSTGRES_DSN" -f db/edd/003_create_processed_events.sql
psql "$EVENT_STORE_POSTGRES_DSN" -f db/edd/004_create_outbox_dlq.sql

# Parar Postgres
docker compose --profile events down
```

## 8. Governança

- Alterações neste diretório devem ser feitas por **tarefa aprovada** (`/implement`).
- Cada SQL deve ser criado e validado **isoladamente**.
- Runtime só pode ser conectado em ciclo futuro **explicitamente aprovado**.
- Não executar scripts SQL sem decisão explícita do usuário.
- Não commitar secrets em nenhum arquivo deste diretório.

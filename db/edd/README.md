# `db/edd/` — Schema EDD (Event Driven Design com Postgres)

> **Status: implementado.** O Event Driven Design com Postgres está funcional e validado por testes E2E.
> Para arquitetura, consulte `db/edd/ARCHITECTURE.md`.
> Para operação, consulte `db/edd/RUNBOOK.md`.

---

## Schemas

O bloco EDD utiliza **5 tabelas**. Cada DDL é idempotente (`CREATE TABLE IF NOT EXISTS`).

| Ordem | Arquivo | Tabela | Finalidade |
|---|---|---|---|
| 001 | `app/infrastructure/event_store/sql/001_create_event_store_events.sql` | `event_store_events` | Event Log append-only com `UNIQUE(stream_id, stream_version)` |
| 002 | `db/edd/002_create_outbox_events.sql` | `outbox_events` | Fila de dispatch com status, retry, locking e auditoria |
| 003 | `db/edd/003_create_processed_events.sql` | `processed_events` | Idempotência por consumer — `PRIMARY KEY (consumer_name, event_id)` |
| 004 | `db/edd/004_create_outbox_dlq.sql` | `outbox_dlq` | Dead-letter queue separada com snapshot do payload final |
| 005 | `db/edd/005_create_outbox_recovery_audit.sql` | `outbox_recovery_audit` | Auditoria append-only de operações de recovery |

## Como o `/chat` usa EDD

Quando `EVENT_DRIVEN_ENABLED=true` e `EVENT_STORE_BACKEND=transactional_postgres`, o endpoint `/chat` publica eventos em `event_store_events` e `outbox_events` em uma única transação Postgres. O `OutboxDispatcher` (one-shot ou worker) posteriormente consome eventos da outbox para processamento assíncrono (ex: salvar memória de conversa).

Sem EDD habilitado, o `/chat` funciona sem Postgres (fallback produtivo: `NullEventPublisher`).

## Documentos relacionados

| Documento | Conteúdo |
|---|---|
| `db/edd/ARCHITECTURE.md` | Arquitetura EDD: fluxo, componentes, decisões, limitações |
| `db/edd/RUNBOOK.md` | Operação: schema, dispatcher, worker, inspect, recovery |

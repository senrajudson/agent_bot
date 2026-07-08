# EDD Schema — Event Driven Design com Postgres

> **A arquitetura EDD atual está documentada em `db/edd/ARCHITECTURE.md`.**
> **A operação do sistema está documentada em `db/edd/RUNBOOK.md`.**
>
> Este documento é uma referência curta dos schemas SQL utilizados.

---

## Schemas

| Ordem | Arquivo | Tabela | Finalidade |
|---|---|---|---|
| 001 | `app/infrastructure/event_store/sql/001_create_event_store_events.sql` | `event_store_events` | Event Log append-only com `UNIQUE(stream_id, stream_version)` |
| 002 | `db/edd/002_create_outbox_events.sql` | `outbox_events` | Fila de dispatch com status, retry, locking e auditoria |
| 003 | `db/edd/003_create_processed_events.sql` | `processed_events` | Idempotência por consumer — `PRIMARY KEY (consumer_name, event_id)` |
| 004 | `db/edd/004_create_outbox_dlq.sql` | `outbox_dlq` | Dead-letter queue separada com snapshot do payload final |
| 005 | `db/edd/005_create_outbox_recovery_audit.sql` | `outbox_recovery_audit` | Auditoria append-only de operações de recovery (com trigger `BEFORE UPDATE OR DELETE`) |

Todas as DDLs são idempotentes (`CREATE TABLE IF NOT EXISTS`). Não há FK física entre as tabelas — a integridade é mantida pela aplicação.

## Documentos relacionados

| Documento | Conteúdo |
|---|---|
| `db/edd/ARCHITECTURE.md` | Arquitetura EDD: fluxo, componentes, decisões |
| `db/edd/RUNBOOK.md` | Operação: schema, dispatcher, worker, inspect, recovery |
| `db/edd/README.md` | Índice do diretório `db/edd/` |

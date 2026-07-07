# Runbook — Outbox, Retry e DLQ

## 1. Objetivo

Descrever operacionalmente a outbox transacional do Agent Bot: como identificar pendências, como inspecionar DLQ e quais cuidados tomar com dados sensíveis.

## 2. Visão geral da outbox

A outbox é gravada em `event_store_events` e `outbox_events` em uma única transação no `TransactionalPostgresEventStore`. O dispatcher one-shot (`scripts/run_outbox_dispatcher_once.py`) consome `outbox_events` com `SELECT ... FOR UPDATE SKIP LOCKED`, executa o handler via `EventTypeRouterConsumer`, registra sucesso em `processed_events` ou move o evento para `outbox_dlq` após `max_attempts`.

## 3. Tabelas envolvidas

| Tabela | Propósito |
|---|---|
| `event_store_events` | Log append-only de Domain Events |
| `outbox_events` | Fila durável com status, tentativas, locks e erro |
| `processed_events` | Registro de idempotência por `(consumer_name, event_id)` |
| `outbox_dlq` | Snapshot integral do evento na última falha. **DADO SENSÍVEL** |

## 4. Status de `outbox_events`

| Status | Significado |
|---|---|
| `pending` | Pronto para ser reivindicado pelo dispatcher |
| `locked` | Em processamento por um worker (lock ativo com TTL) |
| `dispatched` | Processado com sucesso; `processed_events` tem a linha |
| `dead_letter` | Excedeu `max_attempts`; snapshot em `outbox_dlq` |

## 5. `processed_events` e idempotência

Chave primária lógica: `(consumer_name, event_id)`. Mecanismo `ON CONFLICT DO NOTHING` garante que o consumer não seja chamado duas vezes para o mesmo evento. Antes de executar o consumer, o dispatcher verifica `is_processed()` — se já existe linha, o evento é marcado como `dispatched` sem executar o handler novamente.

## 6. `outbox_dlq` e dados sensíveis

`outbox_dlq` persiste `event_payload` integral por design atual do `PostgresOutboxStore.move_to_dlq()`. **Tratar como armazenamento sensível.** Não expor conteúdo em logs públicos, dashboards ou relatórios sem redação. Política de retenção/expurgo é decisão futura (ver seção 11).

## 7. Exit codes do CLI

`scripts/run_outbox_dispatcher_once.py` retorna:

| Código | Nome | Significado |
|---|---|---|
| 0 | OK | Sucesso, sem retry nem DLQ |
| 1 | ARGS | Falha ao serializar resultado como JSON |
| 2 | GATE | `OUTBOX_DISPATCHER_ENABLED != true` ou DSN ausente/inválido |
| 3 | CONFIG | Schema ausente (`outbox_events` não encontrada) ou configuração do banco |
| 4 | RESULT_FAIL | Dispatch executou, mas houve retry ou DLQ |
| 5 | STORE | Falha no pool asyncpg ou em `dispatch_once` |

## 8. Como inspecionar pendências

Conceitual — exemplos de SELECT de leitura (não destrutivos):

```sql
-- Eventos com erro pendentes de retry
SELECT outbox_id, event_type, attempts, last_error_class, last_error, updated_at
FROM outbox_events
WHERE status = 'pending' AND last_error IS NOT NULL
ORDER BY updated_at DESC
LIMIT 50;

-- Eventos locked há mais tempo que o TTL
SELECT outbox_id, locked_by, locked_until, NOW() - locked_until AS expired_ago
FROM outbox_events
WHERE status = 'locked' AND locked_until < NOW()
ORDER BY locked_until ASC;
```

## 9. Como inspecionar DLQ

Conceitual — exemplos de SELECT de leitura:

```sql
-- Listar snapshots da DLQ
SELECT outbox_id, event_id, event_type, final_error_class, attempts, max_attempts, moved_to_dlq_at
FROM outbox_dlq
ORDER BY moved_to_dlq_at DESC
LIMIT 50;
```

## 10. Cuidados com payload e `last_error`

- `event_payload` em `outbox_dlq` pode conter `user_message` e `assistant_message` em texto claro. **Não expor.**
- `last_error` em `outbox_events` e `final_error` em `outbox_dlq` são **sanitizados** automaticamente pelo helper `app/infrastructure/outbox/_error_redaction.py` antes da persistência (Prompt 19). Valores de `user_message`, `assistant_message`, `token`, `password`, `passwd`, `secret`, `api_key`, `authorization` e `Bearer` são redigidos como `<REDACTED>`. `last_error_class` e `final_error_class` preservam a classe original da exceção.
- Logs do `ConversationMemorySaveOutboxHandler`, do `LoggingOutboxConsumer` e do `OutboxDispatcher` foram verificados e não vazam `user_message`/`assistant_message`/`event_payload` (Prompts 18 e 19).
- `OutboxDispatcher` emite logs estruturados seguros:
  - `WARNING outbox_event_retry_scheduled` — evento re-agendado para retry.
  - `ERROR outbox_event_dead_lettered` — evento movido para DLQ.
  - Campos seguros: `event_id`, `event_type`, `consumer_name`, `attempts`, `max_attempts`, `action`, `error_class`, `sanitized_error` (máx. 512 chars). Sem `event_payload`, sem `user_message`, sem `assistant_message`, sem `logger.exception`.
- `event_payload` em `outbox_dlq` continua snapshot integral por design do schema. **Não expor.**

## 11. Retenção de DLQ, recovery e inspeção

> **Prompt 20**: Este ciclo implementou política formal de retenção, bloqueio de recovery
> e script read-only de inspeção. Nenhuma operação destrutiva foi implementada.

### 11a. Política de retenção de `outbox_dlq`

| Ambiente | Prazo de referência |
|---|---|
| Local / QA | **30 dias** como referência. Sem purge automático. |
| Produção | Decisão futura. Depende de compliance, auditoria e política de dados. |

- `outbox_dlq.event_payload` contém snapshot integral de `user_message`/`assistant_message`.
  **Tratar como PII.** Não copiar payload em tickets, logs ou dashboards.
- **Não há** script de purge neste ciclo. Exclusão de registros antigos é manual e só deve ser
  executada após aprovação explícita, com backup prévio e registro em ticket.

### 11b. Política de recovery

> **Recovery está bloqueado neste ciclo.**

Regras:
- **Não** reprocessar eventos com `event_type = ConversationMemorySaveRequested`.
- **Não** recolocar `dead_letter` como `pending`.
- **Não** limpar `processed_events`.
- **Não** usar novo `consumer_name` para replay.
- **Não** criar novo `event_id`.
- **Não** executar `UPDATE` em `outbox_events` para forçar reprocessamento.
- **Não** executar `DELETE` em `outbox_dlq` para permitir re‑INSERT.

Motivo:
`ConversationMemorySaveOutboxHandler` **não possui idempotência de negócio**:
`append_memory_turns` faz `rpush` no Redis sem dedup. Reprocessar o mesmo evento
duplica o turn na memória de conversa, poluindo o histórico e inflando tokens.

Pré‑condições para reabertura de recovery (todas obrigatórias):

1. Handler idempotente de negócio (ex.: `SET NX` por `event_id`, ou `LPOS` antes de `rpush`).
2. Dedupe key por `event_id` ou `turn_id`.
3. Operação de memória idempotente.
4. Allowlist por `event_type`.
5. Dry‑run obrigatório antes de qualquer recovery real.
6. Confirmação explícita do operador.
7. Auditoria da operação manual (registro em ticket/issue).

### 11c. Auditoria manual

Não há tabela de auditoria neste ciclo. Operações manuais devem ser registradas em ticket/issue:

```text
Data: YYYY-MM-DD
Operador: nome
Ação: inspeção / análise / (futuro: purge / recovery)
Tabela: outbox_events / outbox_dlq
Filtros: event_id, outbox_id, event_type
Motivo: ...
```

### 11d. Glossário

| Termo | Significado |
|---|---|
| `dead_letter` | Status terminal de `outbox_events`. Evento excedeu `max_attempts`. |
| `outbox_dlq` | Tabela separada que armazena snapshot do evento na falha terminal. |
| `retry` | Reagendamento automático com backoff exponencial (`mark_retry`). |
| `recovery` | (Bloqueado) Ação manual de recolocar evento como `pending`. |
| `replay` | (Bloqueado) Reexecução de evento para reconstruir estado. |
| `purge` | (Futuro exclusão manual de registros antigos. |

### 11e. Script read-only `inspect_outbox.py`

**Localização**: `scripts/inspect_outbox.py`

**Função**: Inspecionar estado da outbox e DLQ sem alterar dados.

**Subcomandos**:

| Subcomando | Alvo | Ordenação |
|---|---|---|
| `outbox-pending` | `outbox_events` com `status='pending'` | `available_at ASC, outbox_id ASC` |
| `outbox-locked` | `outbox_events` com `status='locked'` | `locked_until ASC, outbox_id ASC` |
| `outbox-dlq` | `outbox_dlq` | `moved_to_dlq_at DESC, outbox_id DESC` |

**DSN**: variável de ambiente `EVENT_STORE_POSTGRES_DSN`. Apenas `127.0.0.1` ou `localhost`.
**Gate**: não exige `OUTBOX_DISPATCHER_ENABLED`. O script funciona mesmo com EDD off.

**Flags compartilhadas**:

| Flag | Efeito |
|---|---|
| `--event-type TYPE` | Filtra por `event_type` |
| `--since YYYY-MM-DD` | Filtra a partir da data (ISO 8601, coluna variável por subcomando) |
| `--outbox-id ID` | Filtra por `outbox_id` |
| `--conversation-id CID` | Filtra por `aggregate_id` (não consulta `event_payload`) |
| `--limit N` | Máximo de linhas (default 50, max 500) |
| `--json` | Saída em JSON único no lugar de tabela texto |
| `--show-sanitized-error` | Exibe `last_error`/`final_error` sanitizados (truncado a 200 chars) |
| `--with-error` | (apenas `outbox-pending`) Filtra só pendências com erro retentável |

**Exit codes**:

| Código | Nome | Significado |
|---|---|---|
| 0 | OK | Consulta executada com sucesso |
| 1 | ARGS | Argumentos CLI inválidos |
| 2 | DSN | DSN ausente ou não‑local |
| 3 | SCHEMA | Schema/tabela ausente (execute `scripts/apply_edd_schema.sh --apply`) |
| 4 | QUERY | Erro de conexão ou query |

**Regras de segurança**:
- Apenas `SELECT`. Sem `UPDATE/DELETE/INSERT/TRUNCATE`.
- `event_payload`, `metadata`, `user_message`, `assistant_message` jamais selecionados.
- `conversation_id`/`user_id` jamais expostos na saída.
- DSN bruto jamais impresso; formato redigido: `postgresql://[REDACTED]@host:port/db`.
- `--show-sanitized-error` reusa `sanitize_error_message` para redação de PII.

**Exemplos**:

```bash
# Listar pendências com erro
python scripts/inspect_outbox.py outbox-pending --with-error --limit 10

# Listar DLQ com erro sanitizado
python scripts/inspect_outbox.py outbox-dlq --limit 20 --show-sanitized-error

# Listar locked para debugging
python scripts/inspect_outbox.py outbox-locked --since 2026-07-01

# Saída JSON
python scripts/inspect_outbox.py outbox-pending --json --limit 5
```

### 11f. Histórico

> A seção 11 original (Prompts 12–19) marcava retenção como "decisão futura".
> A partir do Prompt 20, a política está definida nas seções 11a–11e.
> Esta subseção existe apenas para rastreabilidade e será removida em Prompt futuro.

## 12. O que não fazer manualmente

- **Não** executar `UPDATE` ou `DELETE` em `outbox_events` para forçar reprocessamento. O `is_processed` check impede reexecução pelo dispatcher.
- **Não** executar `UPDATE` em `processed_events`. O `ON CONFLICT DO NOTHING` protege idempotência.
- **Não** executar `TRUNCATE` em qualquer das 4 tabelas sem backup e aprovação.
- **Não** executar `INSERT` manual em `outbox_events` para "replay" — usar o caminho de reemissão de evento pela saga.
- **Não** expor `outbox_dlq.event_payload` em logs, dashboards ou relatórios.
- **Não** executar recovery manual: `ConversationMemorySaveRequested` não pode ser reprocessado (handler não idempotente). Veja seção 11b.
- **Não** executar purge manual: decisão futura. Veja seção 11a.
- **Não** executar replay manual: bloqueado até recovery ser reaberto (seção 11b).

## 13. Fora do escopo

- Worker contínuo (não existe; CLI é one-shot)
- Replay automático de `outbox_dlq` (não existe; decisão futura)
- Purge automático de `outbox_dlq` (não existe; decisão futura)
- Tabela de auditoria de operações manuais (não existe; registre em ticket/issue — seção 11c)

## 14. Próximos prompts possíveis

- Purge de `outbox_dlq` com dry-run (após política de retenção estar madura)
- Recovery de `outbox_dlq` com dry-run (após handler real ser idempotente de negócio)
- Mecanismo de injeção de falha no CLI para validação live

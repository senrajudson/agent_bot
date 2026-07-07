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

## 11. Retenção de DLQ pendente

Política de retenção/expurgo de `outbox_dlq` é **decisão futura**. Não há job de purge, não há SQL de expurgo, não há rotina de limpeza. Não criar script de retenção sem aprovação explícita.

## 12. O que não fazer manualmente

- **Não** executar `UPDATE` ou `DELETE` em `outbox_events` para forçar reprocessamento. O `is_processed` check impede reexecução pelo dispatcher.
- **Não** executar `UPDATE` em `processed_events`. O `ON CONFLICT DO NOTHING` protege idempotência.
- **Não** executar `TRUNCATE` em qualquer das 4 tabelas sem backup e aprovação.
- **Não** executar `INSERT` manual em `outbox_events` para "replay" — usar o caminho de reemissão de evento pela saga.
- **Não** expor `outbox_dlq.event_payload` em logs, dashboards ou relatórios.

## 13. Fora do escopo

- Worker contínuo (não existe; CLI é one-shot)
- Replay automático de `outbox_dlq` (não existe; decisão futura)
- Purge automático de `outbox_dlq` (não existe; decisão futura)

## 14. Próximos prompts possíveis

- Política de retenção/expurgo de `outbox_dlq`
- Mecanismo de injeção de falha no CLI para validação live

# EDD Prompt 14 — Ativação Controlada do Outbox Dispatcher (CLI One-Shot)

> **Status**: Runbook operacional. Não executa nada automaticamente.
> **Ciclo**: Prompt 14 — CLI one-shot `scripts/run_outbox_dispatcher_once.py`.
> **Pré-requisito**: Prompt 12/13 concluído (Postgres rodando, schema 001–004 aplicado, `/chat` gerou eventos com `status='pending'`).

---

## 1. Objetivo

Processar **um único batch** de `outbox_events` com `status='pending'` usando o `OutboxDispatcher` + `LoggingOutboxConsumer` reais, via CLI one-shot manual.

```
scripts/run_outbox_dispatcher_once.py
→ PostgresOutboxStore (pool próprio asyncpg)
→ OutboxDispatcher.dispatch_once
→ LoggingOutboxConsumer (log-only, metadados)
→ outbox_events.status='dispatched'
→ processed_events + 1 linha
```

Sem worker contínuo. Sem loop. Sem background task. Sem alteração de `lifespan`/`main.py`/schema/compose.

---

## 2. Pré-condições

| Item | Como verificar |
|---|---|
| Postgres `event_store_postgres` rodando | `docker compose --profile events ps` |
| Schema 001–004 aplicado | `bash scripts/smoke_chat_event_driven.sh --validate-schema` |
| `EVENT_STORE_POSTGRES_DSN` exportado | `echo "$EVENT_STORE_POSTGRES_DSN"` |
| `OUTBOX_DISPATCHER_ENABLED=true` exportado | `echo "$OUTBOX_DISPATCHER_ENABLED"` |
| ≥1 evento `pending` em `outbox_events` | `psql "$EVENT_STORE_POSTGRES_DSN" -c "SELECT count(*) FROM outbox_events WHERE status='pending'"` |
| Ambiente local/QA **dedicado** | **Nunca usar DSN de produção** |

---

## 3. Avisos de segurança

| Aviso | Explicação |
|---|---|
| **Banco dedicado** | Use apenas banco local/QA. **Nunca usar DSN de produção.** |
| **One-shot** | O CLI processa **um** batch e encerra. Não cria worker, não altera runtime. |
| **Não commitar DSN** | A senha no DSN não deve ser versionada. |
| **Sem script bash** | Este runbook não cria script bash; a operação é manual + CLI Python. |

---

## 4. Variáveis de ambiente

Exporte no shell **antes** de executar o CLI:

```bash
export OUTBOX_DISPATCHER_ENABLED=true
export EVENT_STORE_POSTGRES_DSN="postgresql://agent_bot:change_me_event_store@127.0.0.1:5433/agent_bot_events"
```

O CLI lê `OUTBOX_DISPATCHER_ENABLED` via `os.environ` direto (não usa Pydantic Settings).
Se ausente ou diferente de `"true"`, o CLI retorna exit 2 sem processar nada.

---

## 5. Executar o CLI

```bash
poetry run python scripts/run_outbox_dispatcher_once.py
```

Com flags customizadas:

```bash
poetry run python scripts/run_outbox_dispatcher_once.py \
  --batch-size 10 \
  --consumer-name meu-consumer \
  --worker-id worker-1
```

### Flags

| Flag | Default | Descrição |
|---|---|---|
| `--batch-size` | `10` | Número máximo de eventos por batch |
| `--consumer-name` | `outbox-logging-default` | Identificador do consumer (usado em `processed_events`) |
| `--worker-id` | auto-gerado | Identificador do worker para lock |

### Saída esperada (stdout JSON)

```json
{
  "claimed_count": 8,
  "processed_count": 8,
  "already_processed_count": 0,
  "dispatched_count": 8,
  "retry_count": 0,
  "dlq_count": 0
}
```

Logs operacionais vão para **stderr**.

---

## 6. Exit codes

| Código | Significado |
|---|---|
| `0` | Execução concluída sem erro (inclusive `claimed_count=0`) |
| `1` | Argumentos inválidos ou falha de serialização JSON |
| `2` | Gate `OUTBOX_DISPATCHER_ENABLED` ausente/≠`true`, ou DSN ausente/inválido/não-local |
| `3` | Schema ausente (tabela `outbox_events` não encontrada) |
| `4` | `dispatch_once` executou, mas `retry_count > 0` ou `dlq_count > 0` |
| `5` | Erro inesperado de pool/`dispatch_once`/asyncpg |

### Regras

- `claimed_count=0` não é erro (exit 0).
- `already_processed_count > 0` não é erro (exit 0).
- Erros de `store.*` (D23–D30) propagam como exit 5.
- Erros de `consumer.handle` são capturados pelo `OutboxDispatcher` e viram retry/DLQ (exit 4).

---

## 7. Validação pós-execução

### 7.1. Verificar status `dispatched`

```bash
psql "$EVENT_STORE_POSTGRES_DSN" -c "
SELECT status, count(*) AS n
FROM outbox_events ob
JOIN event_store_events es ON es.event_id = ob.event_id
WHERE es.stream_id = 'conversation:edd-smoke-user'
GROUP BY status;
"
```

Esperado: apenas `dispatched`.

### 7.2. Verificar `processed_events`

```bash
psql "$EVENT_STORE_POSTGRES_DSN" -c "
SELECT consumer_name, count(*) AS n
FROM processed_events
GROUP BY consumer_name;
"
```

Esperado: ≥1 linha com `consumer_name` do CLI.

### 7.3. Verificar idempotência

Execute o CLI **novamente** com o mesmo `--consumer-name`:

```bash
poetry run python scripts/run_outbox_dispatcher_once.py
```

Esperado: `already_processed_count > 0`, `processed_count = 0`, exit 0.

---

## 8. Cleanup

Para limpar os dados processados (referência ao Prompt 12):

```bash
bash scripts/smoke_chat_event_driven.sh --cleanup --yes
```

Isso executa `TRUNCATE` nas 4 tabelas de eventos (`event_store_events`, `outbox_events`, `processed_events`, `outbox_dlq`).

**Aviso**: Destrutivo. Só em banco local/QA.

---

## 9. Fora de escopo

O Prompt 14 **não** cria, ativa ou gerencia:

- Loop contínuo, worker, scheduler, daemon
- Background task no FastAPI
- Dispatcher em `app.state`
- Alteração de `lifespan.py`, `app/main.py`, `app/core/config.py`
- Alteração de schema SQL, `docker-compose.yaml`, `.env`
- Consumer com side effect externo (HTTP, Redis, Kafka, Pub/Sub)
- Read model persistente, projection complexa, DLQ processor
- Novo script bash de smoke
- Integração com n8n

---

## 10. Solução de problemas

| Erro | Causa provável | Solução |
|---|---|---|
| `OUTBOX_DISPATCHER_ENABLED must be 'true'` | Variável não exportada ou ≠ `true` | Exportar `OUTBOX_DISPATCHER_ENABLED=true` |
| `EVENT_STORE_POSTGRES_DSN is not set` | DSN não exportado | Exportar DSN local |
| `DSN inválido ou não-local` | DSN aponta para outro host | Usar `127.0.0.1` ou `localhost` |
| `tabela outbox_events não encontrada` | Schema não aplicado | `bash scripts/smoke_chat_event_driven.sh --apply-schema` |
| `Falha ao criar pool asyncpg` | Postgres não está rodando | `docker compose --profile events up -d event_store_postgres` |
| `exit 4` com `retry_count > 0` | Consumer falhou | Verificar logs em stderr; o dispatcher aplicou retry automático |
| `exit 4` com `dlq_count > 0` | Esgotou tentativas do consumer | Verificar `outbox_dlq` e logs |

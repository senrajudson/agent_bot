# EDD Prompt 12 — Smoke Test: Validação Operacional Controlada do `/chat` com Postgres

> **Status**: Runbook operacional. Não executa nada automaticamente.
> **Ciclo**: Prompt 12 — runbook + script auxiliar.
> **Próximo ciclo**: `/validate` para execução real.

---

## 1. Objetivo

Validar, em ambiente local/QA controlado, o caminho completo:

```
POST /chat
→ build_runtime_event_publisher
→ EventPublisherImpl
→ TransactionalPostgresEventStore
→ event_store_events + outbox_events
```

Sem criar dispatcher/worker. Sem alterar código do app. Sem alterar runtime. Sem alterar lifecycle. Sem alterar configuração. A outbox permanece com `status='pending'` porque não há dispatcher.

---

## 2. Pré-condições

| Item | Versão mínima | Como verificar |
|---|---|---|
| Docker + Docker Compose | v2.x | `docker compose version` |
| `psql` | 13+ | `psql --version` |
| `curl` | 7.x+ | `curl --version` |
| Repositório agent_bot | — | `git status` (working tree limpo) |
| Banco `event_store_postgres` rodando | — | Ver passo 5 |
| App local executável | — | `poetry run uvicorn app.main:app --port 8002` |
| Ambiente local/QA **dedicado** | — | **Nunca usar produção** |

---

## 3. Avisos de segurança

| Aviso | Explicação |
|---|---|
| 🔴 Banco dedicado | Este smoke test usa o schema `public` do banco `event_store_postgres`. Use **apenas** um banco local/QA dedicado. **Nunca usar DSN de produção.** |
| 🔴 Cleanup destrutivo | `--cleanup` apaga **todas** as linhas de `event_store_events`, `outbox_events`, `processed_events` e `outbox_dlq`. Só execute com autorização explícita. |
| 🔴 Não commitar DSN | As variáveis de ambiente com senha não devem ser versionadas. |
| 🔴 Sem dispatcher | Os eventos ficam com `status='pending'` permanentemente. Isso é esperado. |

---

## 4. Variáveis de ambiente

Exporte no shell **antes** de iniciar o app:

```bash
export EVENT_DRIVEN_ENABLED=true
export EVENT_STORE_BACKEND=transactional_postgres
export EVENT_STORE_POSTGRES_DSN="postgresql://agent_bot:change_me_event_store@127.0.0.1:5433/agent_bot_events"
```

**Regras**:
- Não alterar `.env`.
- Não alterar `.env.example`.
- Não commitar senha.
- Não usar DSN de produção.
- O script `smoke_chat_event_driven.sh` lê `EVENT_STORE_POSTGRES_DSN` do ambiente.

---

## 5. Subir Postgres local/QA

```bash
docker compose --profile events up -d event_store_postgres
```

Opcional — verificar healthcheck:

```bash
docker compose --profile events exec event_store_postgres pg_isready -U agent_bot -d agent_bot_events
```

Esperado: `127.0.0.1:5432 - accepting connections`.

Porta mapeada: `127.0.0.1:5433 → 5432` (definido em `docker-compose.yaml`).

---

## 6. Aplicar schema

```bash
bash scripts/smoke_chat_event_driven.sh --apply-schema
```

Esse comando chama `scripts/apply_edd_schema.sh --apply`, que aplica os 4 scripts SQL (001–004) em ordem no banco apontado por `EVENT_STORE_POSTGRES_DSN`. Os DDLs são idempotentes (`CREATE TABLE IF NOT EXISTS`).

---

## 7. Validar schema

```bash
bash scripts/smoke_chat_event_driven.sh --validate-schema
```

Esse comando chama `scripts/validate_edd_schema.sh --validate`, que executa **apenas SELECTs** para verificar tabelas, colunas, constraints e índices.

---

## 8. Iniciar app local com flags

Com as variáveis de ambiente **já exportadas** (passo 4), inicie o app:

```bash
poetry run uvicorn app.main:app --port 8002
```

Verifique no log a presença de:

```
EventStore EDD: pool created (min_size=1, max_size=4)
```

Isso confirma que o gate G3 foi ativado com sucesso.

---

## 9. Executar smoke `/chat`

Com o app rodando, execute o smoke:

```bash
bash scripts/smoke_chat_event_driven.sh --smoke
```

Esse comando faz `POST http://127.0.0.1:8002/chat` com o payload:

```json
{
  "message": "Responda apenas: smoke ok",
  "user_id": "edd-smoke-user"
}
```

Esperado: HTTP `200` + resposta JSON com `ok=true`.

---

## 10. Validar eventos

```bash
bash scripts/smoke_chat_event_driven.sh --validate-events
```

Esse comando executa as 12 checagens de sucesso contra o banco (ver seção 11 e 12).

---

## 11. Queries SQL de validação

Todas as queries são **read-only** (SELECT). Use o DSN exportado em `EVENT_STORE_POSTGRES_DSN`.

### 11.1. Contagem de eventos do smoke no Event Store

```sql
SELECT count(*) AS n
FROM event_store_events
WHERE stream_id = 'conversation:edd-smoke-user';
```

Esperado: `n >= 1`.

### 11.2. Lista recente de eventos por stream

```sql
SELECT event_id, event_type, stream_version, occurred_at
FROM event_store_events
WHERE stream_id = 'conversation:edd-smoke-user'
ORDER BY stream_version ASC
LIMIT 50;
```

Esperado: ≥ 1 linha.

### 11.3. Join `event_store_events` × `outbox_events` por `event_id`

```sql
SELECT es.event_id, es.event_type, ob.status, ob.attempts, ob.max_attempts
FROM event_store_events es
JOIN outbox_events ob ON ob.event_id = es.event_id
WHERE es.stream_id = 'conversation:edd-smoke-user'
ORDER BY es.stream_version ASC;
```

Esperado: ≥ 1 linha, com `status='pending'`, `attempts=0`, `max_attempts=3`.

### 11.4. Contagem por status da outbox

```sql
SELECT status, count(*) AS n
FROM outbox_events ob
JOIN event_store_events es ON es.event_id = ob.event_id
WHERE es.stream_id = 'conversation:edd-smoke-user'
GROUP BY status;
```

Esperado: apenas `pending`.

### 11.5. Validação de `attempts` e `max_attempts`

```sql
SELECT
  count(*) FILTER (WHERE ob.attempts = 0)       AS attempts_zero,
  count(*) FILTER (WHERE ob.max_attempts = 3)   AS max_attempts_three,
  count(*)                                       AS total
FROM outbox_events ob
JOIN event_store_events es ON es.event_id = ob.event_id
WHERE es.stream_id = 'conversation:edd-smoke-user';
```

Esperado: `attempts_zero = total` **E** `max_attempts_three = total`.

### 11.6. `processed_events` permanece vazio

```sql
SELECT count(*) AS n FROM processed_events;
```

Esperado: `n = 0`.

### 11.7. `outbox_dlq` permanece vazio

```sql
SELECT count(*) AS n FROM outbox_dlq;
```

Esperado: `n = 0`.

### 11.8. Atomicidade: mesmo `event_id` em ambas as tabelas

```sql
SELECT
  count(*) FILTER (WHERE ob.event_id IS NOT NULL) AS with_outbox,
  count(*)                                          AS total
FROM event_store_events es
LEFT JOIN outbox_events ob ON ob.event_id = es.event_id
WHERE es.stream_id = 'conversation:edd-smoke-user';
```

Esperado: `with_outbox = total`.

---

## 12. Resultado esperado

| # | Critério | Como validar | Esperado |
|---|---|---|---|
| 1 | `/chat` HTTP 200 | `curl -w '%{http_code}'` | `200` |
| 2 | Resposta mantém envelope | `jq .ok` da resposta | `true` |
| 3 | Log R4 presente | `grep 'event=event_publisher_created_transactional'` | ≥ 1 hit |
| 4 | `event_store_events` ≥ 1 para o stream | §11.1 | `n >= 1` |
| 5 | `outbox_events` ≥ 1 para os `event_id` | §11.3 | todas com outbox |
| 6 | Join válido por `event_id` | §11.3 | `ob.event_id IS NOT NULL` |
| 7 | `status='pending'` | §11.4 | apenas `pending` |
| 8 | `attempts=0` | §11.5 | `attempts_zero = total` |
| 9 | `max_attempts=3` | §11.5 | `max_attempts_three = total` |
| 10 | `processed_events` vazia | §11.6 | `n = 0` |
| 11 | `outbox_dlq` vazia | §11.7 | `n = 0` |
| 12 | Nenhum dispatcher/worker iniciado | Garantia de escopo | OK |

---

## 13. Cleanup

```bash
bash scripts/smoke_chat_event_driven.sh --cleanup --yes
```

Ou, com variável de ambiente:

```bash
SMOKE_CHAT_YES=1 bash scripts/smoke_chat_event_driven.sh --cleanup
```

SQL executado:

```sql
TRUNCATE TABLE
  event_store_events,
  outbox_events,
  processed_events,
  outbox_dlq
RESTART IDENTITY CASCADE;
```

**Aviso**: Esta operação é **destrutiva**. Remove todos os dados das 4 tabelas. Só execute em banco local/QA dedicado.

---

## 14. Rollback

Se algo falhar durante o smoke, siga os passos abaixo na ordem:

1. **Parar o app local**: `Ctrl+C` no terminal do `uvicorn` ou `kill <PID>`.
2. **Limpar variáveis de ambiente**:
   ```bash
   unset EVENT_DRIVEN_ENABLED
   unset EVENT_STORE_BACKEND
   unset EVENT_STORE_POSTGRES_DSN
   ```
3. **(Opcional) Cleanup de dados**:
   ```bash
   bash scripts/smoke_chat_event_driven.sh --cleanup --yes
   ```
4. **(Opcional) Parar container Postgres**:
   ```bash
   docker compose --profile events down
   ```
   Para apagar o volume (perde todos os dados):
   ```bash
   docker compose --profile events down -v
   ```
5. **Rollback de código**: **Não há.** O Prompt 12 não altera código do app.

---

## 15. Comandos manuais opcionais

| Comando | Descrição |
|---|---|
| `docker compose --profile events down` | Para o container sem apagar volume |
| `docker compose --profile events down -v` | Para o container e apaga volume |
| `docker compose --profile events logs` | Logs do container |
| `docker compose --profile events exec event_store_postgres psql -U agent_bot -d agent_bot_events` | Conexão psql interativa |

---

## 16. Solução de problemas

| Erro | Causa provável | Solução |
|---|---|---|
| `EVENT_STORE_POSTGRES_DSN is not set` | Variável não exportada | Exportar DSN no shell (passo 4) |
| `DSN must point to 127.0.0.1 or localhost` | DSN aponta para outro host | Verificar DSN; só local/QA |
| `psql: not found` (exit 3) | `psql` não instalado | `apt install postgresql-client` |
| `curl: not found` (exit 3) | `curl` não instalado | `apt install curl` |
| `event=event_publisher_created_transactional` ausente no log | G3 não ativado | Verificar env vars; verificar log de startup |
| `pq: password authentication failed` | Senha errada no DSN | Verificar `POSTGRES_PASSWORD` no compose |
| `pq: database "agent_bot_events" does not exist` | Banco não criado | Verificar `POSTGRES_DB` no compose; container pode precisar ser recriado |
| `could not translate host name` | Container não está rodando | `docker compose --profile events ps` |
| HTTP 500 do `/chat` | Erro no fluxo do agente | Verificar log do uvicorn; pode ser LLM provider |
| `outbox_events` vazia | Publisher não gravou | Verificar log R4; se R4 ausente, G3 não ativou |
| `processed_events` não está vazia | Dispatcher rodou por engano | Fora do escopo; não deve acontecer |
| `outbox_dlq` não está vazia | Dispatcher rodou por engano | Fora do escopo; não deve acontecer |

---

## 17. Fora do escopo

O Prompt 12 **não** cria, ativa ou gerencia:

- Dispatcher de outbox
- Worker de eventos
- Consumer de eventos
- Scheduler
- Projection / read models
- Retry loop
- DLQ processor
- Conexão com Kafka ou Pub/Sub
- Alteração de código do app
- Alteração de schema SQL
- CI/CD pipeline

O `TransactionalPostgresEventStore` escreve em ambas as tabelas (`event_store_events` + `outbox_events`), mas **não há dispatcher** para processar a outbox. O `status='pending'` é esperado e terminal neste ciclo.

---

## 18. Próximo ciclo

A execução real (Docker, Postgres, `curl POST /chat`, `psql`) será feita em:

- **`/validate`**: execução controlada com autorização explícita do operador.
- **Manual**: seguindo os passos deste runbook, com autorização explícita.

Após o `/validate`, o prompt estará fechado e o próximo ciclo (se houver) será o dispatcher/worker (Prompt 13+).

---

## Apêndice: scripts e arquivos de referência

| Path | Função |
|---|---|
| `scripts/smoke_chat_event_driven.sh` | Script auxiliar deste runbook |
| `scripts/apply_edd_schema.sh` | Aplica schema 001–004 |
| `scripts/validate_edd_schema.sh` | Valida schema via SELECTs |
| `app/infrastructure/event_store/sql/001_create_event_store_events.sql` | DDL do Event Log |
| `db/edd/002_create_outbox_events.sql` | DDL da outbox |
| `db/edd/003_create_processed_events.sql` | DDL de idempotência |
| `db/edd/004_create_outbox_dlq.sql` | DDL da DLQ |
| `db/edd/README.md` | Governança do schema |
| `docker-compose.yaml` (linhas 72–92) | Definição do `event_store_postgres` |

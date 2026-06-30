# EDD Schema — Event Driven Design com Postgres

> **Status: preparação.** Este documento descreve o schema SQL preparado para o bloco "Event Driven Design com Postgres" do agent_bot. O runtime ainda não foi conectado. O `/chat` permanece intacto. O sistema **não é** Event Sourcing completo.

---

## 1. Resumo

O schema EDD com Postgres prepara infraestrutura para:

- **Outbox** transacional (`outbox_events`) — fila de dispatch com retry, locking e auditoria.
- **Idempotência** por consumer (`processed_events`) — deduplicação segura em at-least-once.
- **Dead-letter queue** (`outbox_dlq`) — eventos que esgotaram tentativas.

O runtime ainda **não** foi conectado. O `/chat` continua usando `InMemoryEventStore()` em `app/agent/orchestrator.py`. O Postgres permanece sob ativação explícita no profile `events` do `docker-compose.yaml`.

Este schema **não transforma** o sistema em Event Sourcing completo. O Event Store continua sendo append-only (não fonte da verdade do estado). O schema prepara o terreno para que um dispatcher futuro possa consumir eventos da outbox de forma segura e idempotente.

## 2. Arquivos do schema

| Arquivo | Local | Finalidade |
|---|---|---|
| `001_create_event_store_events.sql` | `app/infrastructure/event_store/sql/` | Base herdada: Event Log append-only com `UNIQUE(stream_id, stream_version)` |
| `002_create_outbox_events.sql` | `db/edd/` | T-01: Outbox transacional com 22 colunas, retry, locking, auditoria |
| `003_create_processed_events.sql` | `db/edd/` | T-02: Tabela de idempotência por consumer (9 colunas) |
| `004_create_outbox_dlq.sql` | `db/edd/` | T-03: DLQ separada com snapshot do payload final (17 colunas) |

## 3. Scripts auxiliares

| Script | Local | Finalidade |
|---|---|---|
| `apply_edd_schema.sh` | `scripts/` | Aplica os 4 SQLs em ordem (dry-run por padrão, `--apply` para executar) |
| `validate_edd_schema.sh` | `scripts/` | Valida tabelas/colunas/constraints/índices (dry-run por padrão, `--validate` para conectar) |

### Comportamento dos scripts

- Ambos são **manuais** — nenhum é executado automaticamente.
- Ambos exigem `EVENT_STORE_POSTGRES_DSN` apenas no modo real (`--apply` / `--validate`).
- Ambos são dry-run por padrão — sem flag explícita, nada acontece.
- Nenhum deles sobe Docker, cria banco ou carrega `.env`.
- `apply_edd_schema.sh` usa `psql -f` para aplicar cada SQL.
- `validate_edd_schema.sh` usa `psql -Atc` para queries SELECT (read-only).

## 4. Ordem futura de aplicação

| Ordem | Arquivo | Finalidade |
|---|---|---|
| 1 | `001_create_event_store_events.sql` | Base: Event Log existente (não re-aplicar em prod) |
| 2 | `002_create_outbox_events.sql` | Cria a outbox transacional |
| 3 | `003_create_processed_events.sql` | Cria a tabela de idempotência |
| 4 | `004_create_outbox_dlq.sql` | Cria a DLQ separada |

**Por que a ordem é segura**:

- Cada DDL é idempotente (`CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`).
- Não há FK física entre tabelas — ordem é por conveniência, não por dependência de integridade.
- `001` é herdado e pode ser pulado se já aplicado (mas não re-aplicar em prod).
- `002`, `003` e `004` são independentes entre si, mas a ordem lógica (outbox → idempotência → DLQ) segue o fluxo de dados.

## 5. Tabela `event_store_events`

**Local**: `app/infrastructure/event_store/sql/001_create_event_store_events.sql`

**Finalidade**: Armazena eventos por stream (`stream_id`). Cada evento é append-only, com versão incremental por stream.

**Papel de stream e stream_version**:
- `stream_id` identifica o fluxo de eventos (ex: `conversation:user-123`).
- `stream_version` é a versão incremental do evento dentro do stream.
- `UNIQUE(stream_id, stream_version)` garante ordenação e previne duplicação.

**Por que não recebe colunas de dispatch, retry, locking ou DLQ**:
- `event_store_events` é um **Event Log puro** — seu papel é apenas registrar fatos.
- Colunas de dispatch (`locked_by`, `available_at`, etc.) pertencem à `outbox_events`.
- Misturar concerns de log e fila dificulta evolução e torna o Event Store mais complexo.

**Aviso**: esta tabela não deve ser confundida com Event Sourcing completo. O estado do sistema continua sendo reconstruído a partir de Redis, não a partir dos eventos aqui armazenados.

## 6. Tabela `outbox_events`

**Local**: `db/edd/002_create_outbox_events.sql` (T-01)

**Finalidade**: Tabela transacional que materializa a outbox — fila de dispatch com suporte a retry, locking concorrente e auditoria.

### Grupos de colunas

| Grupo | Colunas | Finalidade |
|---|---|---|
| **Identificação** | `outbox_id`, `event_id`, `stream_id`, `stream_version` | Identificação única e proveniência |
| **Payload** | `event_type`, `event_payload`, `aggregate_id` | Conteúdo do evento |
| **Status** | `status` | Estado atual do dispatch (pending/locked/dispatched/dead_letter) |
| **Retry** | `attempts`, `max_attempts`, `available_at`, `last_error`, `last_error_class` | Controle de retentativas e backoff |
| **Locking** | `locked_by`, `locked_until` | Concôrencia com `FOR UPDATE SKIP LOCKED` |
| **Auditoria** | `created_at`, `updated_at`, `dispatched_at`, `dead_lettered_at` | Timestamps de ciclo de vida |
| **Correlação** | `correlation_id`, `causation_id`, `metadata` | Rastreabilidade cross-event |

**UNIQUE(event_id)**: previne que o mesmo evento seja colocado na outbox mais de uma vez.

**Ausência do status `failed`**: a falha retentável é representada por `status='pending'` com `attempts` incrementado, `available_at` no futuro e `last_error` preenchido. O status `failed` não persiste — o dispatcher usa `pending` para reagendar.

**Suporte futuro a `FOR UPDATE SKIP LOCKED`**: o índice `idx_outbox_status_available_at` em `(status, available_at)` foi desenhado para suportar queries como:

```sql
SELECT ... FROM outbox_events
 WHERE status = 'pending' AND available_at <= NOW()
 ORDER BY available_at ASC
 LIMIT N
FOR UPDATE SKIP LOCKED;
```

## 7. Tabela `processed_events`

**Local**: `db/edd/003_create_processed_events.sql` (T-02)

**Finalidade**: Garantir idempotência por consumer no processamento de eventos.

**PK composta `(consumer_name, event_id)`**: cada consumer tem namespace próprio. O mesmo consumer não deve processar o mesmo `event_id` duas vezes com sucesso.

**Múltiplos consumers independentes**: a PK composta isola namespace. Consumer A pode processar evento X 100 vezes sem afetar consumer B.

**Por que exactly-once não deve ser assumido**: o modelo realista é at-least-once com deduplicação. O publisher pode reenviar o mesmo evento (ex: retry de rede), e o consumer pode falhar antes de gravar em `processed_events`. A dedup por `(consumer_name, event_id)` protege contra re-execução.

**Relação com at-least-once + deduplicação**: antes de processar, o consumer consulta `processed_events`. Se já existir `(consumer_name, event_id)`, pula. Se não existir, processa e grava após sucesso (com `ON CONFLICT DO NOTHING` para lidar com concorrência).

## 8. Tabela `outbox_dlq`

**Local**: `db/edd/004_create_outbox_dlq.sql` (T-03)

**Finalidade**: Armazena eventos que esgotaram tentativas de dispatch. Tabela separada da outbox principal.

**UNIQUE(outbox_id)**: 1 evento na outbox = 1 entrada na DLQ. Impossível duplicar.

### Campos principais

| Campo | Finalidade |
|---|---|
| `final_error` | Mensagem de erro que causou o movimento para DLQ |
| `final_error_class` | Tipo da exceção (ex: `ConnectionError`, `TimeoutError`) |
| `attempts` | Número de tentativas realizadas antes de falhar |
| `max_attempts` | Limite configurado |
| `moved_to_dlq_at` | Timestamp do movimento |
| `original_created_at` | Timestamp de criação original na outbox (auditoria) |

**Sem FK física**: a integridade entre `outbox_events` e `outbox_dlq` é tratada pelo dispatcher futuro, não por constraint física. Isso permite que o schema seja validado isoladamente.

**Investigação operacional**: a DLQ pode ser consultada para investigar falhas recorrentes, padrões de erro e eventos problemáticos. Os índices em `event_id`, `stream_id`, `event_type`, `moved_to_dlq_at` e `aggregate_id` suportam queries de investigação.

## 9. Estados da outbox

| Estado | Significado | Transições futuras | Campos relevantes |
|---|---|---|---|
| `pending` | Aguardando dispatcher | → `locked` (dispatcher pega) | `available_at`, `attempts` |
| `locked` | Em processamento por worker | → `dispatched` (sucesso), → `pending` (falha retentável), → `dead_letter` (esgotado) | `locked_by`, `locked_until` |
| `dispatched` | Despachado com sucesso | Terminal (nenhuma) | `dispatched_at` |
| `dead_letter` | Tentativas esgotadas | Terminal (nenhuma) | `dead_lettered_at` |

**`failed` NÃO é estado persistente.** A falha retentável é representada por:
- `status = 'pending'`
- `attempts` incrementado
- `available_at` no futuro (backoff exponencial)
- `last_error` e `last_error_class` preenchidos

Após `attempts >= max_attempts`, o evento é movido para `dead_letter` (INSERT em `outbox_dlq` + UPDATE status).

## 10. Contrato futuro do dispatcher

> Sem implementar. Apenas especificação conceitual.

O dispatcher futuro deve:

1. **Selecionar** eventos com `status = 'pending' AND available_at <= NOW()`.
2. **Usar** `SELECT ... FOR UPDATE SKIP LOCKED` para concorrência segura entre workers.
3. **Respeitar** `available_at` — não processar antes do backoff.
4. **Incrementar** `attempts` a cada tentativa.
5. **Recalcular** `available_at` com backoff exponencial: `NOW() + (base * factor^attempts)`.
6. **Mover para DLQ** quando `attempts >= max_attempts` (INSERT em `outbox_dlq` + UPDATE `status='dead_letter'`).
7. **Evitar processamento duplicado** via lock + idempotência no consumer.
8. **Registrar** `last_error` e `last_error_class` em caso de falha.

**Defaults conceituais** (configuráveis via env vars):
- `EDD_MAX_ATTEMPTS=3`
- `EDD_BACKOFF_BASE_SECONDS=0.5`
- `EDD_BACKOFF_FACTOR=2.0`
- `EDD_LOCK_TTL_SECONDS=30`

## 11. Contrato futuro de idempotência

> Sem implementar. Apenas especificação conceitual.

O consumer futuro deve:

1. **Consultar** `processed_events` com `SELECT 1 FROM processed_events WHERE consumer_name = $1 AND event_id = $2`.
2. **Se retornar linha**: pular (já processado).
3. **Se não retornar**: processar o evento.
4. **Após sucesso**: gravar em `processed_events` com `ON CONFLICT (consumer_name, event_id) DO NOTHING`.

**Riscos de falha antes/depois de gravar**:
- Falha **antes** de processar: `processed_events` não tem a linha → reprocessamento seguro.
- Falha **durante** o trabalho: reprocessamento re-executa o trabalho (at-least-once).
- Falha **após** processar, **antes** de gravar: reprocessamento re-executa (at-least-once).

**Modelo**: at-least-once com deduplicação por consumer. Não assumir exactly-once.

## 12. Observabilidade futura

> Sem implementar. Apenas especificação conceitual.

**Span agregado**: `event_publish_batch` (1 span por chamada do Publisher, englobando N eventos).

**Metadados recomendados**:
- `event_store.backend` — backend ativo (memory, redis_streams, postgres)
- `event_store.batch_size` — quantidade de eventos no batch
- `event_store.success_count` — eventos publicados com sucesso
- `event_store.failure_count` — eventos que falharam
- `event_store.duration_ms` — tempo total do batch
- `event_store.first_error_class` — tipo da primeira exceção
- `event_store.first_error_message` — mensagem truncada

**Logs estruturados**: toda falha deve ser logada com severidade WARNING/ERROR, contendo `event_id`, `event_type`, `stream_id`, `attempts`, `error_class`, `error_message`.

**Falhas não devem ser silenciosas**: `EventPublisherImpl.publish` atual engole exceções. O desenho futuro deve registrar toda falha de publicação.

## 13. Limites explícitos

- **Não** ativa Postgres no `/chat`.
- **Não** cria dispatcher.
- **Não** cria worker.
- **Não** altera `conversation_saga.py`.
- **Não** altera `EventPublisher` ou `EventStore` Protocolos.
- **Não** altera `docker-compose.yaml`.
- **Não** altera `.env`.
- **Não** cria secrets.
- **Não** aplica SQL automaticamente.
- **Não** substitui migrations futuras.
- **Não** transforma o sistema em Event Sourcing completo.

## 14. Validação futura

A validação real em Postgres local/efêmero deve ser feita em ciclo separado, com:

- Aplicação dos SQLs via `scripts/apply_edd_schema.sh --apply`.
- Validação via `scripts/validate_edd_schema.sh --validate`.
- Verificação de tabelas, constraints, índices.
- Verificação de idempotência: rodar scripts 2 vezes sem erro.
- Verificação de que runtime permanece intacto (`/chat` continua com `InMemoryEventStore()`).
- Uso dos scripts manuais apenas quando explicitamente aprovado pelo usuário.

## 15. Riscos conhecidos

| # | Risco | Mitigação |
|---|---|---|
| 1 | Aplicação em banco errado | Scripts exigem DSN explícito; dry-run por padrão |
| 2 | Divergência entre documentação e SQL | Este documento foi escrito após validação das tarefas T-01..T-06 |
| 3 | Crescimento indefinido de outbox/DLQ/processed_events | Política de purge/retention a ser definida em ciclo futuro |
| 4 | Falta de purge/retention | Documentado como limitação conhecida |
| 5 | Permissões dos scripts | Scripts criados sem `chmod +x`; execução requer aprovação explícita |
| 6 | Validação real em Postgres ainda pendente | Requer Postgres efêmero + execução manual dos scripts |
| 7 | Risco de confundir outbox com Event Sourcing | Documentado: outbox é fila de dispatch, não fonte da verdade |
| 8 | CHECK constraint pode ter variações de formatação entre versões do Postgres | Assertions do validate script usam `LIKE` para tolerância |

## 16. Próximas etapas

| Etapa | Status | Descrição |
|---|---|---|
| T-01 a T-06 | **Concluídas** | Schema SQL + scripts + README |
| T-07 | **Este documento** | Documentação técnica consolidada |
| T-08 | **N/A** | `failed` já foi removido na T-01 (CHECK com 4 status) |
| T-09 | **Pendente** | Validação consolidada dos critérios de aceite |
| Runtime EDD | **Futuro** | Conexão do Postgres ao `/chat` em ciclo explicitamente aprovado |
| Dispatcher | **Futuro** | Implementação do dispatcher com `FOR UPDATE SKIP LOCKED` |
| Publisher transacional | **Futuro** | Conexão do `EventPublisher` com a outbox |

O runtime só deve ser planejado em ciclo **posterior** ao schema estar validado em Postgres real.

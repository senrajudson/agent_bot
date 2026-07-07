# Last Answer — Validação do EDD Prompt 18

> Sessão: 2026-07-06
> Solicitação: Validar a implementação do EDD Prompt 18 — failure path, retry, DLQ, idempotência e runbook operacional.

---

## 1. Arquivos alterados

| Operação | Arquivo | Task |
|---|---|---|
| Editado (extensão) | `tests/unit/test_conversation_memory_save_outbox_handler.py` | T1 |
| Criado | `tests/unit/test_logging_consumer_does_not_log_payload.py` | T2 |
| Criado | `tests/integration/edd/test_conversation_memory_save_handler_integration.py` | T3 |
| Criado | `tests/integration/edd/test_conversation_memory_save_handler_dlq_integration.py` | T4 |
| Criado | `db/edd/RUNBOOK.md` | T5 |

**Nenhum arquivo em `app/**`, `scripts/**`, `db/edd/*.sql`, `db/edd/README.md`, `AGENTS.md`, `docker-compose.yaml`, `.env`, `app/.env.example` foi tocado.**

## 2. Diff resumido

```
tests/unit/test_conversation_memory_save_outbox_handler.py  | +28 (extensão)
tests/unit/test_logging_consumer_does_not_log_payload.py    | +60 (novo)
tests/integration/edd/test_conversation_memory_save_handler_integration.py        | +96 (novo)
tests/integration/edd/test_conversation_memory_save_handler_dlq_integration.py    | +88 (novo)
db/edd/RUNBOOK.md                                          | +95 (novo)
```

Housekeeping via `git diff -- <8 paths>`: **0 linhas alteradas**.

## 3. Critérios de aceite — resumo

### T1 — Logs seguros do handler
- Unit, sem externas, sentinelas claras, `RuntimeError` forçado, 4 asserts de ausência em `caplog.text`. ✓

### T2 — LoggingOutboxConsumer sem payload
- Unit, sem externas, 5 asserts de ausência, sanity check `"outbox_event_handled"` presente. ✓

### T3 — Retry com handler real + Postgres
- `@pytest.mark.integration`, `pg_pool` fixture, chain real, sem adapter/Redis/fakeredis/rede. Asserts: `claimed=1, processed=0, retry=1, dlq=0, status=pending, attempts=1, last_error_class=RuntimeError, processed_events=0, outbox_dlq=0`. ✓

### T4 — DLQ com handler real + Postgres
- `attempts=2, max_attempts=3`. Asserts: `dlq=1, status=dead_letter, attempts=3, dead_lettered_at not null, outbox_dlq` snapshot, `processed_events=0`. ✓

### T5 — Runbook
- PT-BR, 14 seções, apenas SELECT, sem comandos destrutivos, marca `outbox_dlq` e `last_error` como sensíveis, retenção pendente. ✓

## 4. Testes executados e resultados

| Suite | Testes | Resultado |
|---|---|---|
| Unit (T1+T2) | 10 | **10/10 passed** (0.05s) |
| Integration (T3+T4) | 2 | **2/2 passed** (7.23s, Postgres real) |
| **Total** | **12** | **12/12 passed** |

## 5. Riscos restantes

| Risco | Severidade | Mitigação |
|---|---|---|
| `last_error` pode conter `user_message` se exceção ecoar | Médio | T1 + runbook alerta + redaction futura |
| `outbox_dlq` persiste payload integral | Médio | Runbook marca sensível + retenção futura |
| Dispatcher não loga falhas estruturadas | Baixo | Runbook orienta SQL |
| Integration depende de Postgres local | Médio | CI deve garantir DSN + schema |

## 6. Regressões potenciais

- **Nenhuma detectada**: suite unit existente (8 testes anteriores) mantém-se passando + 1 novo (9 total).
- Recomendação: re-executar suite integration anterior (`test_outbox_dispatcher_integration.py`, `test_postgres_outbox_store_integration.py`, `test_logging_consumer_integration.py`) para confirmar ausência de regressão colateral.

## 7. Documentação afetada

| Arquivo | Estado |
|---|---|
| `db/edd/RUNBOOK.md` | Criado (novo, 14 seções) |
| `AGENTS.md`, `db/edd/README.md`, `app/.env.example` | Não alterados |

## 8. Pontos de atenção

1. **Sanity check T2 ajustado**: `extra` dict não é renderizado no formato `basicConfig` padrão; sanity check trocado de `event_id` em texto para `"outbox_event_handled"` na string da mensagem. Asserções principais (ausência de vazamento) mantidas.
2. **`insert_outbox_event` exige `event_payload` como `str`**: T3/T4 usam `json.dumps({...})` conforme necessidade do helper.

## 9. Próxima ação recomendada

**Aprovar implementação do EDD Prompt 18.** Sugestão de próximos prompts:
1. Logging estruturado de falhas no `OutboxDispatcher` (observabilidade).
2. Política de retenção/expurgo de `outbox_dlq`.
3. Redaction automática de `last_error`.
4. Mecanismo de injeção de falha no CLI para validação live.

---

**Resumo da validação**: 5 arquivos, 12 testes novos (10 unit + 2 integration), todos passando. 0 arquivos housekeeping alterados. 0 regressões detectadas.

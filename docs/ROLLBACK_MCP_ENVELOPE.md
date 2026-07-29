# Rollback — Eliminação de retorno volumoso no envelope MCP

## Procedimento de rollback

### Commit 1 — Configuração segura e tool exposure

**Revert**: `git revert <hash_do_commit_1>`

**Mudanças revertidas**:
- `mcp_server/.env`: `ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY` volta para `false` ou ausente
- `mcp_server/.env.production`: idem
- `mcp_server/.env.example`: flags removidas
- `docker-compose.yaml`: overrides explícitos removidos
- `mcp_server/core/config.py`: `log_effective_config()` removido; `logger` import removido
- `mcp_server/server.py`: log de boot da flag removido; registro de `export_csv_to_drive_tool` restaurado (condicional)

**Verificação pós-revert**:
```bash
docker exec mcp_server python -c "from mcp_server.core.config import settings; print(settings.ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY, settings.ENABLE_DRIVE_CSV_EXPORT_TOOL)"
```
Esperado: `False True`

---

### Commit 2 — Barreira universal MCP

**Revert**: `git revert <hash_do_commit_2>`

**Mudanças revertidas**:
- `mcp_server/services/delivery/contracts.py`: `DeliveryMode.REJECT`, `reason_code` removidos
- `mcp_server/services/delivery/exceptions.py`: `InlinePayloadTooLargeError`, `ArtifactDeliveryDisabledError`, `DeliveryRejectedError` removidos
- `mcp_server/services/delivery/output_delivery_policy.py`: volta à versão anterior (consultar_tag > 20 → INLINE, sem reason_code)
- `mcp_server/server.py`: `_mcp_safe_tool` removido; ferramentas voltam a ser funções diretas sem wrapper

**Verificação pós-revert**:
```bash
poetry run pytest tests/mcp_server/test_delivery_policy.py -v | grep "passed\|failed"
```
Esperado: testes de policy existentes passam

---

### Commit 3 — tag_statistics fail-closed + CSV + manifesto

**Revert**: `git revert <hash_do_commit_3>`

**Mudanças revertidas**:
- `mcp_server/server.py`: `tag_statistics` volta a retornar série inline com flag false; `_artifact_publisher` removido; retorno volta a usar `json.dumps()` em vez de dict
- `domain/analytics/services/math_tool_service.py`: `drive_artifact_delivery` removido; série sempre inline

**Verificação pós-revert**:
```bash
poetry run pytest tests/mcp_server/test_tag_statistics_artifact.py -v | grep "passed\|failed"
```

---

### Commit 4 — Hardening consultar_tag

**Revert**: `git revert <hash_do_commit_4>`

**Mudanças revertidas**:
- `mcp_server/server.py`: `consultar_tag` volta a não ter cap de 50 tags; não gera artefato para 21-50 tags
- `domain/pims/services/consultar_tag_service.py`: `include_raw_response` restaurado

**Verificação pós-revert**:
```bash
poetry run pytest tests/mcp_server/test_consultar_tag_policy.py -v | grep "passed\|failed"
```

---

### Commit 5 — Proteção demais tools + observabilidade

**Revert**: `git revert <hash_do_commit_5>`

**Mudanças revertidas**:
- `mcp_server/server.py`: `search_pi_points` volta para `max_count: int = 20`; demais tools voltam a não ter wrapper
- `app/observability/phoenix.py`: span attributes `delivery_mode`, `row_count` removidos

**Verificação pós-revert**:
```bash
poetry run pytest tests/mcp_server/ -v | grep "passed\|failed"
```

---

### Commit 6 — Prompt + RAG

**Revert**: `git revert <hash_do_commit_6>`

**Mudanças revertidas**:
- `app/prompts/agent_prompt.py`: `drive_csv_*` blocos restaurados (com `ENABLE_DRIVE_CSV_EXPORT_TOOL` conditional)
- `app/agent/agent.py`: parâmetro `enable_drive_csv_export_tool` restaurado na chamada

**Verificação pós-revert**:
```bash
poetry run pytest tests/unit/test_agent_prompt_delega_mcp.py -v | grep "passed\|failed"
```

---

### Commit 7 — Testes de integração

**Revert**: `git revert <hash_do_commit_7>`

**Mudanças revertidas**:
- Arquivos de teste novos removidos (test_mcp_safe_tool_decorator.py, test_server_tool_registration.py, test_consultar_tag_policy.py, etc.)
- Ajustes em testes existentes revertidos

**Verificação pós-revert**:
```bash
poetry run pytest tests/mcp_server/ -v | grep "passed\|failed"
```

---

## Rollback de configuração (Docker)

```bash
# Reverter imagem para versão anterior
docker compose down mcp_server
docker tag pi_mcp_server:0.1.1 pi_mcp_server:0.1.1-after-fix
docker pull pi_mcp_server:0.1.1  # ou usar imagem anterior disponível no registry
docker compose up -d mcp_server

# Alternativa: rebuild sem as alterações
git revert HEAD~7..HEAD  # reverter todos os 7 commits
docker compose build mcp_server
docker compose up -d --force-recreate mcp_server

# Verificar flags
docker exec mcp_server python -c "from mcp_server.core.config import settings; print(settings.ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY, settings.ENABLE_DRIVE_CSV_EXPORT_TOOL)"
```

## Rollback de RAG

```bash
# Reingerir versão anterior do markdown
git checkout HEAD~1 PI_WEB_API_AGENT_GUIDE.md  # ou restaurar versão anterior
poetry run python scripts/ingest_pi_guide.py --confirm

# Verificar
poetry run python scripts/validate_rag_recall.py
```

## Rollback de configuração manual (.env)

```bash
# Restaurar .env de backup
cp mcp_server/.env.bak mcp_server/.env
# ou via git
git checkout HEAD~1 mcp_server/.env mcp_server/.env.production docker-compose.yaml
docker compose up -d --force-recreate mcp_server
```

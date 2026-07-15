# Experimento A/B — Reversão de Docstrings MCP Enriquecidas

> **Data**: 2026-07-13
> **Estado**: experimental — revertido apenas para teste controlado.

---

## Objetivo

Testar se o agente PI continua roteando corretamente com docstrings MCP
simplificadas, desde que as demais camadas (nomes, schemas, FastMCP.instructions,
prompt enxuto, CHUNK 01, outputs interpretáveis) permaneçam ativas.

## Hipótese

A seleção de tools pelo agente pode funcionar adequadamente com base apenas em:

1. Nomes claros das tools
2. Schemas/parâmetros descritivos
3. `FastMCP.instructions` com tabela de roteamento + desambiguação
4. `AGENT_SYSTEM_PROMPT` delegando seleção primária para MCP/schema
5. CHUNK 01 como mapa de roteamento sempre injetado
6. Services com outputs interpretáveis

Mesmo sem docstrings individuais ricas (6 seções obrigatórias como Propósito,
Quando usar, Quando NÃO usar, Anti-padrões, Parâmetros, Saída).

## O que foi revertido

- Docstrings das 6 tools MCP em `mcp_server/server.py`:
  - `consultar_tag`
  - `search_pi_points`
  - `tag_attributes_tool`
  - `tag_statistics`
  - `tag_calculus`
  - `status_pims_tool`
- Teste `test_mcp_docstrings.py` ajustado: removidas asserções que exigiam
  as 6 seções obrigatórias; mantidas asserções de registro, docstring não vazia,
  assinaturas e ausência de formato rico.

## O que foi preservado (intacto)

| Camada | Arquivo |
|---|---|
| `FastMCP.instructions` | `mcp_server/server.py` (linhas 30-42) |
| `AGENT_SYSTEM_PROMPT` | `app/prompts/agent_prompt.py` |
| Services interpretáveis | `domain/pims/services/*`, `domain/analytics/services/*`, `domain/pims_ops/services/*` |
| Espelhamento MCP server | `mcp_server/services/*`, `mcp_server/utils/*` |
| CHUNK 01 (mapa de roteamento) | `PI_WEB_API_AGENT_GUIDE.md` |
| RAG conceitual (CHUNKs 02-24) | `PI_WEB_API_AGENT_GUIDE.md` |
| Testes de outputs interpretáveis | `tests/unit/test_outputs_interpretaveis.py` |
| Teste de RAG vazio | `tests/integration/test_routing_with_empty_rag.py` |
| Teste de CHUNK 01 | `tests/unit/test_chunk_01_cobre_6_tools.py` |
| Teste de prompt | `tests/unit/test_agent_prompt_delega_mcp.py` |
| Matriz QA | `tests/qa_routing_matrix.md` |
| Script de QA | `scripts/qa_routing_matrix.py` |
| Documentação Etapa 9 | `AGENTS.md` (seção 24) |

## Como validar

```bash
# Testes focados
pytest tests/mcp_server/test_mcp_docstrings.py -v
pytest tests/mcp_server/test_mcp_instructions.py -v
pytest tests/unit/test_agent_prompt_delega_mcp.py -v
pytest tests/unit/test_chunk_01_cobre_6_tools.py -v
pytest tests/unit/test_outputs_interpretaveis.py -v
pytest tests/integration/test_routing_with_empty_rag.py -v

# Suite completa
pytest tests/ -v

# Validar diff
git diff --name-only
git diff --stat
```

## Critérios de sucesso

- [ ] `test_mcp_docstrings.py` passa (4+ testes)
- [ ] `test_mcp_instructions.py` passa (instructions intactas)
- [ ] `test_agent_prompt_delega_mcp.py` passa (prompt intacto)
- [ ] `test_chunk_01_cobre_6_tools.py` passa (CHUNK 01 intacto)
- [ ] `test_outputs_interpretaveis.py` passa (services intactos)
- [ ] `test_routing_with_empty_rag.py` passa (RAG vazio ainda funcional)
- [ ] Suite completa: ~1253 passed, 0 regressão nova
- [ ] `git diff --name-only` lista apenas `mcp_server/server.py`,
      `tests/mcp_server/test_mcp_docstrings.py`,
      `docs/EXPERIMENT_MCP_DOCSTRINGS_REVERT.md`

## Critérios de falha

- Qualquer regressão nova na suite (além das 15 pré-existentes)
- Qualquer teste de output interpretável quebrando
- Teste de RAG vazio quebrando (evidência de que docstrings ricas eram necessárias)

## Como restaurar

```bash
# Opção 1: reverter o commit experimental inteiro
git revert HEAD

# Opção 2: restaurar apenas os arquivos tocados
git checkout HEAD~1 -- mcp_server/server.py tests/mcp_server/test_mcp_docstrings.py
rm docs/EXPERIMENT_MCP_DOCSTRINGS_REVERT.md
```

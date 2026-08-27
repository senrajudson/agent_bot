# Ambiente QA Local — `agent_bot`

Este diretório contém a infraestrutura, scripts de preflight e documentação necessária para executar o ambiente de **QA Local** do `agent_bot` de forma 100% isolada do ambiente de Produção e de infraestruturas compartilhadas.

---

## 1. Arquitetura do QA Local

```text
Consumidor HTTP Externo (ex: n8n local, scripts)
              |
              v
     API agent_bot (Host local, porta 8002)
       - APP_ENV=qa
       - REDIS_URL=redis://127.0.0.1:6380/0
       - REDIS_KEY_PREFIX=pi_chat:qa:memory
              |
              v
     Container Docker Redis QA (127.0.0.1:6380)
       - Volume: agent_bot_redis_qa_data
```

- **API `agent_bot`**: Executada diretamente no Host pelo desenvolvedor.
- **Redis QA**: Container Docker exclusivo rodando em `127.0.0.1:6380` (Database `0`).
- **Validador Preflight (`qa/validate_environment.py`)**: Script autônomo fail-closed que verifica todas as configurações e serviços de QA antes dos testes.
- **Desacoplamento do n8n**: O n8n é considerado exclusivamente um consumidor HTTP externo da API. A aplicação não possui acoplamento de código ou dependência de infraestrutura com o n8n.

---

## 2. Pré-requisitos

- Docker e Docker Compose V2 instalados no Host.
- Python 3.12+ e Poetry instalados.

---

## 3. Passo a Passo de Operação

### Passo 1 — Criar Arquivo de Configuração Local

Copie o modelo de exemplo para criar o arquivo de ambiente local de QA:

```bash
cp qa/.env.qa.example qa/.env.qa
```

> **Nota:** O arquivo `qa/.env.qa` é ignorado pelo Git para evitar vazamento de credenciais locais.

### Passo 2 — Iniciar o Redis QA

Suba o container Redis dedicado ao ambiente QA:

```bash
docker compose -p agent_bot_qa -f qa/docker-compose.qa.yaml up -d
```

### Passo 3 — Iniciar a API `agent_bot` em Modo QA

Execute a API no host carregando o arquivo de ambiente de QA:

```bash
poetry run uvicorn app.main:app --host 127.0.0.1 --port 8002 --env-file qa/.env.qa
```

### Passo 4 — Executar o Validador Preflight Operacional (QA-04)

Com o Redis QA e a API em execução, execute o validador preflight por comando único:

```bash
poetry run python qa/validate_environment.py
```

Ou especificando explicitamente o arquivo de ambiente e URL da API:

```bash
poetry run python qa/validate_environment.py --env-file qa/.env.qa --api-base-url http://127.0.0.1:8002
```

---

## 4. Validador Preflight Operacional (`qa/validate_environment.py`)

O validador `qa/validate_environment.py` é uma ferramenta autônoma fail-closed que executa verificações estáticas e de I/O controladas sem produzir efeitos colaterais (zero gravações no Redis e zero criações/exclusões de arquivos).

### Tabela de Exit Codes

| Exit Code | Significado | Descrição |
| --------: | :---------- | :-------- |
| `0` | **PASS** | Todos os checks obrigatórios passaram com sucesso. |
| `1` | **FAIL** | Um ou mais checks operacionais de I/O falharam (ex: Redis offline ou API inativa). |
| `2` | **BLOCKED** | Configuração insegura ou não-QA bloqueada estaticamente antes de abrir conexões de rede (Fail-Closed). |
| `3` | **INTERNAL_ERROR** | Erro interno ou exceção inesperada no validador. |

### Interpretação dos Status dos Checks

- **`PASS`**: A verificação foi concluída com sucesso.
- **`FAIL`**: A verificação estática ou de I/O falhou (ex: porta incorreta, conexão recusada).
- **`BLOCKED`**: O preflight identificou um valor inseguro (ex: `APP_ENV=prd` ou host não-loopback) e interrompeu a execução sem abrir rede.
- **`NOT_EXECUTED`**: O check não foi executado (ex: por conta de bloqueio prévio ou por ser verificação opcional standing como o MCP).

### Saída Esperada (Exemplo de Sucesso)

```json
{
  "status": "PASS",
  "environment": "qa",
  "checks": [
    {
      "name": "environment",
      "status": "PASS",
      "detail": "Identidade do ambiente confirmada como 'qa'"
    },
    {
      "name": "redis_configuration",
      "status": "PASS",
      "detail": "Redis QA local configurado (127.0.0.1:6380/0)"
    },
    {
      "name": "memory_namespace",
      "status": "PASS",
      "detail": "Namespace de memoria QA configurado ('pi_chat:qa:memory')"
    },
    {
      "name": "artifact_api_path",
      "status": "PASS",
      "detail": "Diretorio de artefatos API valido: /tmp/agent_bot_qa/api_artifacts"
    },
    {
      "name": "artifact_mcp_path",
      "status": "PASS",
      "detail": "Diretorio de artefatos MCP valido: /tmp/agent_bot_qa/mcp_artifacts"
    },
    {
      "name": "artifact_csv_path",
      "status": "PASS",
      "detail": "Diretorio de series CSV valido: /tmp/agent_bot_qa/mcp_series_csv"
    },
    {
      "name": "phoenix_project",
      "status": "PASS",
      "detail": "Projeto Phoenix QA configurado ('pi-chat-api-qa')"
    },
    {
      "name": "otel_environment",
      "status": "PASS",
      "detail": "Atributo OTel deployment.environment=qa presente"
    },
    {
      "name": "otel_channel",
      "status": "PASS",
      "detail": "Atributo OTel app.channel=n8n presente"
    },
    {
      "name": "api_url_security",
      "status": "PASS",
      "detail": "URL da API local validada: http://127.0.0.1:8002"
    },
    {
      "name": "redis_ping",
      "status": "PASS",
      "detail": "PING no Redis QA respondeu PONG com sucesso"
    },
    {
      "name": "api_health",
      "status": "PASS",
      "detail": "GET /health respondeu 200 OK (service: Bot Chat API QA)"
    },
    {
      "name": "mcp_health",
      "status": "NOT_EXECUTED",
      "detail": "MCP health: NOT_EXECUTED — fora do preflight obrigatorio do QA-04"
    }
  ]
}
```

---

## 5. Smoke Tests Manuais Posteriores

Após a aprovação do preflight pelo validador (`exit_code = 0`), smoke tests manuais podem ser executados:

### Smoke Test 1 — Memória QA (Redis)

Para verificar as chaves salvas exclusivamente pelo ambiente QA no Redis:

```bash
docker compose -p agent_bot_qa -f qa/docker-compose.qa.yaml exec -T redis_qa redis-cli keys "pi_chat:qa:memory:*"
```

As chaves do histórico de conversa seguirão a estrutura:
- **Turnos:** `pi_chat:qa:memory:{conversation_id}:turns`
- **Deduplicação:** `pi_chat:qa:memory:{conversation_id}:dedupe:{event_id}`

### Smoke Test 2 — Artefatos Locais (`/tmp/agent_bot_qa/`)

Durante a execução em QA, os artefatos gerados são gravados sob a raiz isolada `/tmp/agent_bot_qa/`:

```text
/tmp/agent_bot_qa/
├── api_artifacts/     # Artefatos servidos pela API
├── mcp_artifacts/     # Relatórios temporários do MCP Server
└── mcp_series_csv/    # Séries temporais em CSV do MCP Server
```

Para listar os arquivos gerados em cada diretório de QA:

```bash
ls -la /tmp/agent_bot_qa/api_artifacts
ls -la /tmp/agent_bot_qa/mcp_artifacts
ls -la /tmp/agent_bot_qa/mcp_series_csv
```

### Smoke Test 3 — Tracing no Arize Phoenix

Os traces da API local de QA podem ser localizados e filtrados na UI do Arize Phoenix utilizando:
- **Projeto Phoenix:** `pi-chat-api-qa`
- **Ambiente de Instância:** `deployment.environment = qa`
- **Canal Consumidor QA:** `app.channel = n8n`

---

## 6. Diagnóstico e Troubleshooting

| Problema | Causa Provável | Solução Recomendada |
| :------- | :------------- | :------------------ |
| `status = BLOCKED`, exit `2` | `APP_ENV` != `qa`, IP/URL remota ou paths fora de `/tmp/agent_bot_qa` | Verifique se `qa/.env.qa` contém `APP_ENV=qa`, `REDIS_URL=redis://127.0.0.1:6380/0` e caminhos sob `/tmp/agent_bot_qa/`. |
| `redis_ping = FAIL (connection_refused)` | Container Redis QA não está rodando na porta 6380 | Execute `docker compose -p agent_bot_qa -f qa/docker-compose.qa.yaml up -d`. |
| `api_health = FAIL (connection_refused)` | API local não foi iniciada na porta 8002 | Suba a API com `poetry run uvicorn app.main:app --host 127.0.0.1 --port 8002 --env-file qa/.env.qa`. |
| `phoenix_project = BLOCKED` | `PHOENIX_PROJECT_NAME` configurado para projeto de Produção | Garanta que `PHOENIX_PROJECT_NAME=pi-chat-api-qa` no `qa/.env.qa`. |

---

## 7. Encerramento e Limpeza Segura

### Parar o Ambiente QA (Preservando Dados)

Para encerrar o container do Redis QA mantendo o volume de memória de testes:

```bash
docker compose -p agent_bot_qa -f qa/docker-compose.qa.yaml down
```

### Limpeza Completa (Removendo Volume do Redis QA)

Para apagar o container e resetar a memória do Redis QA:

```bash
docker compose -p agent_bot_qa -f qa/docker-compose.qa.yaml down -v
```

### Limpeza Segura dos Artefatos de QA

> [!WARNING]
> A remoção de artefatos deve ser feita exclusivamente na raiz `/tmp/agent_bot_qa/`. Nunca execute comandos de remoção genéricos em `/tmp` ou no diretório de Produção.

Para limpar apenas os artefatos locais gerados pelo ambiente de QA:

```bash
rm -rf /tmp/agent_bot_qa/api_artifacts/*
rm -rf /tmp/agent_bot_qa/mcp_artifacts/*
rm -rf /tmp/agent_bot_qa/mcp_series_csv/*
```

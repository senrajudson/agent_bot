# Drive CSV Export — `export_csv_to_drive_tool`

## Arquitetura

A tool `export_csv_to_drive_tool` recebe dados tabulares inline (filename,
columns, rows), serializa como CSV, faz upload para uma pasta configurada em
Google Shared Drive, e retorna links canônicos (view_url, download_url).

```
LLM → Agent → MCP → export_csv_to_drive_tool → CSV serializer → Drive API → links
```

## Pré-requisitos (checklist administrativo)

1. [ ] Criar service account dedicada (`pi-chat-drive-exporter@...`)
2. [ ] Habilitar Drive API no projeto GCP
3. [ ] Gerar chave JSON e armazenar como secret
4. [ ] Selecionar Shared Drive corporativo
5. [ ] Criar pasta de exportações do PI Chat
6. [ ] Adicionar grupo corporativo autorizado
7. [ ] Adicionar service account à pasta com papel **Writer**
8. [ ] Obter folder ID
9. [ ] Montar secret no `mcp_server` (ver `docker-compose.yaml`)
10. [ ] Configurar `GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE` e `GOOGLE_DRIVE_EXPORT_FOLDER_ID`
11. [ ] Testar acesso em non-prod
12. [ ] Manter flag `false` em produção até aprovação

## Ambiente: Host vs Docker

Algumas variáveis divergem entre execução local (host) e Docker (produção).
A tabela abaixo documenta a separação:

| Variável | Host | Docker |
|---|---|---|
| `MCP_PORT` | `8015` | `8005` |
| `AGENT_API_BASE_URL` | `http://localhost:8002` | `http://agent_bot:8002` |
| `GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE` | path absoluto do host | `/run/secrets/pi_chat_drive_exporter/service-account.json` |
| Fonte do template | `mcp_server/.env.example` | `docker-compose.yaml` (environment section) |

- Em **host**: `mcp_server/.env` local define `MCP_PORT=8015` e `AGENT_API_BASE_URL=http://localhost:8002`.
- Em **Docker**: `docker-compose.yaml` sobrescreve via `environment` com `MCP_PORT=8005` e `AGENT_API_BASE_URL=http://agent_bot:8002`.
- A credencial Drive nunca é versionada; em host aponta para caminho absoluto local, em Docker via bind mount `read-only`.

## Configuração

### `mcp_server/.env`

```bash
ENABLE_DRIVE_CSV_EXPORT_TOOL=false
GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=/run/secrets/pi_chat_drive_exporter/service-account.json
GOOGLE_DRIVE_EXPORT_FOLDER_ID=<folder_id>

DRIVE_CSV_MAX_ROWS=500
DRIVE_CSV_MAX_COLUMNS=50
DRIVE_CSV_MAX_CELL_BYTES=32768
DRIVE_CSV_MAX_INPUT_BYTES=5242880
DRIVE_CSV_MAX_FILE_BYTES=10485760
DRIVE_CSV_UPLOAD_TIMEOUT_SECONDS=60
DRIVE_CSV_MAX_FILENAME_LENGTH=180
DRIVE_CSV_FORMULA_PROTECTION=true
```

### `app/.env`

```bash
ENABLE_DRIVE_CSV_EXPORT_TOOL=false
```

### Flag false

- mcp_server inicia sem secret
- tool não registrada em tools/list
- prompt informa indisponibilidade

### Flag true

- Configuração validada no startup
- tool registrada
- prompt anuncia a tool

## Secret

O JSON da service account deve ser montado apenas no container
`mcp_server`, via bind mount read-only:

```yaml
volumes:
  - ./secrets/pi_chat_drive_exporter:/run/secrets/pi_chat_drive_exporter:ro
```

Não montar no agent_bot ou na bridge.

## Formato CSV

| Propriedade | Valor |
|-------------|-------|
| MIME | `text/csv` |
| Encoding | `utf-8-sig` (UTF-8 com BOM) |
| Delimiter | `;` |
| Line terminator | `\r\n` (CRLF) |
| Biblioteca | `csv.writer` (stdlib) |
| Upload | Memória (`BytesIO`) |

## Formula Protection

Células do tipo `str` cujo primeiro caractere seja `=`, `+`, `-`, `@`, `\t` ou `\r`
recebem prefixo `'` para evitar interpretação como fórmula no Excel/Sheets.

Números negativos (`int`, `float`, `Decimal`) não são alterados.

Configurável via `DRIVE_CSV_FORMULA_PROTECTION=true|false`.

## Links

- `view_url`: webViewLink (obrigatório, abre no navegador/Sheets)
- `download_url`: webContentLink (opcional, download direto)

Links não são públicos; sujeitos às permissões do Shared Drive.

## Limites

| Limite | Valor | Descrição |
|--------|-------|-----------|
| LINHAS | 500 | Máximo de linhas no CSV |
| COLUNAS | 50 | Máximo de colunas |
| CELL_BYTES | 32768 | Máximo UTF-8 por célula |
| INPUT_BYTES | 5 MB | Máximo da projeção JSON de entrada |
| FILE_BYTES | 10 MB | Máximo do arquivo CSV final |
| TIMEOUT | 60 s | Timeout do upload |
| FILENAME | 180 chars | Máximo do filename sanitizado |

## Rollback

1. Desabilitar ambas as flags
2. `docker compose build mcp_server agent_bot`
3. `docker compose up -d --force-recreate --no-deps mcp_server`
4. `docker compose restart agent_bot`
5. Confirmar tool ausente e prompt negativo

Arquivos já exportados não são apagados.

## Troubleshooting

| Erro | Causa provável |
|------|----------------|
| `config_missing` | Flag true sem credencial ou folder |
| `credential_invalid` | Arquivo de credencial ilegível ou ausente |
| `drive_auth_error` | SA sem acesso ao Shared Drive |
| `drive_not_found` | Folder ID incorreto |
| `drive_quota_error` | Quota excedida |
| `validation_error` | Dados excedem limites |
| `drive_upload_error` | Erro de rede ou 5xx do Drive |

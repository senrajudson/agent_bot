#!/usr/bin/env python3
"""
qa/validate_environment.py

Validador operacional de preflight para o ambiente QA local (Incremento QA-04).
Verifica a integridade da configuração, isolamento do Redis, memória, artefatos,
tracing e disponibilidade da API local sob politica estrita de fail-closed.

Sem efeitos colaterais: não grava no Redis, não cria/deleta arquivos e não chama serviços de produção.
"""

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

# Tentar importar python-dotenv se disponível
try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

# Dependências já instaladas no projeto
import httpx
import redis


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NOT_EXECUTED = "NOT_EXECUTED"


class AggregatedStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    detail: str


@dataclass
class ValidationReport:
    status: AggregatedStatus
    environment: str
    checks: list[CheckResult]


ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
ALLOWED_REDIS_PORT = 6380
ALLOWED_REDIS_DB = 0
ALLOWED_REDIS_PREFIX = "pi_chat:qa:memory"
ALLOWED_ARTIFACT_ROOT = "/tmp/agent_bot_qa"
EXPECTED_API_ARTIFACTS_DIR = "/tmp/agent_bot_qa/api_artifacts"
EXPECTED_MCP_ARTIFACTS_DIR = "/tmp/agent_bot_qa/mcp_artifacts"
EXPECTED_MCP_SERIES_CSV_DIR = "/tmp/agent_bot_qa/mcp_series_csv"
EXPECTED_PHOENIX_PROJECT = "pi-chat-api-qa"
EXPECTED_OTEL_ENV = "deployment.environment=qa"
EXPECTED_OTEL_CHANNEL = "app.channel=n8n"
ALLOWED_API_PORT = 8002


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validador preflight operacional do ambiente QA local (QA-04)"
    )
    parser.add_argument(
        "--env-file",
        default="qa/.env.qa",
        help="Caminho para o arquivo de configuração de QA (default: qa/.env.qa)",
    )
    parser.add_argument(
        "--api-base-url",
        default="http://127.0.0.1:8002",
        help="URL base da API local (default: http://127.0.0.1:8002)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Timeout maximo em segundos para chamadas de rede (default: 2.0)",
    )
    return parser.parse_args(args)


def load_env_file_manual(env_path: str) -> dict[str, str]:
    """Fallback simples para ler chave=valor se python-dotenv não estiver disponível."""
    env_dict = {}
    path = Path(env_path)
    if not path.is_file():
        return env_dict

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            env_dict[key] = val
    return env_dict


def load_effective_config(env_file_path: str) -> dict[str, str]:
    """
    Carrega a configuração aplicando a precedência:
    variáveis do processo (os.environ) > arquivo .env.qa
    """
    file_vars = {}
    if Path(env_file_path).is_file():
        if dotenv_values is not None:
            raw = dotenv_values(env_file_path)
            file_vars = {k: v for k, v in raw.items() if v is not None}
        else:
            file_vars = load_env_file_manual(env_file_path)

    effective = dict(file_vars)
    for k, v in os.environ.items():
        effective[k] = v
    return effective


def sanitize_text(text: str) -> str:
    """Remove credenciais, senhas e tokens de mensagens e relatórios."""
    if not text:
        return ""
    # Se houver senha em URL no formato redis://:pass@host ou user:pass@host
    if "://" in text and "@" in text:
        try:
            parsed = urlparse(text)
            if parsed.password:
                netloc = parsed.netloc.replace(f":{parsed.password}", ":***")
                if parsed.username:
                    netloc = netloc.replace(f"{parsed.username}:", "***:")
                text = text.replace(parsed.netloc, netloc)
        except Exception:
            pass
    return text


def parse_otel_attributes(attr_str: str) -> dict[str, str]:
    """Parse de atributos OTel no formato chave=valor,chave=valor."""
    result = {}
    if not attr_str:
        return result
    items = attr_str.split(",")
    for item in items:
        item = item.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k:
            result[k] = v
    return result


def is_path_safe_under_root(path_str: str, root_str: str) -> bool:
    """Verifica se path_str é um caminho absoluto e está estritamente sob root_str."""
    if not path_str or not os.path.isabs(path_str):
        return False

    norm_path = os.path.normpath(path_str)
    norm_root = os.path.normpath(root_str)

    if norm_path == norm_root:
        return False  # Não pode ser igual à própria raiz

    try:
        common = os.path.commonpath([norm_path, norm_root])
        if common != norm_root:
            return False
    except ValueError:
        return False

    # Verificar symlink apontando para fora da raiz se o caminho existir
    p = Path(norm_path)
    if p.exists() or p.is_symlink():
        real_p = os.path.realpath(norm_path)
        real_root = os.path.realpath(norm_root)
        try:
            if os.path.commonpath([real_p, real_root]) != real_root:
                return False
        except ValueError:
            return False

    return True


def run_static_preflight(config: dict[str, str], api_base_url: str) -> list[CheckResult]:
    """
    Validações estáticas fail-closed sem conexões de rede.
    Retorna a lista de resultados dos checks.
    """
    checks: list[CheckResult] = []

    # 1. APP_ENV
    app_env = config.get("APP_ENV", "").strip()
    if app_env == "qa":
        checks.append(CheckResult("environment", CheckStatus.PASS, "Identidade do ambiente confirmada como 'qa'"))
    else:
        checks.append(CheckResult(
            "environment",
            CheckStatus.BLOCKED,
            f"APP_ENV invalido ou inseguro: '{sanitize_text(app_env)}' (esperado: 'qa')"
        ))

    # 2. Configuração do Redis (REDIS_URL)
    redis_url = config.get("REDIS_URL", "").strip()
    if not redis_url:
        checks.append(CheckResult("redis_configuration", CheckStatus.BLOCKED, "REDIS_URL nao configurada"))
    else:
        try:
            parsed_redis = urlparse(redis_url)
            host = parsed_redis.hostname or ""
            port = parsed_redis.port
            # Path do redis costuma ser /0
            db_str = parsed_redis.path.lstrip("/") if parsed_redis.path else "0"
            db = int(db_str) if db_str.isdigit() else -1

            if parsed_redis.scheme != "redis":
                checks.append(CheckResult("redis_configuration", CheckStatus.BLOCKED, f"Scheme Redis invalido: '{parsed_redis.scheme}'"))
            elif host not in ALLOWED_HOSTS:
                checks.append(CheckResult("redis_configuration", CheckStatus.BLOCKED, f"Host Redis nao e local/loopback: '{host}'"))
            elif port != ALLOWED_REDIS_PORT:
                checks.append(CheckResult("redis_configuration", CheckStatus.BLOCKED, f"Porta Redis invalida para QA: {port} (esperado: {ALLOWED_REDIS_PORT})"))
            elif db != ALLOWED_REDIS_DB:
                checks.append(CheckResult("redis_configuration", CheckStatus.BLOCKED, f"Database Redis invalido: {db} (esperado: {ALLOWED_REDIS_DB})"))
            else:
                checks.append(CheckResult("redis_configuration", CheckStatus.PASS, "Redis QA local configurado (127.0.0.1:6380/0)"))
        except Exception as e:
            checks.append(CheckResult("redis_configuration", CheckStatus.BLOCKED, f"Erro no parsing de REDIS_URL: {sanitize_text(str(e))}"))

    # 3. Prefixo da Memória
    prefix = config.get("REDIS_KEY_PREFIX", "").strip()
    if prefix == ALLOWED_REDIS_PREFIX:
        checks.append(CheckResult("memory_namespace", CheckStatus.PASS, f"Namespace de memoria QA configurado ('{ALLOWED_REDIS_PREFIX}')"))
    else:
        checks.append(CheckResult("memory_namespace", CheckStatus.BLOCKED, f"Prefixo de memoria invalido ou legado: '{prefix}' (esperado: '{ALLOWED_REDIS_PREFIX}')"))

    # 4. Path da API Artifacts
    api_art = config.get("AGENT_ARTIFACTS_BASE_DIR", "").strip()
    if api_art == EXPECTED_API_ARTIFACTS_DIR and is_path_safe_under_root(api_art, ALLOWED_ARTIFACT_ROOT):
        checks.append(CheckResult("artifact_api_path", CheckStatus.PASS, f"Diretorio de artefatos API valido: {api_art}"))
    else:
        checks.append(CheckResult("artifact_api_path", CheckStatus.BLOCKED, f"Caminho de artefatos API invalido ou fora da raiz QA: '{api_art}'"))

    # 5. Path do MCP Artifacts
    mcp_art = config.get("MCP_ARTIFACT_TEMP_DIR", "").strip()
    if mcp_art == EXPECTED_MCP_ARTIFACTS_DIR and is_path_safe_under_root(mcp_art, ALLOWED_ARTIFACT_ROOT):
        checks.append(CheckResult("artifact_mcp_path", CheckStatus.PASS, f"Diretorio de artefatos MCP valido: {mcp_art}"))
    else:
        checks.append(CheckResult("artifact_mcp_path", CheckStatus.BLOCKED, f"Caminho de artefatos MCP invalido ou fora da raiz QA: '{mcp_art}'"))

    # 6. Path do MCP Series CSV
    csv_art = config.get("MCP_SERIES_CSV_PUBLISH_TEMP_DIR", "").strip()
    if csv_art == EXPECTED_MCP_SERIES_CSV_DIR and is_path_safe_under_root(csv_art, ALLOWED_ARTIFACT_ROOT):
        checks.append(CheckResult("artifact_csv_path", CheckStatus.PASS, f"Diretorio de series CSV valido: {csv_art}"))
    else:
        checks.append(CheckResult("artifact_csv_path", CheckStatus.BLOCKED, f"Caminho de series CSV invalido ou fora da raiz QA: '{csv_art}'"))

    # 7. Projeto Phoenix
    phx_proj = config.get("PHOENIX_PROJECT_NAME", "").strip()
    if phx_proj == EXPECTED_PHOENIX_PROJECT:
        checks.append(CheckResult("phoenix_project", CheckStatus.PASS, f"Projeto Phoenix QA configurado ('{EXPECTED_PHOENIX_PROJECT}')"))
    else:
        checks.append(CheckResult("phoenix_project", CheckStatus.BLOCKED, f"Projeto Phoenix invalido: '{phx_proj}' (esperado: '{EXPECTED_PHOENIX_PROJECT}')"))

    # 8 e 9. Atributos OTel
    otel_attrs_raw = config.get("OTEL_RESOURCE_ATTRIBUTES", "").strip()
    otel_map = parse_otel_attributes(otel_attrs_raw)

    if otel_map.get("deployment.environment") == "qa":
        checks.append(CheckResult("otel_environment", CheckStatus.PASS, "Atributo OTel deployment.environment=qa presente"))
    else:
        checks.append(CheckResult("otel_environment", CheckStatus.BLOCKED, f"Atributo deployment.environment invalido: '{otel_map.get('deployment.environment')}'"))

    if otel_map.get("app.channel") == "n8n":
        checks.append(CheckResult("otel_channel", CheckStatus.PASS, "Atributo OTel app.channel=n8n presente"))
    else:
        checks.append(CheckResult("otel_channel", CheckStatus.BLOCKED, f"Atributo app.channel invalido: '{otel_map.get('app.channel')}'"))

    # 10. URL da API Local
    try:
        parsed_api = urlparse(api_base_url)
        api_host = parsed_api.hostname or ""
        api_port = parsed_api.port or 80

        if parsed_api.scheme != "http":
            checks.append(CheckResult("api_url_security", CheckStatus.BLOCKED, f"Scheme API invalido: '{parsed_api.scheme}' (apenas 'http' local e permitido)"))
        elif api_host not in ALLOWED_HOSTS:
            checks.append(CheckResult("api_url_security", CheckStatus.BLOCKED, f"Host da API nao e loopback local: '{api_host}'"))
        elif api_port != ALLOWED_API_PORT:
            checks.append(CheckResult("api_url_security", CheckStatus.BLOCKED, f"Porta da API invalida para QA: {api_port} (esperado: {ALLOWED_API_PORT})"))
        else:
            checks.append(CheckResult("api_url_security", CheckStatus.PASS, f"URL da API local validada: {api_base_url}"))
    except Exception as e:
        checks.append(CheckResult("api_url_security", CheckStatus.BLOCKED, f"Erro no parsing da URL da API: {sanitize_text(str(e))}"))

    return checks


def run_redis_ping_check(redis_url: str, timeout: float) -> CheckResult:
    """Executa unicamente PING contra o Redis QA local."""
    try:
        parsed = urlparse(redis_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 6380
        db_str = parsed.path.lstrip("/") if parsed.path else "0"
        db = int(db_str) if db_str.isdigit() else 0
        password = parsed.password

        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
        )
        response = client.ping()
        client.close()

        if response is True:
            return CheckResult("redis_ping", CheckStatus.PASS, "PING no Redis QA respondeu PONG com sucesso")
        else:
            return CheckResult("redis_ping", CheckStatus.FAIL, "Resposta inesperada do PING Redis")
    except redis.exceptions.AuthenticationError:
        return CheckResult("redis_ping", CheckStatus.FAIL, "Falha de autenticacao no Redis QA (authentication_failed)")
    except redis.exceptions.TimeoutError:
        return CheckResult("redis_ping", CheckStatus.FAIL, "Timeout ao conectar no Redis QA (timeout)")
    except redis.exceptions.ConnectionError:
        return CheckResult("redis_ping", CheckStatus.FAIL, "Conexao recusada no Redis QA (connection_refused)")
    except Exception as e:
        return CheckResult("redis_ping", CheckStatus.FAIL, f"Erro na checagem do Redis: {sanitize_text(str(e))}")


def run_api_health_check(api_base_url: str, timeout: float) -> CheckResult:
    """Consulta exclusivamente GET /health na API local com follow_redirects=False."""
    health_url = f"{api_base_url.rstrip('/')}/health"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.get(health_url)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("ok") is True:
                    return CheckResult("api_health", CheckStatus.PASS, f"GET /health respondeu 200 OK (service: {data.get('service', 'bot')})")
                else:
                    return CheckResult("api_health", CheckStatus.FAIL, f"GET /health respondeu 200 mas corpo 'ok' nao e True")
            elif 300 <= resp.status_code < 400:
                return CheckResult("api_health", CheckStatus.FAIL, f"GET /health respondeu redirect {resp.status_code} (inseguro)")
            else:
                return CheckResult("api_health", CheckStatus.FAIL, f"GET /health respondeu status {resp.status_code}")
    except httpx.ConnectError:
        return CheckResult("api_health", CheckStatus.FAIL, "Conexao recusada na API local (connection_refused)")
    except httpx.TimeoutException:
        return CheckResult("api_health", CheckStatus.FAIL, "Timeout ao consultar GET /health na API local (timeout)")
    except Exception as e:
        return CheckResult("api_health", CheckStatus.FAIL, f"Erro no healthcheck da API: {sanitize_text(str(e))}")


def validate_environment(
    env_file_path: str = "qa/.env.qa",
    api_base_url: str = "http://127.0.0.1:8002",
    timeout: float = 2.0,
) -> tuple[ValidationReport, int]:
    """
    Executa o preflight e retorna o relatório estruturado e o exit code.
    """
    config = load_effective_config(env_file_path)

    # Preflight estático
    checks = run_static_preflight(config, api_base_url)

    # Verificar se algum check estático bloqueou a execução
    is_blocked = any(c.status == CheckStatus.BLOCKED for c in checks)

    if is_blocked:
        # Modo fail-closed: não executa chamadas de rede se o preflight estático falhar
        checks.append(CheckResult("redis_ping", CheckStatus.NOT_EXECUTED, "PING do Redis nao executado devido ao bloqueio preflight"))
        checks.append(CheckResult("api_health", CheckStatus.NOT_EXECUTED, "Healthcheck da API nao executado devido ao bloqueio preflight"))
        checks.append(CheckResult("mcp_health", CheckStatus.NOT_EXECUTED, "MCP health: NOT_EXECUTED — fora do preflight obrigatorio do QA-04"))

        report = ValidationReport(
            status=AggregatedStatus.BLOCKED,
            environment=config.get("APP_ENV", "desconhecido"),
            checks=checks,
        )
        return report, 2

    # Executar I/O controlado somente se preflight passou
    redis_url = config.get("REDIS_URL", "")
    redis_check = run_redis_ping_check(redis_url, timeout)
    checks.append(redis_check)

    api_check = run_api_health_check(api_base_url, timeout)
    checks.append(api_check)

    # Check opcional standing de MCP
    checks.append(CheckResult("mcp_health", CheckStatus.NOT_EXECUTED, "MCP health: NOT_EXECUTED — fora do preflight obrigatorio do QA-04"))

    # Determinar status agregado
    has_fail = any(c.status == CheckStatus.FAIL for c in checks)

    if has_fail:
        agg_status = AggregatedStatus.FAIL
        exit_code = 1
    else:
        agg_status = AggregatedStatus.PASS
        exit_code = 0

    report = ValidationReport(
        status=agg_status,
        environment=config.get("APP_ENV", "qa"),
        checks=checks,
    )
    return report, exit_code


def main(args_list: list[str] | None = None) -> int:
    try:
        parsed_args = parse_args(args_list)
        timeout = max(0.1, min(parsed_args.timeout, 2.0))

        report, exit_code = validate_environment(
            env_file_path=parsed_args.env_file,
            api_base_url=parsed_args.api_base_url,
            timeout=timeout,
        )

        report_dict = asdict(report)
        print(json.dumps(report_dict, indent=2, ensure_ascii=False))
        return exit_code
    except Exception as e:
        err_report = {
            "status": "INTERNAL_ERROR",
            "environment": "desconhecido",
            "checks": [
                {
                    "name": "internal_error",
                    "status": "FAIL",
                    "detail": f"Erro interno inesperado no validador: {sanitize_text(str(e))}"
                }
            ]
        }
        print(json.dumps(err_report, indent=2, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    sys.exit(main())

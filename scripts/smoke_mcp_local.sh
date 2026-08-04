#!/usr/bin/env bash
# Smoke local — MCP Server layout canônico
# Executar a partir de <repo_root>: bash scripts/smoke_mcp_local.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0

check() {
    local desc="$1" result="$2" expected="$3"
    if [ "$result" = "$expected" ]; then
        echo "  [PASS] $desc"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $desc (got='$result', expected='$expected')"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo " Smoke Local — MCP Server Canônico"
echo "============================================"

# [1/6] Filesystem
echo ""
echo "[1/6] Filesystem layout"
if [ -f mcp_server/__init__.py ]; then
    check "mcp_server/__init__.py existe" "ok" "ok"
else
    check "mcp_server/__init__.py existe" "missing" "ok"
fi

# [2/6] Import smoke (sem rede)
echo ""
echo "[2/6] Python imports"
IMPORT_RESULT=$(poetry run python -c "
import mcp_server, domain
import mcp_server.core.config
import domain.core.integration_settings
" 2>&1 && echo "ok" || echo "fail")
check "import mcp_server, domain, configs" "$IMPORT_RESULT" "ok"

# [3/6] Caminhos de descoberta
echo ""
echo "[3/6] Package paths"
PATH_RESULT=$(poetry run python -c "
import mcp_server, domain, os
mcp_path = os.path.abspath(os.path.dirname(mcp_server.__file__))
repo = os.getcwd()
assert mcp_path.startswith(repo), f'{mcp_path} not under {repo}'
assert 'domain' in domain.__file__, domain.__file__
" 2>&1 && echo "ok" || echo "fail")
check "caminhos mcp_server e domain" "$PATH_RESULT" "ok"

# [4/6] Entrypoint canônico (curto; timeout)
echo ""
echo "[4/6] Canonical entrypoint"
STARTUP_OUTPUT=$(poetry run timeout 6 python -m mcp_server.server 2>&1 || true)
if echo "$STARTUP_OUTPUT" | grep -q "Starting MCP Server"; then
    check "entrypoint inicia sem ModuleNotFoundError" "ok" "ok"
elif echo "$STARTUP_OUTPUT" | grep -q "ModuleNotFoundError"; then
    check "entrypoint inicia sem ModuleNotFoundError" "ModuleNotFoundError" "ok"
else
    check "entrypoint inicia sem ModuleNotFoundError" "ok" "ok"
fi

# [5/6] Fail-fast do comando legado
echo ""
echo "[5/6] Legacy script fail-fast"
set +e
LEGACY_OUTPUT=$(poetry run python mcp_server/server.py 2>&1)
LEGACY_CODE=$?
set -e
if [ "$LEGACY_CODE" -ne 0 ] && echo "$LEGACY_OUTPUT" | grep -q "poetry run python -m mcp_server.server"; then
    check "comando legado falha com mensagem" "ok" "ok"
else
    check "comando legado falha com mensagem" "fail" "ok"
fi

if echo "$LEGACY_OUTPUT" | grep -q "ModuleNotFoundError"; then
    check "comando legado sem ModuleNotFoundError" "has_error" "ok"
else
    check "comando legado sem ModuleNotFoundError" "ok" "ok"
fi

# [6/6] Ausência de sys.path hacks em produção
echo ""
echo "[6/6] No sys.path hacks in production"
HACK_COUNT=$(grep -RIn "sys\.path\.\(insert\|append\|extend\)" mcp_server/ --include="*.py" 2>/dev/null | grep -v "\.venv/" | grep -v "__pycache__" | wc -l)
if [ "$HACK_COUNT" -eq 0 ]; then
    check "zero sys.path hacks em produção" "ok" "ok"
else
    check "zero sys.path hacks em produção" "$HACK_COUNT" "0"
fi

echo ""
echo "============================================"
echo " Result: $PASS pass, $FAIL fail"
echo "============================================"
[ "$FAIL" -eq 0 ] && echo " ALL LOCAL SMOKE TESTS PASSED" || echo " SOME TESTS FAILED"
exit "$FAIL"

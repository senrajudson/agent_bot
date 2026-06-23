#!/usr/bin/env bash
# ==========================================================
# Valida correção do bug MATH_TOOL_BASE_URL em PRD (Docker)
# ==========================================================
# Uso: bash scripts/validate_mcp_prd.sh
# Pré-requisitos: containers rodando (docker-compose up -d)
set -e

PASS=0
FAIL=0

check() {
    local desc="$1" result="$2" expected="$3"
    if [ "$result" = "$expected" ]; then
        echo "  ✓ PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  ✗ FAIL: $desc (obtido='$result', esperado='$expected')"
        FAIL=$((FAIL + 1))
    fi
}

echo "========================================"
echo " Smoke Test — MCP Server (PRD fix)"
echo "========================================"

# [1] Config carregada pelo container
echo ""
echo "[1/4] Verificando MATH_TOOL_BASE_URL no container mcp_server..."
MATH_URL=$(docker exec mcp_server env 2>/dev/null | grep "^MATH_TOOL_BASE_URL=" | cut -d= -f2- || echo "N/A")
check "MATH_TOOL_BASE_URL=http://math_tool:8001" "$MATH_URL" "http://math_tool:8001"

# [2] Conectividade math_tool via hostname Docker
echo ""
echo "[2/4] Testando conectividade math_tool:8001..."
MATH_STATUS=$(docker exec mcp_server python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('http://math_tool:8001/health', timeout=5)
    print(r.status)
except Exception as e:
    print('FAIL')
" 2>/dev/null)
check "math_tool:8001/health -> 200" "$MATH_STATUS" "200"

# [3] localhost NÃO deve funcionar (esperado: Connection refused = "FAIL")
echo ""
echo "[3/4] Verificando que localhost:8001 NÃO resolve (confirmado bug antigo)..."
LOCALHOST_STATUS=$(docker exec mcp_server python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('http://localhost:8001/health', timeout=5)
    print(r.status)
except Exception:
    print('FAIL')
" 2>/dev/null)
check "localhost:8001 -> Connection refused (bug antigo)" "$LOCALHOST_STATUS" "FAIL"

# [4] Query via agent_bot (chat endpoint)
echo ""
echo "[4/4] Executando query de consumo via agent_bot..."
BEFORE_LOGS=$(docker logs mcp_server --tail 0 2>&1 | wc -l)

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST http://localhost:8002/chat \
    -H "Content-Type: application/json" \
    -d '{"message":"consumo semana passada LFI_RB3_VAZ_GN_TOTAL","user_id":"smoke-prd-validation"}' \
    --max-time 120 2>/dev/null)

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
    check "HTTP 200 no /chat" "200" "200"

    HAS_OUTPUT=$(echo "$BODY" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    output = d.get('output', '')
    if output and 'erro' not in output.lower()[:20]:
        print('YES')
    else:
        print('NO')
except:
    print('NO')
" 2>/dev/null)
    check "Resposta contém output válido" "$HAS_OUTPUT" "YES"
else
    check "HTTP 200 no /chat" "$HTTP_CODE" "200"
fi

echo ""
echo "--- Logs recentes do mcp_server (últimas 20 linhas com math_tool/stats) ---"
docker logs mcp_server --tail 50 2>&1 | grep -iE "math_tool|stats|tag_statistics|error" | tail -10 || echo "  (nenhum log relevante)"

echo ""
echo "========================================"
echo " Resultado: $PASS passed, $FAIL failed"
echo "========================================"
[ "$FAIL" -eq 0 ] && echo " ALL TESTS PASSED" || echo " SOME TESTS FAILED"
exit $FAIL

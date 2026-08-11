#!/usr/bin/env bash
set -euo pipefail

IMAGE="pi_mcp_server:0.1.1"
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
echo " Smoke Test — MCP Docker Layout Fix"
echo "============================================"

# [1] Filesystem
echo ""
echo "[1/5] Filesystem layout"
docker run --rm "$IMAGE" ls -d /app/mcp_server >/dev/null 2>&1
check "/app/mcp_server/ exists" "ok" "ok"

docker run --rm "$IMAGE" ls /app/mcp_server/server.py >/dev/null 2>&1
check "/app/mcp_server/server.py exists" "ok" "ok"

docker run --rm "$IMAGE" ls /app/server.py 2>/dev/null && FOUND=1 || FOUND=0
check "/app/server.py NOT found (flat layout removed)" "$FOUND" "0"

docker run --rm "$IMAGE" ls -d /app/domain >/dev/null 2>&1
check "/app/domain/ exists" "ok" "ok"

# [2] Import smoke
echo ""
echo "[2/5] Python imports"
docker run --rm --entrypoint python "$IMAGE" -c "
import mcp_server
import domain
import mcp_server.services.delivery.output_delivery_policy
" 2>/dev/null
check "import mcp_server, domain, delivery" "ok" "ok"

# [3] CMD
echo ""
echo "[3/5] Entrypoint"
CMD=$(docker inspect "$IMAGE" --format '{{join .Config.Cmd " "}}')
check "CMD contains python -m mcp_server.server" "$CMD" "python -m mcp_server.server"

# [4] Startup — habilitar analysis tools para exercitar imports do profile real
echo ""
echo "[4/5] Container startup"
# Criar credencial dummy para Settings validation (arquivo montado read-only)
DUMMY_SA=$(mktemp /tmp/smoke_sa_XXXXXX.json)
echo '{"type":"service_account","project_id":"smoke-test"}' > "$DUMMY_SA"
trap 'rm -f "$DUMMY_SA"' EXIT
CID=$(docker run -d --rm \
  -v "$DUMMY_SA":/tmp/smoke_sa.json:ro \
  -e MCP_PORT=8005 \
  -e ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY=false \
  -e ENABLE_DRIVE_CSV_EXPORT_TOOL=false \
  -e ENABLE_TEST_ARTIFACT_TOOL=false \
  -e ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV=false \
  -e ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND=false \
  -e ENABLE_MCP_ANALYSIS_TOOLS=true \
  -e PI_WEB_API_BASE_URL=http://10.247.224.39/piwebapi \
  -e MATH_TOOL_BASE_URL=http://localhost:8001 \
  -e GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=/tmp/smoke_sa.json \
  "$IMAGE" 2>/dev/null)

sleep 8
STATUS=$(docker inspect "$CID" --format '{{.State.Status}}' 2>/dev/null || echo "exited")
check "container status running" "$STATUS" "running"

# Check logs for no ModuleNotFoundError
LOGS=$(docker logs "$CID" 2>&1)
MOD_NOT_FOUND=$(echo "$LOGS" | grep -c "ModuleNotFoundError" || true)
check "no ModuleNotFoundError in logs" "$MOD_NOT_FOUND" "0"

# Check port
PORT_OPEN=$(docker exec "$CID" python -c "
import socket; s = socket.create_connection(('127.0.0.1', 8005), 2); s.close(); print('open')
" 2>/dev/null || echo "closed")
check "port 8005 open" "$PORT_OPEN" "open"

docker rm -f "$CID" >/dev/null 2>&1

# [5] MCP protocol (requires running container)
echo ""
echo "[5/5] MCP protocol"
CID=$(docker run -d --rm \
  -v "$DUMMY_SA":/tmp/smoke_sa.json:ro \
  -e MCP_PORT=8005 \
  -e ENABLE_MCP_DRIVE_ARTIFACT_DELIVERY=false \
  -e ENABLE_DRIVE_CSV_EXPORT_TOOL=false \
  -e ENABLE_TEST_ARTIFACT_TOOL=false \
  -e ENABLE_MCP_GENERATE_PI_TAGS_SERIES_CSV=false \
  -e ENABLE_MCP_SEARCH_PI_POINTS_STRICT_AND=false \
  -e ENABLE_MCP_ANALYSIS_TOOLS=true \
  -e PI_WEB_API_BASE_URL=http://10.247.224.39/piwebapi \
  -e MATH_TOOL_BASE_URL=http://localhost:8001 \
  -e GOOGLE_DRIVE_EXPORT_CREDENTIALS_FILE=/tmp/smoke_sa.json \
  "$IMAGE" 2>/dev/null)
sleep 10

# Get session ID
RAW=$(curl -sS -D - -X POST http://localhost:8005/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke-test","version":"1.0"}},"id":1}' 2>/dev/null || echo "FAIL")
echo "$RAW" | grep -q "serverInfo" && INIT_OK="ok" || INIT_OK="fail"
check "MCP initialize" "$INIT_OK" "ok"

SESSION=$(echo "$RAW" | grep -i "mcp-session-id" | awk '{print $2}' | tr -d '\r\n')

TOOLS_JSON=$(curl -sS -X POST http://localhost:8005/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}' 2>/dev/null || echo "FAIL")

TOOL_COUNT=$(echo "$TOOLS_JSON" | grep -oP '"name":"[^"]*"' | wc -l)
check "tools/list returns tools" "$TOOL_COUNT" "7"

docker rm -f "$CID" >/dev/null 2>&1

echo ""
echo "============================================"
echo " Result: $PASS pass, $FAIL fail"
echo "============================================"
[ "$FAIL" -eq 0 ] && echo " ALL SMOKE TESTS PASSED" || echo " SOME TESTS FAILED"
exit "$FAIL"

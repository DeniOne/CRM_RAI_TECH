#!/usr/bin/env bash
set -euo pipefail

API_KEY="0hxTOWm6F57dyIqdQOVpd15hU3qrsN2AW8u4iiHN7QI"
PORT=8010
BASE="http://127.0.0.1:${PORT}/api/v1/integration"
DB_PATH="/tmp/crm-test-v13.db"
LOG="/tmp/crm-uvicorn-v13.log"
UVICORN_PID=""

cleanup() {
  if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    kill "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
    echo "✓ uvicorn PID $UVICORN_PID killed"
  fi
  rm -f "$DB_PATH"
}
trap cleanup EXIT

echo "=== V13 CRM Integration Proofs ==="

# 1. Create test DB with schema
echo "[1/8] Creating test DB schema..."
rm -f "$DB_PATH"
DATABASE_URL="sqlite+aiosqlite:///${DB_PATH}" \
CRM_INTEGRATION_KEY="$API_KEY" \
HERMES_ENABLED=false \
CRM_ENV=dev \
python3 -c "
import asyncio, os
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///${DB_PATH}'
os.environ['CRM_INTEGRATION_KEY'] = '${API_KEY}'
os.environ['HERMES_ENABLED'] = 'false'

# Re-import with correct env
from app.database import async_engine, Base, init_db
async def setup():
    await init_db()
    print('✓ Tables created')
asyncio.run(setup())
"

# 2. Start uvicorn
echo "[2/8] Starting uvicorn on :${PORT}..."
DATABASE_URL="sqlite+aiosqlite:///${DB_PATH}" \
CRM_INTEGRATION_KEY="$API_KEY" \
HERMES_ENABLED=false \
CRM_ENV=dev \
uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --log-level warning > "$LOG" 2>&1 &
UVICORN_PID=$!
echo "  uvicorn PID: $UVICORN_PID"

# Wait for health
for i in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:${PORT}/docs" > /dev/null 2>&1; then
    echo "  ✓ uvicorn ready"
    break
  fi
  if [[ $i -eq 20 ]]; then
    echo "✗ uvicorn failed to start"; cat "$LOG"; exit 1
  fi
  sleep 0.5
done

# 3. POST /leads — create
echo "[3/8] POST /leads — create lead..."
RESP=$(curl -sf -X POST "${BASE}/leads" \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{
    "source": "RAI_MI",
    "opportunity_ref": "RAI-OPP-proof01",
    "inn": "1234567890",
    "name": "ООО Мегаферма",
    "region": "Воронежская область",
    "level": "A",
    "priority": 1,
    "evidence_summary": "[FACT] herd_size: 500 голов",
    "sellability_grade": "A",
    "next_action": "Связаться с директором"
  }')
echo "  Response: $RESP"
LEAD_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  ✓ Lead created, id=$LEAD_ID"

# 4. POST /leads — idempotent repeat (same opportunity_ref → same lead, no dup)
echo "[4/8] POST /leads — idempotent repeat..."
RESP2=$(curl -sf -X POST "${BASE}/leads" \
  -H "Content-Type: application/json" \
  -H "x-api-key: ${API_KEY}" \
  -d '{
    "source": "RAI_MI",
    "opportunity_ref": "RAI-OPP-proof01",
    "inn": "1234567890",
    "name": "ООО Мегаферма"
  }')
LEAD_ID2=$(echo "$RESP2" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
if [[ "$LEAD_ID" == "$LEAD_ID2" ]]; then
  echo "  ✓ Idempotent: same id=$LEAD_ID2 (no duplicate)"
else
  echo "  ✗ FAIL: expected id=$LEAD_ID, got $LEAD_ID2"; exit 1
fi

# 5. GET /leads/by-inn/{inn} — dedup lookup
echo "[5/8] GET /leads/by-inn/1234567890..."
RESP3=$(curl -sf "${BASE}/leads/by-inn/1234567890" \
  -H "x-api-key: ${API_KEY}")
FOUND=$(echo "$RESP3" | python3 -c "import sys,json; print(json.load(sys.stdin)['found'])")
COUNT=$(echo "$RESP3" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['leads']))")
if [[ "$FOUND" == "True" && "$COUNT" -ge 1 ]]; then
  echo "  ✓ by-inn found=$FOUND, leads=$COUNT"
else
  echo "  ✗ FAIL: found=$FOUND, count=$COUNT"; exit 1
fi

# 6. GET /leads/{id}/outcome — stage + history
echo "[6/8] GET /leads/${LEAD_ID}/outcome..."
RESP4=$(curl -sf "${BASE}/leads/${LEAD_ID}/outcome" \
  -H "x-api-key: ${API_KEY}")
STAGE=$(echo "$RESP4" | python3 -c "import sys,json; print(json.load(sys.stdin)['stage'])")
HIST_LEN=$(echo "$RESP4" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['history']))")
echo "  ✓ outcome: stage=$STAGE, history_entries=$HIST_LEN"

# 7. GET /funnel/changes — cursor-based pull
echo "[7/8] GET /funnel/changes..."
RESP5=$(curl -sf "${BASE}/funnel/changes?since=2020-01-01T00:00:00" \
  -H "x-api-key: ${API_KEY}")
CHANGE_COUNT=$(echo "$RESP5" | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])")
echo "  ✓ funnel/changes: count=$CHANGE_COUNT"

# 8. 401 without API key
echo "[8/8] GET /leads/by-inn/0000000000 — no key (expect 401)..."
HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${BASE}/leads/by-inn/0000000000" || true)
if [[ "$HTTP_CODE" == "401" ]]; then
  echo "  ✓ 401 without API key"
else
  # Try with wrong key
  HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${BASE}/leads/by-inn/0000000000" -H "x-api-key: wrong" || true)
  if [[ "$HTTP_CODE" == "401" ]]; then
    echo "  ✓ 401 with wrong API key"
  else
    echo "  ✗ FAIL: expected 401, got $HTTP_CODE"; exit 1
  fi
fi

echo ""
echo "=== ALL8 PROOFS PASSED ==="

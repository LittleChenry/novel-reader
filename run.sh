#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="/tmp/venv/bin/python"
LOG_FILE="/tmp/flask.log"
PID_FILE="/tmp/flask.pid"
XRAY_DIR="/tmp/xray"
XRAY_PID_FILE="/tmp/xray.pid"
PORT=5000

ensure_venv() {
  if [ ! -f "$VENV_PYTHON" ]; then
    echo "[run] Creating venv..."
    python3 -m venv /tmp/venv
    echo "[run] Installing deps..."
    /tmp/venv/bin/pip install --quiet flask flask-limiter pycryptodome requests beautifulsoup4 lxml bcrypt
    echo "[run] Done"
  fi
}

ensure_xray() {
  if [ -f "$XRAY_DIR/xray" ]; then
    return 0
  fi
  echo "[run] Downloading xray..."
  mkdir -p "$XRAY_DIR"
  python3 -c "
import requests, os, zipfile, io
url = 'https://gh-proxy.com/https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip'
r = requests.get(url, stream=True, timeout=300)
z = zipfile.ZipFile(io.BytesIO(r.content))
for name in z.namelist():
    if name.endswith('/'): continue
    z.extract(name, '$XRAY_DIR')
os.chmod('$XRAY_DIR/xray', 0o755)
print('xray ready')
" 2>&1 | tail -1
}

write_xray_config() {
  if [ -z "$PROXY_SUB_URL" ]; then
    echo "[run] PROXY_SUB_URL not set, skipping xray config"
    return 0
  fi
  local cfg
  cfg=$("$VENV_PYTHON" -c "
import sys, json
sys.path.insert(0, '$APP_DIR')
from spiders.proxy_manager import proxy_mgr, build_config
try:
    proxy_mgr.load()
    node = proxy_mgr.nodes[0]
    cfg = build_config(node)
    print(json.dumps(cfg))
except Exception as e:
    print(f'ERROR:{e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null)
  if [ $? -eq 0 ] && [ -n "$cfg" ]; then
    echo "$cfg" > "$XRAY_DIR/config.json"
    local tag
    tag=$(echo "$cfg" | python3 -c "import sys,json; print(json.load(sys.stdin)['outbounds'][0]['settings']['vnext'][0]['address'])" 2>/dev/null)
    echo "[run] xray config generated via proxy_manager ($tag)"
  else
    echo "[run] proxy_manager failed to generate config, check PROXY_SUB_URL"
    return 1
  fi
}

start_xray() {
  ensure_xray
  write_xray_config || return 0
  if [ ! -f "$XRAY_DIR/config.json" ]; then
    echo "[run] xray disabled (no proxy config)"
    return 0
  fi
  if [ -f "$XRAY_PID_FILE" ] && kill -0 "$(cat "$XRAY_PID_FILE")" 2>/dev/null; then
    return
  fi
  nohup "$XRAY_DIR/xray" run -c "$XRAY_DIR/config.json" > /tmp/xray.log 2>&1 &
  echo $! > "$XRAY_PID_FILE"
  sleep 2
  if kill -0 "$(cat "$XRAY_PID_FILE")" 2>/dev/null; then
    echo "[run] xray proxy started (PID $(cat "$XRAY_PID_FILE"))"
  else
    echo "[run] xray proxy failed to start"
  fi
}

stop_xray() {
  if [ -f "$XRAY_PID_FILE" ]; then
    kill "$(cat "$XRAY_PID_FILE")" 2>/dev/null || true
    rm -f "$XRAY_PID_FILE"
  fi
  pkill -f "xray run" 2>/dev/null || true
}

start() {
  ensure_venv
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "[run] Already running (PID $(cat "$PID_FILE"))"
    return
  fi
  start_xray
  echo "[run] Starting Flask..."
  nohup "$VENV_PYTHON" "$APP_DIR/app.py" >> "$LOG_FILE" 2>&1 &
  PID=$!
  echo "$PID" > "$PID_FILE"
  sleep 2
  if kill -0 "$PID" 2>/dev/null; then
    echo "[run] Flask started (PID $PID) http://0.0.0.0:$PORT"
  else
    echo "[run] Flask failed to start, see log: $LOG_FILE"
    tail -5 "$LOG_FILE"
  fi
}

stop() {
  if [ -f "$PID_FILE" ]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null && echo "[run] Flask stopped" || true
    rm -f "$PID_FILE"
  else
    pkill -f "app.py" 2>/dev/null && echo "[run] Flask stopped" || true
  fi
  stop_xray
}

restart() {
  stop
  sleep 1
  start
}

status() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "[run] Flask running (PID $(cat "$PID_FILE"))"
  else
    echo "[run] Flask not running"
  fi
  if [ -f "$XRAY_PID_FILE" ] && kill -0 "$(cat "$XRAY_PID_FILE")" 2>/dev/null; then
    echo "[run] xray running (PID $(cat "$XRAY_PID_FILE"))"
  else
    echo "[run] xray not running"
  fi
}

log() {
  tail -f "$LOG_FILE"
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  status) status ;;
  log) log ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|log}"
    exit 1
    ;;
esac

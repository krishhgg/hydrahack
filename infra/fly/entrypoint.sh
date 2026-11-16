#!/bin/bash
# Runs HydraDB and the app in one container. If either exits, the container exits so Fly restarts it.
set -euo pipefail

# Fly volumes are mounted root-owned; the engine runs as uid 10001.
mkdir -p /data/store /data/cache /run/hydradb
chown -R 10001:10001 /data /run/hydradb
drop=(setpriv --reuid=10001 --regid=10001 --clear-groups)

# HYDRADB_TOKEN comes from a Fly secret; generate one if absent (valid for this boot only).
export HYDRADB_TOKEN="${HYDRADB_TOKEN:-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')}"
export HYDRADB_URL=http://127.0.0.1:8443
export HYDRADB_ADMIN_URL=http://127.0.0.1:9090

# Answer on the public port right away: Render's free tier gives HydraDB 0.1 CPU, so it needs several
# minutes to open the store, and Render fails the deploy when nothing listens on $PORT in that time.
# Until the app takes over, /health answers 200 with ready:false (Render's health check needs a 2xx
# to promote the deploy) and every other path gets a 503 that says the instance is warming up.
"${drop[@]}" python -c '
import http.server, json, os
body = json.dumps({"ok": False, "ready": False, "status": "warming"}).encode()
class H(http.server.BaseHTTPRequestHandler):
    def _r(self):
        if self.path == "/__diag":
            try:
                text = open("/tmp/diag.txt", "rb").read()
            except OSError:
                text = b"no diag yet"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(text)))
            self.end_headers()
            self.wfile.write(text)
            return
        self.send_response(200 if self.path == "/health" else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Retry-After", "30")
        self.end_headers()
        self.wfile.write(body)
    do_GET = do_POST = do_HEAD = _r
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), H).serve_forever()
' &
warm=$!

"${drop[@]}" /usr/local/bin/hydradb-entrypoint > >(tee -a /tmp/engine.log) 2>&1 &
db=$!

# Temporary: a snapshot of the engine's state at /__diag on the warm-up listener, because Render's
# log stream stops forwarding this container's output after the first second.
(
  while true; do
    {
      date -u +%T
      echo "uptime=$SECONDS cpu.max=$(cat /sys/fs/cgroup/cpu.max 2>/dev/null) $(tr '
' ' ' </sys/fs/cgroup/cpu.stat 2>/dev/null)"
      echo "mem.current=$(cat /sys/fs/cgroup/memory.current 2>/dev/null) events=$(tr '
' ' ' </sys/fs/cgroup/memory.events 2>/dev/null)"
      ps -eo pid,stat,pcpu,rss,nlwp,etime,time,comm 2>&1 | head -20
      echo "readyz: $(timeout 8 bash -c 'exec 3<>/dev/tcp/127.0.0.1/9090; printf "GET /readyz HTTP/1.0

" >&3; head -n1 <&3' 2>&1)"
      echo "--- engine log tail"
      tail -n 25 /tmp/engine.log 2>&1 | cut -c1-220
    } > /tmp/diag.tmp 2>&1
    mv /tmp/diag.tmp /tmp/diag.txt
    sleep 10
  done
) &
diag_worker=$!

# Engine state for the platform log while it opens its store (Render shows nothing else after the
# first lines, so a hang there is otherwise invisible).
diag() {
  local pid
  pid=$(pgrep -x graph-node | head -n1 || true)
  echo "diag t=${SECONDS}s engine_pid=${pid:-none} $(grep -E 'State|VmRSS|Threads' "/proc/${pid:-0}/status" 2>/dev/null | tr -s ' 	
' ' ')" >&2
  echo "diag mem.current=$(cat /sys/fs/cgroup/memory.current 2>/dev/null) max=$(cat /sys/fs/cgroup/memory.max 2>/dev/null) events=$(tr '
' ' ' </sys/fs/cgroup/memory.events 2>/dev/null) load=$(cut -d' ' -f1-3 /proc/loadavg) free=$(free -m | awk '/Mem:/{print $3"/"$2"MB"}')" >&2
  echo "diag store: $(du -sk /data/store 2>/dev/null | cut -f1)KB listening: $(ss -ltn 2>/dev/null | awk 'NR>1{print $4}' | tr '
' ' ')" >&2
}

ready=0
last=-30
while [ "$SECONDS" -lt 1200 ]; do
  if ! kill -0 "$db" 2>/dev/null; then
    code=0
    wait "$db" || code=$?
    echo "hydradb exited during startup (status $code; 137 = killed, 132 = illegal instruction, 139 = segfault)" >&2
    echo "diagnostics: $(uname -sr) | cpu flags: $(grep -m1 -o 'avx[0-9a-z_]*' /proc/cpuinfo | sort -u | tr '
' ' ') | mem: $(cat /sys/fs/cgroup/memory.max 2>/dev/null) | /data: $(df -h /data | tail -1)" >&2
    exit 1
  fi
  if timeout 20 "${drop[@]}" /usr/local/bin/hydradb-healthcheck >/dev/null 2>&1; then
    ready=1
    break
  fi
  if [ $((SECONDS - last)) -ge 30 ]; then diag; last=$SECONDS; fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "hydradb did not become healthy in 1200s" >&2; diag; exit 1; }
echo "hydradb healthy"
kill "$warm" "$diag_worker" 2>/dev/null || true
wait "$warm" 2>/dev/null || true

cd /app
if [ "$APP_MODULE" = "hydrahack.api:app" ] && ! python -c 'import importlib.util as u; raise SystemExit(u.find_spec("hydrahack.api") is None)'; then
  echo "hydrahack.api not found, serving the infra.app_stub health app instead" >&2
  APP_MODULE=infra.app_stub:app
fi
echo "starting app: $APP_MODULE on :${PORT:-8080}"
"${drop[@]}" uvicorn "$APP_MODULE" --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers &
app=$!

trap 'kill "$db" "$app" 2>/dev/null || true' TERM INT
status=0
wait -n "$db" "$app" || status=$?
echo "a process exited (status $status), stopping container" >&2
kill "$db" "$app" 2>/dev/null || true
wait || true
exit 1

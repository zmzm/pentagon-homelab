from flask import Flask, jsonify
import os
import requests
import time
import atexit
from threading import Lock

app = Flask(__name__)

PIHOLE_BASE_URL = os.environ.get("PIHOLE_BASE_URL", "http://100.126.16.76:8081").rstrip("/")
PIHOLE_PASSWORD = os.environ.get("PIHOLE_PASSWORD", "")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "10"))
SUMMARY_CACHE_TTL = int(os.environ.get("SUMMARY_CACHE_TTL", "5"))

http = requests.Session()

_cached_sid = None
_sid_expires_at = 0
_sid_lock = Lock()

_summary_cache = None
_summary_cache_until = 0
_summary_lock = Lock()


def log(msg: str):
    print(f"[pid={os.getpid()}] {msg}", flush=True)


def login() -> tuple[str, int]:
    resp = http.post(
        f"{PIHOLE_BASE_URL}/api/auth",
        json={"password": PIHOLE_PASSWORD},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    session = data.get("session", {})
    sid = session.get("sid") or data.get("sid")
    validity = int(session.get("validity", 300))

    if not sid:
        raise RuntimeError("Pi-hole authentication returned no session ID")

    log(f"Pi-hole session created; validity={validity}s")
    return sid, validity


def logout(sid: str | None) -> None:
    if not sid:
        return
    try:
        resp = http.delete(
            f"{PIHOLE_BASE_URL}/api/auth",
            headers={"X-FTL-SID": sid},
            timeout=REQUEST_TIMEOUT,
        )
        log(f"Pi-hole logout status: {resp.status_code}")
    except Exception as e:
        log(f"Pi-hole logout failed ({type(e).__name__})")


def clear_cached_sid() -> None:
    global _cached_sid, _sid_expires_at
    old_sid = _cached_sid
    _cached_sid = None
    _sid_expires_at = 0
    log("Clearing cached Pi-hole session")
    logout(old_sid)


def get_sid() -> str:
    global _cached_sid, _sid_expires_at

    with _sid_lock:
        now = time.time()

        if _cached_sid and now < (_sid_expires_at - 10):
            log("Using cached Pi-hole session")
            return _cached_sid

        old_sid = _cached_sid
        sid, validity = login()

        _cached_sid = sid
        _sid_expires_at = now + max(validity, 60)

        if old_sid and old_sid != sid:
            logout(old_sid)

        return _cached_sid


def fetch_summary() -> dict:
    sid = get_sid()

    log("Requesting Pi-hole statistics summary")
    resp = http.get(
        f"{PIHOLE_BASE_URL}/api/stats/summary",
        headers={"X-FTL-SID": sid},
        timeout=REQUEST_TIMEOUT,
    )

    log(f"summary response status: {resp.status_code}")

    if resp.status_code in (401, 403):
        log("SID rejected, relogin")
        clear_cached_sid()
        sid = get_sid()

        resp = http.get(
            f"{PIHOLE_BASE_URL}/api/stats/summary",
            headers={"X-FTL-SID": sid},
            timeout=REQUEST_TIMEOUT,
        )
        log(f"summary retry status: {resp.status_code}")

    resp.raise_for_status()
    data = resp.json()

    queries = data.get("queries", {})
    clients = data.get("clients", {})
    gravity = data.get("gravity", {})

    return {
        "status": "online",
        "queries_total": queries.get("total", 0),
        "queries_blocked": queries.get("blocked", 0),
        "percent_blocked": queries.get("percent_blocked", 0),
        "unique_clients": clients.get("active", 0),
        "domains_being_blocked": gravity.get("domains_being_blocked", 0),
    }


@atexit.register
def cleanup():
    clear_cached_sid()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/pihole-summary")
def pihole_summary():
    global _summary_cache, _summary_cache_until

    try:
        now = time.time()

        with _summary_lock:
            if _summary_cache is not None and now < _summary_cache_until:
                log("Returning cached summary")
                return jsonify(_summary_cache)

        result = fetch_summary()

        with _summary_lock:
            _summary_cache = result
            _summary_cache_until = time.time() + SUMMARY_CACHE_TTL

        return jsonify(result)

    except Exception as e:
        error_type = type(e).__name__
        log(f"Pi-hole summary failed ({error_type})")
        return jsonify({"status": "error", "error": error_type}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)

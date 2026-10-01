import time

from .security import digest


def within_quota(request):
    """Only validated, live sessions may select a principal quota."""
    settings = request.app.state.settings
    now = int(time.time() // 60)
    kind = "write" if request.method not in {"GET", "HEAD"} else "read"
    limit = settings.write_limit_per_minute if kind == "write" else settings.read_limit_per_minute
    peer = request.client.host if request.client else "unknown"
    with request.app.state.db.transaction() as conn:
        session = None
        raw = request.cookies.get("ig_session", "")
        if raw and not request.url.path.startswith("/api/v1/auth/"):
            session = conn.execute(
                "SELECT user_id FROM sessions WHERE token_hash=%s AND expires_at>now() "
                "AND last_seen>now()-(%s * interval '1 second')",
                (digest(raw), settings.session_idle_seconds),
            ).fetchone()
        identity = "user:" + str(session["user_id"]) if session else "ip:" + peer
        bucket = digest(identity) + kind
        conn.execute("DELETE FROM rate_limits WHERE window_id<%s", (now - 2,))
        count = conn.execute(
            "INSERT INTO rate_limits VALUES(%s,%s,1) ON CONFLICT(bucket) DO UPDATE "
            "SET window_id=excluded.window_id,count=CASE "
            "WHEN rate_limits.window_id=excluded.window_id "
            "THEN rate_limits.count+1 ELSE 1 END RETURNING count",
            (bucket, now),
        ).fetchone()["count"]
    return count <= limit

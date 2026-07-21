import json
import threading
import urllib.error
import urllib.request

from jobscope.core.config import load_config
from jobscope.core.store import Store
from jobscope.deliver import serve


def _cfg(tmp_path):
    cfg = load_config(None)
    cfg["output"]["db_path"] = str(tmp_path / "campaign-api.db")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    cfg["serve"]["web_dist"] = str(dist)
    return cfg


def _request(method, url, *, token="", body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Refresh-Token"] = token
        headers["Origin"] = url.split("/api/", 1)[0]
    request = urllib.request.Request(
        url, method=method, headers=headers,
        data=(json.dumps(body).encode("utf-8") if body is not None else None),
    )
    try:
        response = urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))
    return response.status, json.loads(response.read().decode("utf-8"))


def test_campaign_api_is_local_token_guarded_and_rejects_unknown_fields(tmp_path):
    cfg = _cfg(tmp_path)
    Store(cfg["output"]["db_path"]).close()
    httpd, _, token, _ = serve._build_server(cfg, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        code, denied = _request("GET", base + "/api/campaigns")
        assert code == 403 and denied["error"] == "forbidden"

        code, created = _request(
            "POST", base + "/api/campaigns", token=token,
            body={"name": "India security", "requested_count": 2},
        )
        assert code == 200 and created["ok"] is True
        assert len(created["targets"]) == 2
        campaign_id = created["campaign"]["id"]

        code, listing = _request("GET", base + "/api/campaigns", token=token)
        assert code == 200 and listing["campaigns"][0]["id"] == campaign_id

        code, detail = _request(
            "GET", base + f"/api/campaigns/detail?id={campaign_id}", token=token,
        )
        assert code == 200 and detail["campaign"]["id"] == campaign_id

        code, tracking = _request(
            "POST", base + "/api/campaigns/action", token=token,
            body={"action": "check_replies", "fetch": True},
        )
        assert code == 200 and tracking["ok"] is True
        assert tracking["inbox_status"] == "not_needed"

        code, rejected = _request(
            "POST", base + "/api/campaigns/action", token=token,
            body={"action": "approve", "target_id": "missing", "force": True},
        )
        assert code == 400 and "unknown action field" in rejected["error"]

        code, deleted = _request(
            "POST", base + "/api/campaigns/action", token=token,
            body={"action": "delete", "campaign_id": campaign_id},
        )
        assert code == 200 and deleted["deleted_campaign_id"] == campaign_id
        code, listing = _request("GET", base + "/api/campaigns", token=token)
        assert code == 200 and listing["campaigns"] == []
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)
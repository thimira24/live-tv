#!/usr/bin/env python3
"""Request-handler core for the IPTV web player.

  - /proxy?url=..&cc=..&ua=..&rf=..  HLS proxy: adds CORS, rewrites .m3u8
    children to route back through it, sends per-stream User-Agent/Referer,
    and optionally routes through a per-country upstream proxy.
  - /config  (GET returns, POST sets) per-country upstream proxies.
  - /check   (POST) batch reachability probe used by the "playable only" filter.
"""
import http.server
import json
import os
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, urljoin, quote, unquote

DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SSL_CTX = ssl._create_unverified_context()

# Per-country upstream proxies: {"United States": "socks5h://..", ...}; default for the rest.
STATE = {"profiles": {}, "default": os.environ.get("IPTV_UPSTREAM_PROXY", "").strip()}


def _proxy_for(cc):
    return (STATE["profiles"].get(cc, "") or STATE["default"]).strip()


def _build_opener(proxy_url):
    handlers = []
    if proxy_url:
        if proxy_url.lower().startswith(("socks5", "socks4")):
            try:
                from sockshandler import SocksiPyHandler
                import socks
                u = urlparse(proxy_url)
                stype = socks.SOCKS5 if "socks5" in u.scheme else socks.SOCKS4
                rdns = u.scheme.endswith("h")
                handlers.append(SocksiPyHandler(stype, u.hostname, u.port or 1080,
                                                rdns=rdns, username=u.username,
                                                password=u.password))
            except Exception as e:
                raise RuntimeError(f"SOCKS proxy needs PySocks (pip3 install PySocks): {e}")
        else:
            handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    handlers.append(urllib.request.HTTPSHandler(context=SSL_CTX))
    return urllib.request.build_opener(*handlers)


def _open(target, cc, ua, rf):
    opener = _build_opener(_proxy_for(cc))
    headers = {"User-Agent": ua or DEFAULT_UA, "Accept": "*/*"}
    if rf:
        headers["Referer"] = rf
    return opener.open(urllib.request.Request(target, headers=headers), timeout=18)


def _is_manifest(target, content_type, head):
    if target.split("?")[0].lower().endswith(".m3u8"):
        return True
    if "mpegurl" in (content_type or "").lower():
        return True
    return head[:7] == b"#EXTM3U"


def _rewrite_manifest(text, base_url, suffix):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out.append(line)
            continue
        if s.startswith("#"):
            if 'URI="' in s:
                pre, rest = s.split('URI="', 1)
                uri, post = rest.split('"', 1)
                absu = urljoin(base_url, uri)
                s = f'{pre}URI="/proxy?url={quote(absu, safe="")}{suffix}"{post}'
            out.append(s)
        else:
            absu = urljoin(base_url, s)
            out.append("/proxy?url=" + quote(absu, safe="") + suffix)
    return "\n".join(out) + "\n"


def _probe(item):
    url = (item or {}).get("url")
    if not url:
        return {"ok": False, "code": 0}
    try:
        resp = _open(url, (item.get("cc") or ""), (item.get("ua") or ""), (item.get("rf") or ""))
        code = getattr(resp, "status", 200) or 200
        resp.read(64)
        resp.close()
        return {"ok": 200 <= code < 400, "code": code}
    except urllib.error.HTTPError as e:
        return {"ok": False, "code": e.code}
    except Exception:
        return {"ok": False, "code": 0}


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _send_json(self, obj, code=200):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.startswith("/proxy"):
            return self.handle_proxy()
        if self.path.startswith("/config"):
            return self._send_json({"profiles": STATE["profiles"], "default": STATE["default"]})
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/config"):
            return self.handle_config_post()
        if self.path.startswith("/check"):
            return self.handle_check()
        self.send_error(404)

    def handle_config_post(self):
        data = self._read_json()
        profiles = data.get("profiles", {})
        if isinstance(profiles, dict):
            STATE["profiles"] = {str(k).strip(): str(v).strip()
                                 for k, v in profiles.items() if str(v).strip()}
        STATE["default"] = str(data.get("default", "")).strip()
        self._send_json({"profiles": STATE["profiles"], "default": STATE["default"]})

    def handle_check(self):
        items = self._read_json().get("items", [])
        items = items[:64] if isinstance(items, list) else []
        with ThreadPoolExecutor(max_workers=16) as ex:
            results = list(ex.map(_probe, items))
        self._send_json({"results": results})

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return {}

    def handle_proxy(self):
        qs = parse_qs(urlparse(self.path).query)
        target = qs.get("url", [None])[0]
        if not target:
            self.send_error(400, "missing url")
            return
        target = unquote(target)
        cc = unquote(qs.get("cc", [""])[0])
        ua = unquote(qs.get("ua", [""])[0])
        rf = unquote(qs.get("rf", [""])[0])
        # keep per-stream context on child (segment/variant) fetches
        suffix = ""
        for k, v in (("cc", cc), ("ua", ua), ("rf", rf)):
            if v:
                suffix += f"&{k}=" + quote(v, safe="")

        try:
            resp = _open(target, cc, ua, rf)
        except urllib.error.HTTPError as e:
            self.send_error(502, f"upstream {e.code}")
            return
        except Exception as e:
            self.send_error(502, f"proxy error: {e}")
            return

        ctype = resp.headers.get("Content-Type", "application/octet-stream")
        head = resp.read(64)
        if _is_manifest(target, ctype, head):
            body = head + resp.read()
            text = body.decode("utf-8", errors="replace")
            out = _rewrite_manifest(text, target, suffix).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
        else:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                self.wfile.write(head)
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

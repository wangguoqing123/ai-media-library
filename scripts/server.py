#!/usr/bin/env python3
"""Small loopback-only viewer/editor. Collection and AI reasoning stay in the Agent."""
import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from library import Library


def serve(root, port=0):
    root = str(Path(root).resolve())
    lib = Library(root)
    lib.close()
    token = secrets.token_urlsafe(24)
    html = (Path(__file__).parent.parent / "assets" / "index.html").read_text(encoding="utf-8").replace("__LOCAL_TOKEN__", token)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, data, code=200, content_type="application/json; charset=utf-8"):
            body = data.encode("utf-8") if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host") == "127.0.0.1:" + str(self.server.server_port)

        def do_GET(self):
            if not self.valid_host():
                return self.send({"error": "仅支持本机地址"}, 403)
            if self.path == "/":
                return self.send(html, content_type="text/html; charset=utf-8")
            if self.path == "/api/health":
                return self.send({"ok": True})
            if self.path != "/api/state":
                return self.send({"error": "未找到"}, 404)
            db = Library(root)
            try:
                self.send({"config": db.config(), "services": db.services(), "materials": db.all("materials"), "topics": db.all("topics")})
            finally:
                db.close()

        def do_POST(self):
            origin = self.headers.get("Origin")
            expected = "http://127.0.0.1:" + str(self.server.server_port)
            if not self.valid_host() or origin not in (None, expected) or self.headers.get("X-Library-Token") != token:
                return self.send({"error": "请在自己的内容库页面操作"}, 403)
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self.send({"error": "需要 JSON 内容"}, 415)
            db = None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2 * 1024 * 1024:
                    raise ValueError("输入内容过大或为空")
                payload = json.loads(self.rfile.read(length))
                db = Library(root)
                if self.path == "/api/material":
                    data = db.material(payload, manual=True)
                elif self.path == "/api/topic":
                    data = db.topic_update(payload["id"], payload["patch"])
                elif self.path == "/api/config":
                    data = db.configure(payload)
                else:
                    return self.send({"error": "未找到"}, 404)
                db.export()
                self.send({"ok": True, "data": data})
            except (ValueError, KeyError, TypeError):
                self.send({"error": "保存失败：请检查必填项、状态和发布链接"}, 400)
            finally:
                if db:
                    db.close()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(json.dumps({"url": "http://127.0.0.1:" + str(server.server_port), "stop": "在此终端按 Ctrl+C；重新运行原命令可继续使用"}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    serve(args.root, args.port)

#!/usr/bin/env python3
"""叙阅公网预览聚合代理（cpolar 演示用，临时工具）

单入口：静态前端(dist) + /api/* 转发到本地后端。
客户通过 cpolar 公网域名访问时，页面与 API 同源，无跨域问题。
用法：python tools/preview_proxy.py [port]
"""
import http.server
import os
import socketserver
import sys
import urllib.error
import urllib.request

BACKEND = os.environ.get("PREVIEW_BACKEND", "http://127.0.0.1:6888")
DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dist")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PREVIEW_PORT", "6890"))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIST, **kw)

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(BACKEND + self.path, data=body, method=self.command)
        for k, v in self.headers.items():
            if k.lower() in ("host", "content-length", "connection", "accept-encoding"):
                continue
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
                status = resp.status
                ctype = resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            # 后端返回的 4xx/5xx 是正常业务响应，原样透传，别当成代理故障
            data = e.read()
            status = e.code
            ctype = e.headers.get("Content-Type", "application/json")
        except Exception as e:  # noqa: BLE001
            self.send_error(502, f"Backend proxy failed: {e}")
            return
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            super().do_GET()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_PATCH(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def do_OPTIONS(self):
        self._proxy()

    # SPA history 路由回退 index.html：路径不是真实文件时，回退到 dist/index.html
    def translate_path(self, path):
        resolved = super().translate_path(path)
        if not os.path.isfile(resolved):
            return os.path.join(self.directory, "index.html")
        return resolved


if __name__ == "__main__":
    if not os.path.isdir(DIST):
        sys.exit(f"dist 不存在: {DIST}，先跑 VITE_USE_RELATIVE_API=true npm run build")
    with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"[preview_proxy] :{PORT}  dist={DIST}  backend={BACKEND}", flush=True)
        httpd.serve_forever()

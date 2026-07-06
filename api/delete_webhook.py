from http.server import BaseHTTPRequestHandler
import os
import json
import requests


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def do_GET(self):
        if not BOT_TOKEN:
            self._send_json(500, {
                "ok": False,
                "error": "BOT_TOKEN is missing."
            })
            return

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
                json={"drop_pending_updates": True},
                timeout=10
            )
            data = response.json()
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return

        self._send_json(200, {
            "telegram_response": data
        })

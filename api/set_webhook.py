from http.server import BaseHTTPRequestHandler
import os
import json
import requests


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
VERCEL_URL = os.getenv("VERCEL_URL", "").strip()


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
                "error": "BOT_TOKEN is missing. Add it in Vercel Environment Variables."
            })
            return

        webhook_url = WEBHOOK_URL
        if not webhook_url and VERCEL_URL:
            webhook_url = f"https://{VERCEL_URL}/api/bot"

        if not webhook_url:
            self._send_json(500, {
                "ok": False,
                "error": "WEBHOOK_URL is missing. Add WEBHOOK_URL=https://your-project.vercel.app/api/bot in Vercel Environment Variables."
            })
            return

        payload = {
            "url": webhook_url,
            "allowed_updates": ["message", "edited_message"],
            "drop_pending_updates": True
        }

        if WEBHOOK_SECRET:
            payload["secret_token"] = WEBHOOK_SECRET

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json=payload,
                timeout=10
            )
            data = response.json()
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return

        self._send_json(200, {
            "requested_webhook_url": webhook_url,
            "telegram_response": data
        })

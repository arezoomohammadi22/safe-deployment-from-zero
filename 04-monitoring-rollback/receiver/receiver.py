"""Local webhook viewer for Alertmanager; not an incident paging solution."""
import json
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

EVENTS = deque(maxlen=100)
LOCK = Lock()

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/alerts':
            return self.reply(404, {'error': 'not found'})
        try:
            count = int(self.headers.get('Content-Length', '-1'))
            if count < 0 or count > 1_000_000:
                return self.reply(413, {'error': 'invalid size'})
            data = json.loads(self.rfile.read(count))
            if not isinstance(data, dict) or 'alerts' not in data:
                return self.reply(400, {'error': 'invalid payload'})
        except (ValueError, UnicodeDecodeError):
            return self.reply(400, {'error': 'invalid JSON'})
        item = {'received_at': datetime.now(timezone.utc).isoformat(), 'status': data.get('status'),
                'alerts': [{'name': a.get('labels',{}).get('alertname'), 'status': a.get('status'),
                            'summary': a.get('annotations',{}).get('summary')} for a in data.get('alerts', [])]}
        with LOCK:
            EVENTS.appendleft(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)
        self.reply(200, {'stored': True})

    def do_GET(self):
        if self.path != '/events':
            return self.reply(404, {'error': 'not found'})
        with LOCK:
            events = list(EVENTS)
        self.reply(200, {'events': events})

    def reply(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080),Handler).serve_forever()

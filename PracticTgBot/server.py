from http.server import HTTPServer, SimpleHTTPRequestHandler
import socketserver

class MyHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Добавляем заголовок для обхода localtunnel
        self.send_header('Bypass-Tunnel-Reminder', '1')
        super().end_headers()

PORT = 3000
with socketserver.TCPServer(("", PORT), MyHandler) as httpd:
    print(f"Serving at port {PORT}")
    httpd.serve_forever()
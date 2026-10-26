"""Capturas do portal estático (sem backend) por tema e largura. Uso: shoot.py <static_dir> <out_dir>"""
import http.server, socketserver, sys, threading, functools, os
from playwright.sync_api import sync_playwright
static, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
class H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        p = path.split('?')[0]
        routes = {'/clinica/login': 'clinica.html', '/paciente/': 'index.html', '/clinica/senha': 'senha.html', '/clinica/usuarios': 'usuarios.html'}
        if p in routes: return os.path.join(static, routes[p])
        if p.startswith('/static/'): return os.path.join(static, p[len('/static/'):])
        return os.path.join(static, '__404__')
    def log_message(self, *a): pass
srv = socketserver.TCPServer(('127.0.0.1', 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
pages = {'login': '/clinica/login', 'senha': '/clinica/senha', 'paciente': '/paciente/'}
ext = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--font-render-hinting=none'])
    for theme in ('dark', 'light', 'none'):
        for w in (1440, 390):
            ctx = b.new_context(viewport={'width': w, 'height': 900}, color_scheme='dark')
            if theme != 'none':
                ctx.add_init_script(f"localStorage.setItem('lex-theme','{theme}')")
            pg = ctx.new_page()
            pg.on('request', lambda r: ext.append(r.url) if not r.url.startswith(f'http://127.0.0.1:{port}') else None)
            pg.route('**/api/**', lambda r: r.fulfill(status=401, body='{}'))
            for name, url in pages.items():
                pg.goto(f'http://127.0.0.1:{port}{url}'); pg.wait_for_load_state('networkidle')
                pg.evaluate('document.fonts.ready')
                pg.screenshot(path=f'{out}/{name}-{theme}-{w}.png', full_page=True)
            ctx.close()
    b.close()
print('externos:', sorted(set(ext)))

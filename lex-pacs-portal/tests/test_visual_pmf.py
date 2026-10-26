"""LX1–LX12 — identidade visual PMF só no tema claro (claro passa a ser o padrão)."""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TW = ROOT / "ohif-viewer/platform/ui-next/src/tailwind.css"
PORTAL_CSS = ROOT / "lex-pacs-portal/static/portal.css"
STATIC = ROOT / "lex-pacs-portal/static"

# sha256 de sem_claro(<arquivo em main 0ab4d15>): tudo que NÃO é regra [data-theme='light'].
HASH_NAO_CLARO = {
    TW: "05e5003dd829df665831f0353f3b166fb28c0573d8c274450044613c97d56eed",
    PORTAL_CSS: "7d8d8105fc999429f8776a4d503ed2e6b6d31670cec47988b3e203516a871eef",
}
# sha256 do bloco ":root, [data-theme='dark'] { ... }" em main (byte a byte).
HASH_BLOCO_ESCURO = {
    TW: (
        "  :root,\n  [data-theme='dark'] {",
        "\n  }\n",
        "1a14ee4e692cd05843fc8350205d02b46d879eb976cdc0f226170ff7ed402d83",
    ),
    PORTAL_CSS: (
        ":root,\n[data-theme='dark'] {",
        "\n}\n",
        "1c9227c27ce8153506002369891e553c2c238bc54876172efcbe097af667d27c",
    ),
}


def sem_claro(css: str) -> str:
    """Remove comentários e toda regra cujo seletor é prefixado por [data-theme='light']
    (também dentro de @media/@layer); normaliza espaços. O que sobra é o 'não-claro'."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    def walk(text):
        res, k = [], 0
        while True:
            m = text.find("{", k)
            if m < 0:
                res.append(text[k:])
                break
            sel = text[k:m]
            # fecha o bloco
            depth, j = 0, m
            while True:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            body = text[m + 1 : j]
            s = sel.strip()
            sels = _split_top(s) if not s.startswith("@") else []
            if sels and all(x.startswith("[data-theme='light']") for x in sels):
                pass  # regra do claro: ignorada
            elif s.startswith("@") or "{" in body:
                inner = walk(body)
                if inner.strip():
                    res.append(sel + "{" + inner + "}")
            else:
                res.append(sel + "{" + body + "}")
            k = j + 1
        return "".join(res)

    return re.sub(r"\s+", " ", walk(css)).strip()


def _split_top(sel):
    parts, depth, cur = [], 0, ""
    for ch in sel:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    parts.append(cur.strip())
    return [p for p in parts if p]


def _light_block(css: str) -> str:
    a = css.index("[data-theme='light'] {")
    return css[a : css.index("}", a)]


def test_lx1_escuro_byte_a_byte_e_so_regras_do_claro_mudaram():
    for path, (ini, fim, esperado) in HASH_BLOCO_ESCURO.items():
        css = path.read_text(encoding="utf-8")
        a = css.index(ini)
        bloco = css[a : css.index(fim, a) + len(fim)]
        assert hashlib.sha256(bloco.encode()).hexdigest() == esperado, path.name
    for path, esperado in HASH_NAO_CLARO.items():
        got = hashlib.sha256(
            sem_claro(path.read_text(encoding="utf-8")).encode()
        ).hexdigest()
        assert got == esperado, f"{path.name}: regra fora de [data-theme='light'] mudou"


def test_lx3_primaria_0066cc_sem_vermelho_de_marca_no_claro():
    tw = _light_block(TW.read_text(encoding="utf-8"))
    assert (
        "--primary: 210 100% 40%;" in tw and "--ring: 210 100% 40%;" in tw
    )  # = #0066CC
    assert "0 85% 4" not in tw
    pc = _light_block(PORTAL_CSS.read_text(encoding="utf-8"))
    assert "--red: #0066cc;" in pc and "--brand: #0066cc;" in pc
    assert "#b80000" not in pc and "#cc0000" not in pc
    css = PORTAL_CSS.read_text(encoding="utf-8")
    assert (
        "[data-theme='light'] .error { color: var(--danger); }" in css
    )  # vermelho só para erro
    assert "[data-theme='light'] .hint a { color: var(--brand) !important; }" in css


def test_lx5_area_dicom_preta_no_claro():
    css = TW.read_text(encoding="utf-8")
    assert re.search(
        r"\[data-theme='light'\] \.cornerstone-viewport-element \{\s*background-color: #000;",
        css,
    )
    vp = (
        ROOT
        / "ohif-viewer/extensions/cornerstone/src/Viewport/OHIFCornerstoneViewport.tsx"
    ).read_text(encoding="utf-8")
    assert 'className="cornerstone-viewport-element"' in vp


def test_lx7_ibm_plex_local_so_no_claro():
    tw = TW.read_text(encoding="utf-8")
    assert "font-family: 'IBM Plex Sans'" in _light_block(tw)
    assert (
        "html { font-family: 'Roboto', 'Inter', sans-serif; }" in tw
    )  # escuro segue Roboto/Inter
    pc = PORTAL_CSS.read_text(encoding="utf-8")
    assert "[data-theme='light'] body { font-family: 'IBM Plex Sans'" in pc
    assert "font-family: Roboto, Inter, sans-serif;" in pc
    for fonts_css, base in (
        (STATIC / "fonts/plex.css", None),
        (
            ROOT / "ohif-viewer/platform/ui-next/src/assets/fonts.css",
            ROOT
            / "ohif-viewer/platform/ui-next/src",  # fonts.css é @import inline em src/tailwind.css
        ),
    ):
        txt = fonts_css.read_text(encoding="utf-8")
        assert "IBM Plex Sans" in txt and "IBM Plex Mono" in txt
        assert not re.search(r"url\(['\"]?(https?:)?//", txt), "fonte externa (CDN)"
        for url in re.findall(r"url\('([^']*plex[^']*)'\)", txt):
            f = (
                (STATIC / url.removeprefix("/static/"))
                if base is None
                else (base / url)
            )
            assert f.is_file() and f.read_bytes()[:4] == b"wOF2", url
    for page in ("clinica", "senha", "usuarios", "index"):
        assert '<link rel="stylesheet" href="/static/fonts/plex.css" />' in (
            STATIC / f"{page}.html"
        ).read_text(encoding="utf-8")


def test_padrao_claro_sem_escolha_salva_e_escuro_no_alternador():
    ts = (ROOT / "ohif-viewer/platform/ui-next/src/contexts/lexTheme.ts").read_text(
        encoding="utf-8"
    )
    assert "prefers-color-scheme" not in ts and ts.count("return 'light';") >= 2
    assert "LEX_THEME_STORAGE_KEY = 'lex-theme'" in ts
    js = (STATIC / "theme.js").read_text(encoding="utf-8")
    assert "prefers-color-scheme" not in js and "return 'light';" in js
    assert (
        "toggleTheme" in js and "STORAGE_KEY = 'lex-theme'" in js
    )  # LX10: alternador e chave mantidos
    tpl = (
        ROOT / "ohif-viewer/platform/app/public/html-templates/index.html"
    ).read_text(encoding="utf-8")
    assert "prefers-color-scheme" not in tpl
    for page in ("clinica", "senha", "usuarios", "index"):
        html = (STATIC / f"{page}.html").read_text(encoding="utf-8")
        assert "s === 'light' || s === 'dark' ? s : 'light'" in html, page


def test_lx8_lx11_login_prefeitura_de_franca_e_logo_pmf():
    for page in ("clinica", "senha"):
        html = (STATIC / f"{page}.html").read_text(encoding="utf-8")
        assert '<body class="lex-auth">' in html
        assert re.search(
            r'<aside class="pmf-brand-panel" hidden[^>]*>', html
        )  # escondido no escuro
        assert (
            "Prefeitura de Franca" in html and 'src="/static/pmf-catavento.png"' in html
        )
    pc = PORTAL_CSS.read_text(encoding="utf-8")
    assert "[data-theme='light'] body.lex-auth .pmf-brand-panel {" in pc
    assert "@media (min-width: 1024px)" in pc and "@media (max-width: 1023.98px)" in pc
    for png in (
        STATIC / "pmf-catavento.png",
        ROOT / "ohif-viewer/platform/app/public/pmf-catavento.png",
    ):
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    cfg = (ROOT / "ohif-viewer/platform/app/public/config/default.js").read_text(
        encoding="utf-8"
    )
    assert "lex-logo-lex" in cfg and "lex-logo-pmf" in cfg and "hidden: true" in cfg
    tw = TW.read_text(encoding="utf-8")
    assert (
        "[data-theme='light'] .lex-logo-lex" in tw
        and "[data-theme='light'] .lex-logo-pmf" in tw
    )


def test_lx12_cores_de_anotacao_intocadas():
    # As cores de anotação/medidas do Cornerstone vêm da config de ferramentas, não dos tokens CSS.
    tw = TW.read_text(encoding="utf-8")
    assert "annotation" not in tw.lower() and "measurement" not in tw.lower()


def test_lx9_lx6_foco_brand_e_mono_tabular_no_claro_do_viewer():
    css = TW.read_text(encoding="utf-8")
    assert re.search(
        r"\[data-theme='light'\] :is\([^)]*\):focus-visible \{\s*outline: 2px solid #0066cc;",
        css,
    )
    assert re.search(
        r"\[data-theme='light'\] \.lex-num \{[^}]*IBM Plex Mono[^}]*tabular-nums", css
    )

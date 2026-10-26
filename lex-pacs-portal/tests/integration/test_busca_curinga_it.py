"""LP4 / LP5 / LP9 parcial — integração com Orthanc local sintético via gateway nginx real.

Roda só via scripts/it-busca-curinga.sh (variáveis LEX_IT_*). Sem elas, é pulado.
"""
import json
import os
import statistics
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

GW = os.environ.get("LEX_IT_GATEWAY")
pytestmark = pytest.mark.skipif(not GW, reason="integração: rode scripts/it-busca-curinga.sh")

ROOT = Path(os.environ.get("LEX_IT_ROOT", Path(__file__).resolve().parents[3]))
MOD = ROOT / "ohif-viewer/extensions/default/src/DicomWebDataSource/lexQidoFilters.js"
INCLUDE = "00081030,00080060,00080090"
TIMES: dict[str, list[float]] = {}


def js_query(fn: str, value: str) -> str:
    """Usa o MESMO módulo do OHIF (lexQidoFilters.js) para montar o filtro."""
    code = f"import('{MOD.as_uri()}').then(m=>process.stdout.write(JSON.stringify(m.{fn}({json.dumps(value)}) ?? null)))"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.fixture(scope="module")
def s():
    c = httpx.Client(base_url=GW, timeout=60)
    r = c.post("/clinica-api/auth/clinical/login", json={"username": "admin", "password": "Admin-Inicial-IT1"})
    assert r.status_code == 200, r.text
    r = c.post("/clinica-api/auth/clinical/change-password",
               json={"current_password": "Admin-Inicial-IT1", "new_password": "Admin-Nova-IT-2026"})
    assert r.status_code == 200, r.text
    yield c
    print("\n== Tempos (s) via gateway, 3 medições ==")
    for k, v in TIMES.items():
        print(f"{k}: " + ", ".join(f"{x:.3f}" for x in v) + f"  (mediana {statistics.median(v):.3f})")


def qido(s, label, **params):
    params = {k: v for k, v in params.items() if v is not None}
    params.setdefault("limit", 101)
    params.setdefault("offset", 0)
    params.setdefault("includefield", INCLUDE)
    params.setdefault("fuzzymatching", "false")
    runs = []
    for _ in range(3):
        t = time.perf_counter()
        # igual ao dicomweb-client do OHIF (encodeURIComponent não escapa "*")
        qs = "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='*')}" for k, v in params.items())
        r = s.get(f"/dicom-web/studies?{qs}")
        runs.append(time.perf_counter() - t)
        assert r.status_code in (200, 204), (r.status_code, r.text[:200])
    TIMES[label] = runs
    return r.json() if r.status_code == 200 and r.text.strip() else []


def ids(results):
    return {x.get("00100020", {}).get("Value", [""])[0] for x in results}


def test_lista_padrao_so_101_e_alvo_fora(s):
    res = qido(s, "lista padrão (limit=101)")
    assert len(res) == 101
    assert "SINT-ALVO" not in ids(res)


def test_lp4_nome_parcial_sem_acento_acha_paciente_fora_dos_101(s):
    for typed in ("conceição", "Conceicao", "maria helena", "CONCEI"):
        q = js_query("patientNameQuery", typed)
        assert q.startswith("*") and q.endswith("*")
        res = qido(s, f"nome '{typed}' -> {q}", PatientName=q)
        assert "SINT-ALVO" in ids(res), (typed, q)


def test_lp4_menos_de_3_letras_sem_curinga(s):
    q = js_query("patientNameQuery", "co")
    assert q == "CO"
    assert qido(s, "nome 'co' (sem curinga)", PatientName=q) == []


def test_busca_por_id_exato_fora_dos_101(s):
    q = js_query("exactQuery", " SINT-ALVO ")
    res = qido(s, "ID exato", **{"00100020": q})
    assert ids(res) == {"SINT-ALVO"}


def test_nome_gravado_com_acento_ressalva_conhecida(s):
    """Orthanc não ignora acento no valor GRAVADO: digitar com acento acha; sem acento, não.
    Documentado como limitação (resolvida no PR de busca no servidor)."""
    sem = qido(s, "nome gravado com acento, digitado 'avila'", PatientName=js_query("patientNameQuery", "avila"))
    assert "SINT-ALVO-ACENTO" not in ids(sem)
    parte_sem_acento = qido(s, "nome gravado com acento, digitado 'vila'", PatientName=js_query("patientNameQuery", "vila"))
    assert "SINT-ALVO-ACENTO" in ids(parte_sem_acento)


def test_lp5_so_get_no_orthanc(s):
    before = httpx.get(f"{os.environ['LEX_IT_ORTHANC']}/statistics",
                       auth=tuple(os.environ["LEX_IT_ORTHANC_AUTH"].split(":", 1))).json()["CountStudies"]
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        assert s.request(method, "/dicom-web/studies", content=b"x").status_code == 403, method
        assert s.request(method, "/wado", content=b"x").status_code == 403, method
    after = httpx.get(f"{os.environ['LEX_IT_ORTHANC']}/statistics",
                      auth=tuple(os.environ["LEX_IT_ORTHANC_AUTH"].split(":", 1))).json()["CountStudies"]
    assert before == after >= int(os.environ["LEX_IT_N"])
    log = Path(os.environ["LEX_IT_ACCESS_LOG"]).read_text(encoding="utf-8")
    dicomweb_lines = [line for line in log.splitlines() if " /dicom-web" in line]
    assert dicomweb_lines
    # tudo que passou do gateway ao Orthanc foi GET (os demais métodos ficaram em 403)
    for line in dicomweb_lines:
        method = line.split('"')[1].split()[0]
        status = line.split('"')[2].split()[0]
        assert method == "GET" or status == "403", line


def test_lp9_log_do_nginx_sem_nome_nem_id(s):
    qido(s, "busca para o teste de log", PatientName=js_query("patientNameQuery", "conceição"))
    s.get("/viewer/", params={"patientName": "CONCEICAO", "mrn": "SINT-ALVO"},
          headers={"Referer": f"{GW}/viewer/?patientName=CONCEICAO"})
    time.sleep(0.5)
    log = Path(os.environ["LEX_IT_ACCESS_LOG"]).read_text(encoding="utf-8")
    assert "/dicom-web/studies" in log
    for secret in ("CONCEICAO", "conceicao", "SINT-ALVO", "PatientName", "00100020", "patientName", "mrn="):
        assert secret not in log, secret
    assert "?" not in "".join(line.split('"')[1] for line in log.splitlines() if '"' in line)

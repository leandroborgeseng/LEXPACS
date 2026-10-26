import httpx
import pytest

from app import homolog_seed as hs


@pytest.mark.parametrize("url", ["http://172.21.31.198:8042", "http://172.21.31.198", "https://orthanc.prefeitura.example:8042",
                                 "http://10.0.0.5:8042", "http://server.evil.example:8042", "http://", "ftp://x"])
def test_recusa_host(url):
    with pytest.raises(hs.HostRecusado):
        hs.checar_host(url)


def test_recusa_producao_explicitamente():
    with pytest.raises(hs.HostRecusado, match="produção"):
        hs.checar_host("http://172.21.31.198:8042/")


@pytest.mark.parametrize("url", ["http://server:8042", "http://localhost:8042/", "http://127.0.0.1:18142"])
def test_aceita_hosts_locais(url):
    assert hs.checar_host(url) == url.rstrip("/")


def _nunca(*a, **kw):
    raise AssertionError("não deveria abrir conexão")


@pytest.mark.parametrize("env", [{}, {"HOMOLOG_SEED": ""}, {"HOMOLOG_SEED": "  "}, {"HOMOLOG_SEED": "0"}])
def test_sem_variavel_sai_zero_sem_fazer_nada(env):
    assert hs.run(env, client_factory=_nunca) == 0


def test_run_recusa_producao_sem_conectar():
    assert hs.run({"HOMOLOG_SEED": "10", "ORTHANC_URL": "http://172.21.31.198:8042"}, client_factory=_nunca) == 3


class _Orthanc:
    def __init__(self, inicial=0):
        self.n, self.posts, self.auth = inicial, 0, None

    def __call__(self, req: httpx.Request):
        assert req.url.host == "server"
        self.auth = req.headers.get("authorization")
        if req.method == "GET" and req.url.path == "/statistics":
            return httpx.Response(200, json={"CountStudies": self.n})
        if req.method == "POST" and req.url.path == "/instances":
            self.posts += 1
            self.n += 1
            return httpx.Response(200, json={"Status": "Success"})
        return httpx.Response(404)


def _factory(fake):
    return lambda **kw: httpx.Client(transport=httpx.MockTransport(fake), **kw)


def test_idempotente_orthanc_com_exames_nao_semeia():
    fake = _Orthanc(inicial=5)
    assert hs.run({"HOMOLOG_SEED": "300"}, client_factory=_factory(fake)) == 0
    assert fake.posts == 0


def test_semeia_n_e_espera_todos_gravados_credenciais_do_ambiente():
    fake = _Orthanc()
    env = {"HOMOLOG_SEED": "250", "ORTHANC_USERNAME": "seed", "ORTHANC_PASSWORD": "x"}
    assert hs.run(env, client_factory=_factory(fake)) == 0
    assert fake.posts == fake.n == 250 and fake.auth.startswith("Basic ")


def test_plano_homolog_tem_alvo_2023_maria_ana_jose():
    itens = hs.plano(10000, maria=hs.MARIA_HOMOLOG)
    assert len(itens) == 10000
    assert ("ZZTESTE^JOSÉ CONCEIÇÃO", "SINT-ZZ-2023", "20230505") == itens[-1][1:4]
    nomes = [i[1] for i in itens]
    assert sum(n.startswith("ZZTESTE") and "^MARIA " in n for n in nomes) == 3500
    assert any("^ANA " in n for n in nomes) and any("^JOSE " in n for n in nomes)
    assert all(n.startswith("ZZTESTE") for n in nomes if not n.startswith(("CONCEICAO", "ÁVILA")))


def test_compose_portal_espera_seed_e_seed_nao_reinicia():
    yaml = pytest.importorskip("yaml")
    from pathlib import Path
    c = yaml.safe_load((Path(__file__).resolve().parents[2] / "docker-compose.coolify.yml").read_text())["services"]
    assert c["portal"]["depends_on"]["seed-homolog"] == {"condition": "service_completed_successfully"}
    s = c["seed-homolog"]
    assert s["restart"] == "no" and s["image"] == c["portal"]["image"]
    assert s["command"] == ["python", "-m", "app.homolog_seed"]
    assert s["environment"]["HOMOLOG_SEED"] == "${HOMOLOG_SEED:-}"
    assert s["environment"]["ORTHANC_URL"] == "http://server:8042"

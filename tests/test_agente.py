import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agente_pisos import __main__ as agente
from agente_pisos import informe, texto
from agente_pisos.almacen import Almacen
from agente_pisos.avisos.whatsapp import trocear
from agente_pisos.config import cargar, radio_km
from agente_pisos.filtros import calcular_distancia, motivo_descarte, ordenar, quitar_duplicados
from agente_pisos.fuentes import idealista, portales
from agente_pisos.modelos import Piso

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def cfg():
    return cargar(RAIZ / "config.yaml")


def piso(**kw):
    base = dict(id="x:1", fuente="x", url="https://x/1", titulo="Piso", precio=150000, habitaciones=2)
    base.update(kw)
    return Piso(**base)


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("Certificado energético: E", "E"),
        ("Calificación energética (consumo) D", "D"),
        ("eficiencia energética: letra g", "G"),
        ("Clase energética A. Muy luminoso", "A"),
        ("Certificado energético en trámite", "en trámite"),
        ("Certificación energética: exento", "exento"),
        ("Piso reformado de 3 habitaciones", None),
        ("Calificación energética: Excelente estado", None),
    ],
)
def test_energia(entrada, esperado):
    assert texto.energia(entrada) == esperado


def test_garaje_y_trastero():
    assert texto.menciona_garaje("Incluye plaza de garaje")
    assert not texto.menciona_garaje("Piso sin garaje")
    assert texto.menciona_trastero("Con trastero en el bajo")
    assert not texto.menciona_trastero("sin trastero")


def test_radio(cfg):
    assert radio_km(cfg) == pytest.approx(2.5)
    cfg["busqueda"]["modo"] = "andando"
    assert radio_km(cfg) == pytest.approx(0.4)


def test_filtros(cfg):
    centro = cfg["busqueda"]["centro"]
    cerca = piso(lat=centro["lat"] + 0.005, lon=centro["lon"])  # ~0,55 km
    lejos = piso(lat=43.33, lon=-8.41)  # ~4,7 km (Elviña)
    for p in (cerca, lejos):
        calcular_distancia(p, cfg)
    assert motivo_descarte(cerca, cfg) is None
    assert cerca.minutos_centro == pytest.approx(1.1, abs=0.1)
    assert motivo_descarte(lejos, cfg) == "lejos del centro"
    assert motivo_descarte(piso(precio=171000), cfg) == "precio"
    assert motivo_descarte(piso(habitaciones=1), cfg) == "habitaciones"
    cfg["busqueda"]["exigir_calificacion_energetica"] = True
    assert motivo_descarte(cerca, cfg) == "sin calificación energética"
    cerca.energia = "E"
    assert motivo_descarte(cerca, cfg) is None


def test_ordenar_mas_barato_y_extras_primero():
    a = piso(id="a", precio=160000)
    b = piso(id="b", precio=120000)
    c = piso(id="c", precio=120000, trastero=True)
    assert [p.id for p in ordenar([a, b, c])] == ["c", "b", "a"]


def test_duplicados_entre_portales():
    a = piso(id="idealista:1", metros=70, direccion="Calle Real 10")
    b = piso(id="fotocasa:abc", fuente="fotocasa", url="https://f/1", metros=70.2,
             direccion="Calle Real, 10", energia="F", trastero=True)
    unicos = quitar_duplicados([a, b])
    assert len(unicos) == 1
    assert unicos[0].energia == "F" and unicos[0].trastero
    assert unicos[0].otras_fuentes == ["https://f/1"]


def test_almacen_nuevos_y_bajadas(tmp_path):
    ruta = tmp_path / "vistos.json"
    al = Almacen(ruta)
    nuevos, bajadas = al.clasificar([piso()])
    assert len(nuevos) == 1 and not bajadas
    al.guardar()
    al = Almacen(ruta)
    nuevos, bajadas = al.clasificar([piso(precio=140000)])
    assert not nuevos and bajadas[0][1] == 150000


def test_idealista_a_piso():
    e = {
        "propertyCode": "123", "price": 155000.0, "rooms": 3, "size": 80.0,
        "address": "Calle San Andrés", "neighborhood": "Centro", "latitude": 43.37,
        "longitude": -8.40, "url": "https://www.idealista.com/inmueble/123/",
        "parkingSpace": {"hasParkingSpace": True}, "hasLift": True, "floor": "3",
        "description": "Certificado energético: E. Trastero incluido.",
    }
    p = idealista.a_piso(e)
    texto.enriquecer(p)
    assert (p.id, p.precio, p.garaje, p.trastero, p.energia) == ("idealista:123", 155000, True, True, "E")


def test_portal_extraccion(monkeypatch):
    monkeypatch.setattr(portales, "descargar_texto", lambda url: "página")
    falso = SimpleNamespace(extraer_anuncios=lambda url, t: [
        {"url": "https://www.pisos.com/comprar/piso-1/", "titulo": "Piso", "precio": 130000,
         "habitaciones": 2, "metros": 65, "direccion": "Rúa Nueva", "barrio": "Centro",
         "calificacion_energetica": "F", "garaje": False, "trastero": True, "ascensor": None,
         "planta": "2", "descripcion": ""},
        {"url": "", "precio": None},  # incompleto: se ignora
    ])
    pisos = portales.buscar({"nombre": "pisos.com", "url": "https://www.pisos.com/x"}, falso)
    assert len(pisos) == 1 and pisos[0].id.startswith("pisos.com:") and pisos[0].trastero


def test_trocear():
    texto_largo = "\n".join(f"línea {i} " + "x" * 100 for i in range(50))
    trozos = trocear(texto_largo, 500)
    assert all(len(t) <= 500 for t in trozos)
    assert "\n".join(trozos) == texto_largo


def test_informes(cfg):
    p = piso(metros=70, energia="E", garaje=True, barrio="Pescadería", distancia_km=0.8, minutos_centro=1.6)
    wa = informe.whatsapp([p], [(piso(id="b", precio=140000), 150000)], cfg)
    assert "150.000 €" in wa and "⭐" in wa and "⚡E" in wa and "antes 150.000 €" in wa
    html = informe.email_html([p], [], [p], cfg, ["Idealista: error"])
    assert "Pescadería" in html and "2.143 €/m²" in html and "Idealista: error" in html


def test_ejecucion_completa_sin_red(cfg, monkeypatch, tmp_path):
    """Recorre todo el flujo con fuentes simuladas y comprueba qué se envía."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = cfg["busqueda"]["centro"]
    candidatos = [
        piso(id="i:1", precio=165000, lat=c["lat"], lon=c["lon"], descripcion="Calificación energética: D"),
        piso(id="i:2", precio=125000, lat=c["lat"], lon=c["lon"], descripcion="con trastero"),
        piso(id="i:3", precio=100000, habitaciones=1, lat=c["lat"], lon=c["lon"]),
        piso(id="i:4", precio=110000, lat=43.33, lon=-8.41),
    ]
    monkeypatch.setattr(agente, "recoger", lambda cfg, ia, errores: [Piso(**p.a_dict()) for p in candidatos])
    monkeypatch.setattr(agente, "completar_energia", lambda *a: None)
    enviados = {}
    monkeypatch.setattr(agente.whatsapp, "enviar", lambda t, prov: enviados.setdefault("wa", t))
    monkeypatch.setattr(agente.email, "enviar", lambda asunto, html, t: enviados.setdefault("email", asunto))

    assert agente.ejecutar(cfg, prueba=False, todos=False) == 0
    assert "2 piso(s) nuevo(s)" in enviados["email"] and "125.000" in enviados["email"]
    assert enviados["wa"].index("125.000") < enviados["wa"].index("165.000")
    vistos = json.loads(Path("data/vistos.json").read_text())
    assert set(vistos) == {"i:1", "i:2"}

    enviados.clear()
    assert agente.ejecutar(cfg, prueba=False, todos=False) == 0
    assert not enviados  # segunda vez: nada nuevo


def test_claude_peticion_y_respuesta(monkeypatch):
    """Comprueba la petición que se manda a la API de Claude sin usar la red."""
    import anthropic
    import httpx2 as httpx

    from agente_pisos import ia as modulo_ia

    peticiones = []

    def responder(req):
        peticiones.append((dict(req.headers), json.loads(req.content)))
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "content": [{"type": "text", "text": json.dumps({"calificacion_energetica": "E"})}],
        })

    cliente = anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(responder)))
    monkeypatch.setattr(modulo_ia.anthropic, "Anthropic", lambda: cliente)
    claude = modulo_ia.ClaudeInmobiliario("claude-opus-5-5", "low")
    assert claude.buscar_energia("https://x", "Certificado: E") == "E"
    cabeceras, cuerpo = peticiones[0]
    assert cuerpo["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in cabeceras["anthropic-beta"]
    assert cuerpo["output_config"]["format"]["type"] == "json_schema"


def test_plataformas_filtra_dominio_y_subastas(cfg):
    from agente_pisos.fuentes import plataformas

    llamadas = {}

    class IAFalsa:
        def investigar_plataforma(self, nombre, dominio, criterios, max_busquedas):
            llamadas["criterios"] = criterios
            return "notas de la búsqueda"

        def extraer_anuncios(self, url, texto):
            return [
                {"url": "https://www.escrapalia.com/subasta/piso-coruna-1", "titulo": "Piso", "precio": 90000,
                 "habitaciones": 3, "metros": 80, "direccion": "Os Mallos", "barrio": "", "calificacion_energetica": None,
                 "garaje": False, "trastero": False, "ascensor": None, "planta": "", "descripcion": "",
                 "tipo_venta": "subasta", "fin_subasta": "2026-11-02"},
                {"url": "https://www.otraweb.com/piso-2", "precio": 80000, "habitaciones": 2},
            ]

    pisos = plataformas.buscar({"nombre": "Escrapalia", "dominio": "escrapalia.com"}, IAFalsa(), cfg)
    assert len(pisos) == 1 and pisos[0].tipo_venta == "subasta" and pisos[0].fin_subasta == "2026-11-02"
    assert "170000" in llamadas["criterios"] and "A Coruña" in llamadas["criterios"]
    wa = informe.whatsapp(pisos, [], cfg)
    assert "🔨 subasta hasta 2026-11-02" in wa and "(Escrapalia)" in wa


def test_investigar_plataforma_reanuda_pause_turn(monkeypatch):
    import anthropic
    import httpx2 as httpx

    from agente_pisos import ia as modulo_ia

    cuerpos = []
    respuestas = iter([("pause_turn", "Primera parte."), ("end_turn", "Segunda parte.")])

    def responder(req):
        cuerpos.append(json.loads(req.content))
        motivo, txt = next(respuestas)
        return httpx.Response(200, json={
            "id": "msg", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "stop_reason": motivo, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
            "content": [{"type": "text", "text": txt}],
        })

    cliente = anthropic.Anthropic(api_key="t", http_client=httpx.Client(transport=httpx.MockTransport(responder)))
    monkeypatch.setattr(modulo_ia.anthropic, "Anthropic", lambda: cliente)
    notas = modulo_ia.ClaudeInmobiliario("claude-opus-5-5").investigar_plataforma("Sareb", "sareb.es", "pisos", 3)
    assert notas == "Primera parte.\nSegunda parte."
    herramientas = {t["name"]: t for t in cuerpos[0]["tools"]}
    assert herramientas["web_search"]["allowed_domains"] == ["sareb.es"]
    assert herramientas["web_fetch"]["max_uses"] == 9
    assert [m["role"] for m in cuerpos[1]["messages"]] == ["user", "assistant"]

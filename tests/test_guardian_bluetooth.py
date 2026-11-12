import pytest

from guardian_bluetooth.__main__ import main
from guardian_bluetooth.bluez import Bluetoothctl, Dispositivo, normalizar_mac, parsear_escaneo, parsear_info, parsear_lista
from guardian_bluetooth.lista import MisDispositivos
from guardian_bluetooth.vigilante import Vigilante, revisar_equipo, revisar_visibles

BOSE = "04:52:C7:AA:BB:CC"
MOVIL = "A8:9C:ED:11:22:33"
VECINO = "5C:F3:70:99:88:77"

ESCANEO = f"""\x1b[0;94m[NEW]\x1b[0m Device {BOSE} Bose Revolve
[NEW] Device {VECINO} Galaxy vecino
Discovery started
[CHG] Controller 00:1A:7D:DA:71:13 Discovering: yes
[NEW] Device {BOSE} Bose Revolve
[CHG] Device {BOSE} Class: 0x00240414
[CHG] Device {BOSE} RSSI: -58
[NEW] Device {VECINO} Galaxy vecino
[CHG] Device {VECINO} RSSI: 0xffffffc4 (-60)
[NEW] Device 7A:01:02:03:04:05 7A-01-02-03-04-05
[DEL] Device 7A:01:02:03:04:05 7A-01-02-03-04-05
"""

INFO = f"""Device {VECINO} (public)
\tName: Galaxy vecino
\tAlias: Galaxy vecino
\tClass: 0x005a020c
\tPaired: yes
\tTrusted: no
\tBlocked: no
\tConnected: yes
\tRSSI: -61
"""


@pytest.fixture
def mios(tmp_path):
    m = MisDispositivos(tmp_path / "mios.json")
    m.anadir(BOSE, "Bose Revolve")
    m.anadir(MOVIL.lower(), "Mi móvil")
    return m


class FalsoBt:
    """Simula bluetoothctl y apunta las órdenes recibidas."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.ordenes = []

    def __call__(self, args, timeout):
        self.ordenes.append(args)
        return self.respuestas.get(" ".join(args), self.respuestas.get(args[0], ""))


def test_normalizar_mac():
    assert normalizar_mac("04-52-c7-aa-bb-cc") == BOSE
    with pytest.raises(ValueError):
        normalizar_mac("04:52; rm -rf /")


def test_parsear_lista_e_info():
    lista = parsear_lista(f"Device {BOSE} Bose Revolve\nDevice {MOVIL} Mi móvil\nbasura\n")
    assert [d.mac for d in lista] == [BOSE, MOVIL]
    d = parsear_info(INFO)
    assert (d.mac, d.nombre, d.emparejado, d.confiado, d.conectado, d.rssi, d.clase) == (
        VECINO, "Galaxy vecino", True, False, True, -61, "0x005a020c")


def test_parsear_escaneo_ignora_la_cache_y_los_borrados():
    v = parsear_escaneo(ESCANEO)
    assert set(v) == {BOSE, VECINO}
    assert v[BOSE].clasico and v[BOSE].rssi == -58
    assert v[VECINO].rssi == -60 and v[VECINO].nombre == "Galaxy vecino"
    # Sin búsqueda real, lo que lista de memoria no cuenta como visible... salvo que no haya marca.
    assert parsear_escaneo(f"[NEW] Device {BOSE} Bose") .keys() == {BOSE}


def test_lista_se_guarda_y_recarga(mios):
    otra = MisDispositivos(mios.ruta)
    assert BOSE in otra and MOVIL in otra
    assert otra.nombre(BOSE) == "Bose Revolve"
    assert otra.quitar(MOVIL) and MOVIL not in MisDispositivos(mios.ruta)


def test_alerta_si_tu_bose_esta_en_modo_emparejamiento(mios):
    alertas = revisar_visibles(parsear_escaneo(ESCANEO), mios)
    assert len(alertas) == 1
    assert alertas[0].nivel == "peligro" and "Bose Revolve" in alertas[0].texto


def test_alerta_por_dispositivo_ajeno_en_este_equipo(mios):
    vecino = Dispositivo(VECINO, "Galaxy vecino", emparejado=True, conectado=True)
    alertas = revisar_equipo([Dispositivo(BOSE), vecino], [vecino], mios)
    assert [a.clave for a in alertas] == [f"conectado:{VECINO}"]


def test_vigilante_no_repite_y_vuelve_a_avisar_si_reaparece(mios):
    v = Vigilante(mios)
    visibles = parsear_escaneo(ESCANEO)
    assert len(v.revisar(visibles, [], [])) == 1
    assert v.revisar(visibles, [], []) == []
    assert v.revisar({}, [], []) == []
    assert len(v.revisar(visibles, [], [])) == 1


def test_vigilante_desconocidos_cerca_una_sola_vez(mios):
    v = Vigilante(mios, vigilar_desconocidos=True)
    vecino = {VECINO: Dispositivo(VECINO, "Galaxy vecino", rssi=-55)}
    resultados = [v.revisar(vecino, [], []) for _ in range(5)]
    assert [len(r) for r in resultados] == [0, 0, 1, 0, 0]
    lejos = Vigilante(mios, vigilar_desconocidos=True)
    for _ in range(5):
        assert lejos.revisar({VECINO: Dispositivo(VECINO, rssi=-90)}, [], []) == []


def test_blindar_oculta_y_expulsa_solo_lo_ajeno(mios, monkeypatch, capsys):
    monkeypatch.setenv("GUARDIAN_BT_LISTA", str(mios.ruta))
    falso = FalsoBt({"devices Paired": f"Device {BOSE} Bose Revolve\nDevice {VECINO} Galaxy vecino\n"})
    assert main(["blindar", "--si"], bt=Bluetoothctl(falso)) == 0
    assert ["discoverable", "off"] in falso.ordenes and ["pairable", "off"] in falso.ordenes
    assert ["block", VECINO] in falso.ordenes and ["remove", VECINO] in falso.ordenes
    assert not any(BOSE in o for o in falso.ordenes)
    assert "Expulsados 1" in capsys.readouterr().out


def test_blindar_con_lista_vacia_no_toca_nada(tmp_path, monkeypatch):
    monkeypatch.setenv("GUARDIAN_BT_LISTA", str(tmp_path / "vacia.json"))
    falso = FalsoBt({})
    assert main(["blindar", "--si"], bt=Bluetoothctl(falso)) == 2
    assert falso.ordenes == []


def test_emparejados_en_bluez_antiguo():
    falso = FalsoBt({"devices Paired": "Invalid command", "paired-devices": f"Device {BOSE} Bose"})
    assert [d.mac for d in Bluetoothctl(falso).emparejados()] == [BOSE]


def test_anadir_y_lista_sin_bluetooth(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GUARDIAN_BT_LISTA", str(tmp_path / "l.json"))
    assert main(["añadir", BOSE.lower(), "Bose", "Revolve"]) == 0
    assert main(["lista"]) == 0
    assert f"{BOSE}  Bose Revolve" in capsys.readouterr().out
    assert main(["anadir", "no-es-mac"]) == 2

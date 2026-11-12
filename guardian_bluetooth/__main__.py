"""Guardián Bluetooth:  python -m guardian_bluetooth <orden>

Órdenes: escanear · lista · anadir · quitar · blindar · vigilar
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime

from .bluez import Bluetoothctl, Dispositivo
from .lista import MisDispositivos
from .vigilante import Alerta, Vigilante

log = logging.getLogger("guardian_bluetooth")


def avisar(alerta: Alerta, voz: bool) -> None:
    marca = "🚨" if alerta.nivel == "peligro" else "⚠️"
    print(f"{datetime.now():%H:%M:%S} {marca} {alerta.texto}", flush=True)
    if shutil.which("notify-send"):
        urgencia = "critical" if alerta.nivel == "peligro" else "normal"
        subprocess.run(["notify-send", "-u", urgencia, "Guardián Bluetooth", alerta.texto], check=False)
    if voz:
        for programa in (["spd-say", "-l", "es", "-w"], ["espeak-ng", "-v", "es"], ["espeak", "-v", "es"]):
            if shutil.which(programa[0]):
                subprocess.run([*programa, alerta.texto], check=False)
                break


def conectados(bt: Bluetoothctl, emparejados: list[Dispositivo]) -> list[Dispositivo]:
    return [i for d in emparejados if (i := bt.info(d.mac)) and i.conectado]


def expulsar_ajenos(bt: Bluetoothctl, mios: MisDispositivos, emparejados: list[Dispositivo]) -> list[Dispositivo]:
    ajenos = [d for d in emparejados if d.mac not in mios]
    for d in ajenos:
        bt.expulsar(d.mac)
    return ajenos


def orden_escanear(bt: Bluetoothctl, mios: MisDispositivos, args) -> int:
    print(f"Buscando dispositivos durante {args.segundos} s…")
    visibles = bt.escanear(args.segundos)
    if not visibles:
        print("No se ha visto ningún dispositivo.")
    for d in sorted(visibles.values(), key=lambda d: d.rssi if d.rssi is not None else -999, reverse=True):
        mio = "✔ MÍO " if d.mac in mios else "  ?   "
        modo = " · visible para emparejar" if d.clasico else ""
        rssi = f"{d.rssi} dBm" if d.rssi is not None else "  —   "
        print(f"{mio} {d.mac}  {rssi:>8}  {d.nombre or '(sin nombre)'}{modo}")
    return 0


def orden_lista(bt: Bluetoothctl, mios: MisDispositivos, args) -> int:
    if not mios.dispositivos:
        print("Tu lista está vacía. Añade tus aparatos con:  python -m guardian_bluetooth anadir AA:BB:CC:DD:EE:FF \"Bose Revolve\"")
    for mac, nombre in mios.dispositivos.items():
        print(f"{mac}  {nombre}")
    print(f"(guardada en {mios.ruta})")
    return 0


def orden_anadir(bt: Bluetoothctl, mios: MisDispositivos, args) -> int:
    if args.emparejados:
        for d in bt.emparejados():
            mios.anadir(d.mac, d.nombre)
            print(f"Añadido {d.mac}  {d.nombre}")
        return 0
    if not args.mac:
        print("Indica la dirección (la ves con «escanear») o usa --emparejados.", file=sys.stderr)
        return 2
    mac = mios.anadir(args.mac, " ".join(args.nombre))
    print(f"Añadido {mac}  {mios.nombre(mac)}")
    return 0


def orden_quitar(bt: Bluetoothctl, mios: MisDispositivos, args) -> int:
    print("Quitado." if mios.quitar(args.mac) else "No estaba en la lista.")
    return 0


def orden_blindar(bt: Bluetoothctl, mios: MisDispositivos, args) -> int:
    if not mios.dispositivos:
        print("Primero añade tus dispositivos: si la lista está vacía se expulsaría todo.", file=sys.stderr)
        return 2
    bt.ocultar()
    print("Este equipo ya no es visible ni acepta emparejamientos nuevos.")
    ajenos = [d for d in bt.emparejados() if d.mac not in mios]
    if not ajenos:
        print("No hay dispositivos ajenos emparejados.")
        return 0
    for d in ajenos:
        print(f"  ajeno: {d.mac}  {d.nombre}")
    if not args.si and input("¿Desconectarlos, bloquearlos y olvidarlos? [s/N] ").strip().lower() not in ("s", "si", "sí"):
        print("No se ha tocado nada.")
        return 0
    expulsar_ajenos(bt, mios, ajenos)
    print(f"Expulsados {len(ajenos)} dispositivos.")
    return 0


def orden_vigilar(bt: Bluetoothctl, mios: MisDispositivos, args) -> int:
    if not mios.dispositivos:
        print("Primero añade tus dispositivos con «anadir».", file=sys.stderr)
        return 2
    vigilante = Vigilante(mios, vigilar_desconocidos=args.desconocidos)
    if args.blindar:
        bt.ocultar()
    print(f"Vigilando {len(mios.dispositivos)} dispositivos cada {args.intervalo} s. Ctrl+C para salir.", flush=True)
    try:
        while True:
            visibles = bt.escanear(args.segundos)
            emparejados = bt.emparejados()
            if args.blindar:
                for d in expulsar_ajenos(bt, mios, emparejados):
                    print(f"{datetime.now():%H:%M:%S} 🛡️ Expulsado y bloqueado: {d.nombre or d.mac}", flush=True)
                emparejados = [d for d in emparejados if d.mac in mios]
            for alerta in vigilante.revisar(visibles, emparejados, conectados(bt, emparejados)):
                avisar(alerta, args.voz)
            time.sleep(max(0, args.intervalo - args.segundos))
    except KeyboardInterrupt:
        print("\nVigilancia detenida.")
    return 0


def main(argv: list[str] | None = None, bt: Bluetoothctl | None = None) -> int:
    p = argparse.ArgumentParser(prog="guardian_bluetooth", description="Vigila y blinda tus dispositivos Bluetooth (Linux/BlueZ).")
    sub = p.add_subparsers(dest="orden", required=True)
    s = sub.add_parser("escanear", help="ver qué dispositivos hay cerca")
    s.add_argument("--segundos", type=int, default=12)
    sub.add_parser("lista", help="ver tu lista de dispositivos")
    s = sub.add_parser("anadir", aliases=["añadir"], help="añadir un dispositivo tuyo")
    s.add_argument("mac", nargs="?")
    s.add_argument("nombre", nargs="*")
    s.add_argument("--emparejados", action="store_true", help="añadir todos los emparejados con este equipo")
    s = sub.add_parser("quitar", help="quitar un dispositivo de tu lista")
    s.add_argument("mac")
    s = sub.add_parser("blindar", help="ocultar este equipo y expulsar lo que no sea tuyo")
    s.add_argument("--si", action="store_true", help="no pedir confirmación")
    s = sub.add_parser("vigilar", help="vigilar sin parar y avisar")
    s.add_argument("--intervalo", type=int, default=30, help="segundos entre búsquedas")
    s.add_argument("--segundos", type=int, default=10, help="duración de cada búsqueda")
    s.add_argument("--blindar", action="store_true", help="expulsar automáticamente lo que no sea tuyo de este equipo")
    s.add_argument("--voz", action="store_true", help="leer las alertas en voz alta")
    s.add_argument("--desconocidos", action="store_true", help="avisar también de aparatos desconocidos muy cerca")
    args = p.parse_args(argv)

    sin_bluetooth = args.orden in ("lista", "quitar") or (args.orden in ("anadir", "añadir") and not args.emparejados)
    if bt is None and not sin_bluetooth:
        if not Bluetoothctl.disponible():
            print("No se encuentra «bluetoothctl». Este programa funciona en Linux con BlueZ (también en Raspberry Pi):\n"
                  "  sudo apt install bluez", file=sys.stderr)
            return 1
        bt = Bluetoothctl()
    bt = bt or Bluetoothctl()
    ordenes = {"escanear": orden_escanear, "lista": orden_lista, "anadir": orden_anadir, "añadir": orden_anadir,
               "quitar": orden_quitar, "blindar": orden_blindar, "vigilar": orden_vigilar}
    try:
        return ordenes[args.orden](bt, MisDispositivos(), args)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

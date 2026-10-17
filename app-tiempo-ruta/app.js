// Interfaz, GPS y voz. La lógica de cálculo está en logica.js y las fuentes en fuentes.js.
import {
  distancia,
  rumbo,
  puntoDestino,
  puntoAdelanteEnRuta,
  velocidadNecesaria,
  evaluarAlertas,
  describirTiempo,
  fraseVoz,
  Odometro,
} from "./logica.js";
import {
  obtenerTiempo,
  urlCaudal,
  parsearCaudal,
  urlRuta,
  parsearRuta,
  Cache,
} from "./fuentes.js";

const METROS_ADELANTE = 500;
const PASO_AVISO = 100;
const DESVIO_MAX = 300; // m fuera de la ruta antes de recalcularla
const ORIGEN_SIMULACION = { lat: 43.3623, lon: -8.4115 }; // A Coruña

const AJUSTES_INICIALES = {
  destino: "Madrid",
  lat: 40.4168,
  lon: -3.7038,
  minutos: 90,
  limite: 120,
  voz: "cada100",
  windy: "",
};

const $ = (id) => document.getElementById(id);

// ---------- Ajustes (guardados solo en este navegador) ----------

function cargarAjustes() {
  try {
    return { ...AJUSTES_INICIALES, ...JSON.parse(localStorage.getItem("ajustes") || "{}") };
  } catch {
    return { ...AJUSTES_INICIALES };
  }
}

function guardarAjustes(a) {
  try {
    localStorage.setItem("ajustes", JSON.stringify(a));
  } catch {
    // Sin almacenamiento (modo privado): se usan los valores del formulario.
  }
}

function pintarAjustes(a) {
  $("c-destino").value = a.destino;
  $("c-lat").value = a.lat;
  $("c-lon").value = a.lon;
  $("c-minutos").value = a.minutos;
  $("c-limite").value = a.limite;
  $("c-voz").value = a.voz;
  $("c-windy").value = a.windy;
}

function leerAjustes() {
  const num = (id, def) => {
    const v = parseFloat($(id).value);
    return Number.isFinite(v) ? v : def;
  };
  return {
    destino: $("c-destino").value.trim() || AJUSTES_INICIALES.destino,
    lat: num("c-lat", AJUSTES_INICIALES.lat),
    lon: num("c-lon", AJUSTES_INICIALES.lon),
    minutos: num("c-minutos", AJUSTES_INICIALES.minutos),
    limite: num("c-limite", AJUSTES_INICIALES.limite),
    voz: $("c-voz").value,
    windy: $("c-windy").value.trim(),
  };
}

// ---------- Estado ----------

let ajustes = cargarAjustes();
const cacheTiempo = new Cache(0.01, 10 * 60 * 1000); // ~1 km, 10 min
const cacheCaudal = new Cache(0.05, 60 * 60 * 1000); // ~5 km, 1 h

const estado = {
  activo: false,
  horaLimite: 0,
  pos: null,
  precision: 0,
  velocidadKmh: null,
  rumbo: null,
  posRumbo: null,
  ruta: null,
  pidiendoRuta: false,
  ultimaRuta: 0,
  odometro: new Odometro(PASO_AVISO),
  ocupado: false,
  tiempo: null,
  alertas: [],
  firmaAlertas: "",
  kmAnunciado: -1,
  ultimaFrase: "",
  posMapa: null,
  watchId: null,
  wakeLock: null,
  simulacion: null,
};

// ---------- Voz y alarma ----------

function hablar(texto, urgente = false) {
  if (!texto || ajustes.voz === "apagada" || !("speechSynthesis" in window)) return;
  const s = window.speechSynthesis;
  if (urgente) s.cancel();
  else if (s.speaking || s.pending) return; // no amontonar avisos rutinarios
  const u = new SpeechSynthesisUtterance(texto);
  u.lang = "es-ES";
  const voz = s.getVoices().find((v) => v.lang?.startsWith("es"));
  if (voz) u.voice = voz;
  u.rate = 1.05;
  s.speak(u);
}

let audio = null;
function pitido(veces = 2) {
  try {
    audio ??= new AudioContext();
    for (let i = 0; i < veces; i++) {
      const o = audio.createOscillator();
      const g = audio.createGain();
      o.frequency.value = 880;
      o.connect(g).connect(audio.destination);
      const t = audio.currentTime + i * 0.35;
      g.gain.setValueAtTime(0.4, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + 0.3);
      o.start(t);
      o.stop(t + 0.3);
    }
  } catch {
    // Sin audio: queda la voz y la vibración.
  }
  navigator.vibrate?.([300, 150, 300]);
}

// ---------- Ruta y punto de 500 m ----------

async function actualizarRuta(pos) {
  if (estado.pidiendoRuta) return;
  estado.pidiendoRuta = true;
  estado.ultimaRuta = Date.now();
  try {
    const r = await fetch(urlRuta(pos, ajustes));
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    estado.ruta = parsearRuta(await r.json());
  } catch (e) {
    console.warn("Ruta no disponible:", e);
  } finally {
    estado.pidiendoRuta = false;
  }
}

// Devuelve el punto 500 m por delante y los metros que quedan hasta el destino.
function situar() {
  const pos = estado.pos;
  if (estado.ruta) {
    const r = puntoAdelanteEnRuta(estado.ruta.puntos, pos, METROS_ADELANTE);
    if (r && r.desvio < DESVIO_MAX) {
      return { punto: r.punto, restante: r.restante + r.desvio, enRuta: true };
    }
    // Fuera de la ruta: recalcular (como mucho una vez cada 30 s).
    if (Date.now() - estado.ultimaRuta > 30000) actualizarRuta(pos);
  }
  const destino = { lat: ajustes.lat, lon: ajustes.lon };
  const recta = distancia(pos, destino);
  const punto =
    estado.rumbo == null ? pos : puntoDestino(pos, estado.rumbo, METROS_ADELANTE);
  // Sin ruta, la carretera suele ser ~25 % más larga que la línea recta.
  return { punto, restante: recta * 1.25, enRuta: false };
}

// ---------- Posición ----------

function alPosicion({ lat, lon, precision = 10, rumboGps = null, velocidadMs = null }) {
  const pos = { lat, lon };
  const primera = !estado.pos;
  estado.pos = pos;
  estado.precision = precision;
  estado.velocidadKmh = velocidadMs != null ? velocidadMs * 3.6 : estado.velocidadKmh;

  if (rumboGps != null && !Number.isNaN(rumboGps) && (velocidadMs ?? 0) > 1) {
    estado.rumbo = rumboGps;
  } else if (!estado.posRumbo) {
    estado.posRumbo = pos;
  } else if (distancia(estado.posRumbo, pos) >= 15) {
    estado.rumbo = rumbo(estado.posRumbo, pos);
    estado.posRumbo = pos;
  }

  if (!estado.ruta && !estado.pidiendoRuta && Date.now() - estado.ultimaRuta > 30000) {
    actualizarRuta(pos);
  }

  $("estado-gps").textContent = `GPS ±${Math.round(precision)} m`;
  $("estado-gps").classList.add("vivo");
  pintarVelocidad();

  const tramos = estado.odometro.anadir(pos, precision);
  if (primera || tramos > 0) aviso100m();
}

function errorGps(e) {
  $("estado-gps").textContent = "GPS sin señal";
  $("estado-gps").classList.remove("vivo");
  if (e.code === 1) {
    mostrarAlerta("peligro", "Sin permiso de ubicación", "Permite la ubicación en el navegador para usar la app.");
    hablar("Necesito permiso de ubicación.", true);
  }
}

// ---------- Aviso cada 100 m ----------

async function aviso100m() {
  if (estado.ocupado || !estado.activo) return;
  estado.ocupado = true;
  try {
    const { punto } = situar();
    let tiempo;
    try {
      tiempo = await cacheTiempo.obtener(punto, (p) =>
        obtenerTiempo(p, { claveWindy: ajustes.windy }),
      );
      tiempo.caudalRatio = await cacheCaudal
        .obtener(punto, async (p) => {
          const r = await fetch(urlCaudal(p));
          return r.ok ? parsearCaudal(await r.json()) : null;
        })
        .catch(() => null);
    } catch (e) {
      $("t-fuente").textContent = `Error al pedir el tiempo: ${e.message}`;
      hablar("Sin datos del tiempo. Revisa la cobertura.");
      return;
    }

    estado.tiempo = tiempo;
    estado.alertas = evaluarAlertas(tiempo);
    pintarTiempo(tiempo, estado.alertas);
    moverMapa(punto);
    anunciar();
  } finally {
    estado.ocupado = false;
  }
}

function anunciar() {
  const { alertas, tiempo } = estado;
  const firma = alertas.map((a) => a.tipo + a.nivel).join(",");
  const nuevas = firma !== estado.firmaAlertas;
  const empeora =
    nuevas && alertas.some((a) => !estado.firmaAlertas.includes(a.tipo + a.nivel));
  estado.firmaAlertas = firma;

  const km = Math.floor(estado.odometro.total / 1000);
  const completa = km !== estado.kmAnunciado;
  if (completa) estado.kmAnunciado = km;

  const frase = fraseVoz({
    tiempo,
    alertas,
    velocidad: calcularVelocidad(),
    destino: ajustes.destino,
    completa: completa || nuevas,
  });
  estado.ultimaFrase = frase;

  if (empeora) {
    pitido(alertas[0].nivel === "peligro" ? 3 : 2);
    hablar(frase, true);
  } else if (ajustes.voz === "cada100" || nuevas || completa) {
    hablar(frase, nuevas);
  }
}

// ---------- Pintar ----------

function mostrarAlerta(nivel, titulo, detalle) {
  $("alerta").className = `alerta ${nivel}`;
  $("alerta-titulo").textContent = titulo;
  $("alerta-detalle").textContent = detalle;
}

function pintarTiempo(t, alertas) {
  const f = (v, dec = 0) => (v == null ? "–" : v.toFixed(dec));
  $("t-lluvia").textContent = f(t.precipMmH, 1);
  $("t-visibilidad").textContent =
    t.visibilidadM == null
      ? "–"
      : t.visibilidadM >= 10000
        ? ">10 km"
        : t.visibilidadM >= 1000
          ? `${(t.visibilidadM / 1000).toFixed(1)} km`
          : `${Math.round(t.visibilidadM)} m`;
  $("t-rachas").textContent = f(t.rachasKmH);
  $("t-temp").textContent = t.temperatura == null ? "–" : `${t.temperatura.toFixed(0)} °C`;

  for (const tipo of ["desbordamiento", "derrumbe"]) {
    const a = alertas.find((x) => x.tipo === tipo);
    const el = $(`r-${tipo}`);
    el.textContent = a ? (a.nivel === "peligro" ? "PELIGRO" : "Riesgo") : "Bajo";
    el.className = `dato peq ${a ? a.nivel : ""}`;
  }

  const acumulada =
    t.lluvia24h == null ? "" : ` · lluvia 24 h: ${t.lluvia24h.toFixed(0)} mm`;
  const caudal = t.caudalRatio == null ? "" : ` · río: ×${t.caudalRatio.toFixed(1)} del caudal normal`;
  const hora = new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
  $("t-fuente").textContent =
    `Fuente: ${t.fuente}${acumulada}${caudal} · ${hora}` +
    (t.errorWindy ? ` · Windy falló: ${t.errorWindy}` : "");

  if (alertas.length) {
    mostrarAlerta(
      alertas[0].nivel,
      alertas[0].texto,
      alertas.slice(1).map((a) => a.texto).join(" · ") || "A 500 m por delante",
    );
  } else {
    mostrarAlerta("ok", `Sin alertas · ${describirTiempo(t)}`, "A 500 m por delante");
  }
}

function calcularVelocidad() {
  if (!estado.pos) return null;
  const { restante } = situar();
  return { ...velocidadNecesaria(restante, estado.horaLimite - Date.now(), ajustes.limite), restante };
}

function pintarVelocidad() {
  const v = calcularVelocidad();
  if (!v) return;
  const { enRuta } = situar();
  const msRestantes = estado.horaLimite - Date.now();
  $("d-titulo").textContent = `Hacia ${ajustes.destino}`;
  $("d-restante").textContent = `${enRuta ? "" : "≈"}${(v.restante / 1000).toFixed(1)}`;
  $("d-tiempo").textContent = msRestantes > 0 ? formatoDuracion(msRestantes) : "pasado";
  $("d-actual").textContent =
    estado.velocidadKmh == null ? "–" : `${Math.round(estado.velocidadKmh)}`;

  const necesaria = $("d-necesaria");
  if (Number.isFinite(v.kmh) && v.posible) {
    necesaria.textContent = Math.round(v.kmh);
    necesaria.className = "dato grande";
    $("d-nota").textContent = enRuta
      ? "Distancia por carretera (OSRM). Respeta siempre los límites de cada tramo."
      : "Distancia aproximada: calculando la ruta por carretera…";
  } else {
    necesaria.textContent = "No da";
    necesaria.className = "dato grande peligro";
    const llegada = new Date(Date.now() + v.llegadaALimiteMs);
    $("d-nota").textContent =
      `No se llega a tiempo sin pasar de ${ajustes.limite} km/h. ` +
      `Yendo a ${ajustes.limite} llegarías hacia las ` +
      llegada.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) +
      " (sin contar paradas).";
  }
}

function formatoDuracion(ms) {
  const min = Math.round(ms / 60000);
  return min >= 60 ? `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")}` : `${min} min`;
}

// El mapa de Windy se recarga cada 5 km para que no parpadee constantemente.
function moverMapa(punto) {
  if (estado.posMapa && distancia(estado.posMapa, punto) < 5000) return;
  estado.posMapa = punto;
  const q = new URLSearchParams({
    type: "map",
    location: "coordinates",
    metricRain: "mm",
    metricTemp: "°C",
    metricWind: "km/h",
    zoom: "10",
    overlay: "rain",
    product: "ecmwf",
    level: "surface",
    lat: punto.lat.toFixed(3),
    lon: punto.lon.toFixed(3),
    detailLat: punto.lat.toFixed(3),
    detailLon: punto.lon.toFixed(3),
    marker: "true",
  });
  $("windy").src = `https://embed.windy.com/embed.html?${q}`;
}

// ---------- Empezar / parar ----------

async function empezar(simular = false) {
  ajustes = leerAjustes();
  guardarAjustes(ajustes);
  Object.assign(estado, {
    activo: true,
    horaLimite: Date.now() + ajustes.minutos * 60000,
    pos: null,
    rumbo: null,
    posRumbo: null,
    ruta: null,
    ultimaRuta: 0,
    odometro: new Odometro(PASO_AVISO),
    firmaAlertas: "",
    kmAnunciado: -1,
    posMapa: null,
  });

  $("boton-empezar").textContent = "Parar";
  $("boton-empezar").classList.add("parar");
  $("boton-repetir").disabled = false;
  $("ajustes").open = false;
  mostrarAlerta("ok", "Buscando GPS…", "En cuanto haya posición se pide el tiempo a 500 m.");
  // La primera locución debe salir de un toque del usuario (requisito de iOS/Android).
  hablar(`Empezamos. Te aviso cada ${PASO_AVISO} metros del tiempo a 500 metros por delante.`, true);

  try {
    estado.wakeLock = await navigator.wakeLock?.request("screen");
  } catch {
    // Sin bloqueo de pantalla: el usuario debe dejarla encendida.
  }

  if (simular) {
    iniciarSimulacion();
  } else if ("geolocation" in navigator) {
    estado.watchId = navigator.geolocation.watchPosition(
      (p) =>
        alPosicion({
          lat: p.coords.latitude,
          lon: p.coords.longitude,
          precision: p.coords.accuracy,
          rumboGps: p.coords.heading,
          velocidadMs: p.coords.speed,
        }),
      errorGps,
      { enableHighAccuracy: true, maximumAge: 1000, timeout: 20000 },
    );
  } else {
    errorGps({ code: 0 });
  }
}

function parar() {
  estado.activo = false;
  if (estado.watchId != null) navigator.geolocation.clearWatch(estado.watchId);
  estado.watchId = null;
  clearInterval(estado.simulacion);
  estado.simulacion = null;
  estado.wakeLock?.release?.();
  estado.wakeLock = null;
  window.speechSynthesis?.cancel();
  $("boton-empezar").textContent = "Empezar";
  $("boton-empezar").classList.remove("parar");
  $("boton-repetir").disabled = true;
  $("estado-gps").textContent = "GPS apagado";
  $("estado-gps").classList.remove("vivo");
  mostrarAlerta("ok", "Parado", "Pulsa «Empezar» para volver a recibir avisos.");
}

// Recorre la ruta desde A Coruña a 110 km/h (un punto por segundo) para probar en casa.
async function iniciarSimulacion() {
  let puntos;
  try {
    const r = await fetch(urlRuta(ORIGEN_SIMULACION, ajustes));
    puntos = parsearRuta(await r.json()).puntos;
  } catch {
    puntos = [ORIGEN_SIMULACION, { lat: ajustes.lat, lon: ajustes.lon }];
  }
  const ms = 110 / 3.6;
  let recorrido = 0;
  let anterior = null;
  const paso = () => {
    const p = recorrido === 0 ? puntos[0] : puntoAdelanteEnRuta(puntos, puntos[0], recorrido).punto;
    alPosicion({
      ...p,
      precision: 5,
      rumboGps: anterior ? rumbo(anterior, p) : null,
      velocidadMs: ms,
    });
    anterior = p;
    recorrido += ms;
  };
  paso();
  estado.simulacion = setInterval(paso, 1000);
}

// ---------- Arranque ----------

pintarAjustes(ajustes);
$("d-titulo").textContent = `Hacia ${ajustes.destino}`;
$("boton-empezar").addEventListener("click", () => (estado.activo ? parar() : empezar()));
$("boton-simular").addEventListener("click", () => {
  if (estado.activo) parar();
  empezar(true);
});
$("boton-repetir").addEventListener("click", () => hablar(estado.ultimaFrase, true));
document.addEventListener("visibilitychange", async () => {
  // El bloqueo de pantalla se pierde al cambiar de app: se recupera al volver.
  if (document.visibilityState === "visible" && estado.activo && (!estado.wakeLock || estado.wakeLock.released)) {
    try {
      estado.wakeLock = await navigator.wakeLock?.request("screen");
    } catch {
      // ignorar
    }
  }
});
setInterval(() => estado.activo && estado.pos && pintarVelocidad(), 5000);

if ("serviceWorker" in navigator && location.protocol === "https:") {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

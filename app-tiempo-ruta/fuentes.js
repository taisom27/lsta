// Fuentes de datos: Windy (tiempo), Open-Meteo (visibilidad, lluvia acumulada y
// caudal de ríos) y OSRM (ruta por carretera). Las funciones `parsear*` son puras.

const ahoraS = () => Date.now() / 1000;

function indiceMasCercano(tiempos, objetivo) {
  let mejor = 0;
  for (let i = 1; i < tiempos.length; i++) {
    if (Math.abs(tiempos[i] - objetivo) < Math.abs(tiempos[mejor] - objetivo)) mejor = i;
  }
  return mejor;
}

// ---------- Windy (Point Forecast API v2) ----------

export const URL_WINDY = "https://api.windy.com/api/point-forecast/v2";

export function peticionWindy(punto, clave, modelo = "iconEu") {
  return {
    lat: Number(punto.lat.toFixed(3)),
    lon: Number(punto.lon.toFixed(3)),
    model: modelo,
    parameters: ["precip", "wind", "windGust", "ptype", "temp"],
    levels: ["surface"],
    key: clave,
  };
}

// Windy da la lluvia acumulada en las 3 h previas (en metros) y el viento en m/s.
export function parsearWindy(json, ahora = ahoraS()) {
  const ts = (json.ts ?? []).map((t) => t / 1000);
  if (!ts.length) throw new Error("Windy no devolvió datos");
  const i = indiceMasCercano(ts, ahora);
  const valor = (clave) => json[clave]?.[i] ?? null;
  const p3h = valor("past3hprecip-surface");
  const u = valor("wind_u-surface");
  const v = valor("wind_v-surface");
  const racha = valor("gust-surface");
  const temp = valor("temp-surface");
  return {
    precipMmH: p3h == null ? null : (p3h * 1000) / 3,
    vientoKmH: u == null || v == null ? null : Math.hypot(u, v) * 3.6,
    rachasKmH: racha == null ? null : racha * 3.6,
    temperatura: temp == null ? null : temp - 273.15,
  };
}

// ---------- Open-Meteo (tiempo actual, visibilidad y lluvia acumulada) ----------

export function urlOpenMeteo(punto) {
  const q = new URLSearchParams({
    latitude: punto.lat.toFixed(3),
    longitude: punto.lon.toFixed(3),
    current: "temperature_2m,weather_code,visibility,wind_speed_10m,wind_gusts_10m",
    minutely_15: "precipitation",
    past_minutely_15: "2",
    forecast_minutely_15: "2",
    hourly: "precipitation",
    past_hours: "72",
    forecast_hours: "1",
    timeformat: "unixtime",
    timezone: "GMT",
  });
  return `https://api.open-meteo.com/v1/forecast?${q}`;
}

export function parsearOpenMeteo(json, ahora = ahoraS()) {
  const c = json.current ?? {};
  let precipMmH = null;
  const m15 = json.minutely_15;
  if (m15?.time?.length) {
    // Cada valor es la lluvia de los 15 min anteriores: x4 para pasar a mm/h.
    const i = indiceMasCercano(m15.time, ahora);
    if (m15.precipitation[i] != null) precipMmH = m15.precipitation[i] * 4;
  }
  let lluvia24h = null;
  let lluvia72h = null;
  const h = json.hourly;
  if (h?.time?.length) {
    const pasadas = h.time
      .map((t, i) => [t, h.precipitation[i] ?? 0])
      .filter(([t]) => t <= ahora);
    lluvia72h = pasadas.reduce((s, [, p]) => s + p, 0);
    lluvia24h = pasadas.slice(-24).reduce((s, [, p]) => s + p, 0);
  }
  return {
    precipMmH,
    visibilidadM: c.visibility ?? null,
    vientoKmH: c.wind_speed_10m ?? null,
    rachasKmH: c.wind_gusts_10m ?? null,
    temperatura: c.temperature_2m ?? null,
    codigo: c.weather_code ?? null,
    lluvia24h,
    lluvia72h,
  };
}

// ---------- Open-Meteo Flood (caudal de ríos, GloFAS) ----------

export function urlCaudal(punto) {
  const q = new URLSearchParams({
    latitude: punto.lat.toFixed(2),
    longitude: punto.lon.toFixed(2),
    daily: "river_discharge",
    past_days: "30",
    forecast_days: "2",
    timeformat: "unixtime",
  });
  return `https://flood-api.open-meteo.com/v1/flood?${q}`;
}

// Relación entre el caudal de hoy/mañana y la mediana de los últimos 30 días.
export function parsearCaudal(json, ahora = ahoraS()) {
  const d = json.daily;
  if (!d?.time?.length) return null;
  const pasados = [];
  const proximos = [];
  d.time.forEach((t, i) => {
    const q = d.river_discharge[i];
    if (q == null) return;
    (t < ahora - 86400 ? pasados : proximos).push(q);
  });
  if (pasados.length < 5 || !proximos.length) return null;
  pasados.sort((a, b) => a - b);
  const mediana = pasados[Math.floor(pasados.length / 2)];
  // En cauces muy pequeños la relación no es fiable.
  if (mediana < 1) return null;
  return Math.max(...proximos) / mediana;
}

// ---------- OSRM (ruta por carretera) ----------

export function urlRuta(origen, destino) {
  return (
    "https://router.project-osrm.org/route/v1/driving/" +
    `${origen.lon},${origen.lat};${destino.lon},${destino.lat}` +
    "?overview=full&geometries=geojson"
  );
}

export function parsearRuta(json) {
  const r = json.routes?.[0];
  if (json.code !== "Ok" || !r) throw new Error("No se encontró ruta");
  return {
    metros: r.distance,
    segundos: r.duration,
    puntos: r.geometry.coordinates.map(([lon, lat]) => ({ lat, lon })),
  };
}

// ---------- Llamadas con caché ----------

async function pedirJson(fetchFn, url, opciones) {
  const r = await fetchFn(url, opciones);
  if (!r.ok) throw new Error(`HTTP ${r.status} en ${new URL(url).host}`);
  return r.json();
}

// Junta Windy (si hay clave) y Open-Meteo. Windy manda en lluvia y viento;
// Open-Meteo aporta la visibilidad y la lluvia acumulada que Windy no da.
export async function obtenerTiempo(punto, { claveWindy, fetchFn = fetch } = {}) {
  const [windy, om] = await Promise.allSettled([
    claveWindy
      ? pedirJson(fetchFn, URL_WINDY, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(peticionWindy(punto, claveWindy)),
        }).then((j) => parsearWindy(j))
      : Promise.reject(new Error("sin clave de Windy")),
    pedirJson(fetchFn, urlOpenMeteo(punto)).then((j) => parsearOpenMeteo(j)),
  ]);
  if (windy.status === "rejected" && om.status === "rejected") {
    throw new Error(`Sin datos del tiempo (${om.reason.message})`);
  }
  const w = windy.status === "fulfilled" ? windy.value : {};
  const o = om.status === "fulfilled" ? om.value : {};
  const elegir = (a, b) => (a != null ? a : b ?? null);
  return {
    precipMmH: maximo(w.precipMmH, o.precipMmH),
    visibilidadM: o.visibilidadM ?? null,
    vientoKmH: elegir(w.vientoKmH, o.vientoKmH),
    rachasKmH: maximo(w.rachasKmH, o.rachasKmH),
    temperatura: elegir(o.temperatura, w.temperatura),
    codigo: o.codigo ?? null,
    lluvia24h: o.lluvia24h ?? null,
    lluvia72h: o.lluvia72h ?? null,
    fuente: [windy.status === "fulfilled" && "Windy", om.status === "fulfilled" && "Open-Meteo"]
      .filter(Boolean)
      .join(" + "),
    errorWindy: claveWindy && windy.status === "rejected" ? windy.reason.message : null,
  };
}

// Por seguridad se queda con el valor más desfavorable de las dos fuentes.
function maximo(a, b) {
  if (a == null) return b ?? null;
  if (b == null) return a;
  return Math.max(a, b);
}

// Caché simple por celda de rejilla: los modelos tienen resolución de kilómetros,
// así que no tiene sentido pedir el tiempo de nuevo cada 100 m.
export class Cache {
  constructor(celdaGrados, ttlMs) {
    this.celda = celdaGrados;
    this.ttl = ttlMs;
    this.datos = new Map();
  }

  clave(p) {
    return `${Math.round(p.lat / this.celda)}:${Math.round(p.lon / this.celda)}`;
  }

  async obtener(p, cargar, ahora = Date.now()) {
    const k = this.clave(p);
    const e = this.datos.get(k);
    if (e && ahora - e.t < this.ttl) return e.v;
    const v = await cargar(p);
    this.datos.set(k, { t: ahora, v });
    return v;
  }
}

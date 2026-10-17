import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parsearWindy,
  parsearOpenMeteo,
  parsearCaudal,
  parsearRuta,
  peticionWindy,
  obtenerTiempo,
  Cache,
  URL_WINDY,
} from "../fuentes.js";

const AHORA = 1_790_000_000; // segundos
const P = { lat: 42.5, lon: -6.6 };

const WINDY = {
  ts: [(AHORA - 10800) * 1000, AHORA * 1000, (AHORA + 10800) * 1000],
  units: { "past3hprecip-surface": "m" },
  "past3hprecip-surface": [0, 0.06, 0],
  "wind_u-surface": [0, 3, 0],
  "wind_v-surface": [0, 4, 0],
  "gust-surface": [0, 25, 0],
  "temp-surface": [280, 285.15, 280],
};

const OPEN_METEO = {
  current: { temperature_2m: 11.2, weather_code: 63, visibility: 450, wind_speed_10m: 15, wind_gusts_10m: 40 },
  minutely_15: { time: [AHORA - 900, AHORA, AHORA + 900], precipitation: [1, 2.5, 3] },
  hourly: {
    time: Array.from({ length: 74 }, (_, i) => AHORA - 72 * 3600 + i * 3600),
    precipitation: Array.from({ length: 74 }, (_, i) => (i >= 48 ? 2 : 1)),
  },
};

test("parsearWindy convierte metros/3 h a mm/h y m/s a km/h", () => {
  const w = parsearWindy(WINDY, AHORA);
  assert.equal(Math.round(w.precipMmH), 20);
  assert.equal(Math.round(w.vientoKmH), 18);
  assert.equal(Math.round(w.rachasKmH), 90);
  assert.equal(Math.round(w.temperatura), 12);
});

test("peticionWindy pide los parámetros de superficie con la clave", () => {
  const p = peticionWindy(P, "CLAVE");
  assert.equal(p.key, "CLAVE");
  assert.ok(p.parameters.includes("precip"));
  assert.deepEqual(p.levels, ["surface"]);
});

test("parsearOpenMeteo calcula intensidad y lluvia acumulada", () => {
  const o = parsearOpenMeteo(OPEN_METEO, AHORA);
  assert.equal(o.precipMmH, 10);
  assert.equal(o.visibilidadM, 450);
  assert.equal(o.codigo, 63);
  // Solo cuenta horas pasadas: 48 h a 1 mm + 25 h a 2 mm (la última es futura).
  assert.equal(o.lluvia72h, 48 + 25 * 2);
  assert.equal(o.lluvia24h, 24 * 2);
});

test("parsearCaudal compara con la mediana de los últimos días", () => {
  const dias = Array.from({ length: 32 }, (_, i) => AHORA - (30 - i) * 86400);
  const caudal = dias.map((_, i) => (i < 30 ? 10 : 45));
  assert.equal(parsearCaudal({ daily: { time: dias, river_discharge: caudal } }, AHORA), 4.5);
  // Cauce diminuto: no fiable.
  const pequeno = dias.map(() => 0.2);
  assert.equal(parsearCaudal({ daily: { time: dias, river_discharge: pequeno } }, AHORA), null);
});

test("parsearRuta pasa de [lon, lat] a {lat, lon}", () => {
  const r = parsearRuta({
    code: "Ok",
    routes: [{ distance: 590000, duration: 20000, geometry: { coordinates: [[-8.4, 43.3], [-3.7, 40.4]] } }],
  });
  assert.equal(r.metros, 590000);
  assert.deepEqual(r.puntos[1], { lat: 40.4, lon: -3.7 });
  assert.throws(() => parsearRuta({ code: "NoRoute", routes: [] }));
});

function falsoFetch(respuestas) {
  return async (url) => {
    const host = new URL(url).host;
    const r = respuestas[host];
    if (r instanceof Error) throw r;
    return { ok: true, status: 200, json: async () => r };
  };
}

test("obtenerTiempo junta Windy y Open-Meteo con el valor más desfavorable", async () => {
  const fetchFn = falsoFetch({ "api.windy.com": WINDY, "api.open-meteo.com": OPEN_METEO });
  const realNow = Date.now;
  Date.now = () => AHORA * 1000;
  try {
    const t = await obtenerTiempo(P, { claveWindy: "X", fetchFn });
    assert.equal(t.fuente, "Windy + Open-Meteo");
    assert.equal(Math.round(t.precipMmH), 20); // Windy 20 > Open-Meteo 10
    assert.equal(t.visibilidadM, 450); // solo Open-Meteo
    assert.equal(Math.round(t.rachasKmH), 90);
  } finally {
    Date.now = realNow;
  }
});

test("obtenerTiempo sin clave de Windy usa solo Open-Meteo", async () => {
  const llamadas = [];
  const base = falsoFetch({ "api.open-meteo.com": OPEN_METEO });
  const fetchFn = (url, o) => (llamadas.push(url), base(url, o));
  const t = await obtenerTiempo(P, { fetchFn });
  assert.equal(t.fuente, "Open-Meteo");
  assert.ok(!llamadas.includes(URL_WINDY));
  assert.equal(t.errorWindy, null);
});

test("obtenerTiempo sigue funcionando si Windy falla y avisa del error", async () => {
  const fetchFn = falsoFetch({ "api.windy.com": new Error("403"), "api.open-meteo.com": OPEN_METEO });
  const t = await obtenerTiempo(P, { claveWindy: "X", fetchFn });
  assert.equal(t.fuente, "Open-Meteo");
  assert.match(t.errorWindy, /403/);
});

test("obtenerTiempo falla si no responde ninguna fuente", async () => {
  const fetchFn = falsoFetch({ "api.open-meteo.com": new Error("sin red") });
  await assert.rejects(obtenerTiempo(P, { fetchFn }), /Sin datos del tiempo/);
});

test("Cache reutiliza la celda dentro del plazo y caduca después", async () => {
  const c = new Cache(0.01, 1000);
  let cargas = 0;
  const cargar = async () => ++cargas;
  await c.obtener({ lat: 42.5001, lon: -6.6 }, cargar, 0);
  await c.obtener({ lat: 42.5003, lon: -6.6002 }, cargar, 500);
  assert.equal(cargas, 1);
  await c.obtener({ lat: 42.5003, lon: -6.6002 }, cargar, 1500);
  assert.equal(cargas, 2);
});

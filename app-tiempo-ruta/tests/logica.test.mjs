import { test } from "node:test";
import assert from "node:assert/strict";
import {
  distancia,
  rumbo,
  puntoDestino,
  puntoAdelanteEnRuta,
  velocidadNecesaria,
  evaluarAlertas,
  fraseVoz,
  Odometro,
} from "../logica.js";

const CORUNA = { lat: 43.3623, lon: -8.4115 };
const MADRID = { lat: 40.4168, lon: -3.7038 };

test("distancia entre A Coruña y Madrid en línea recta (~510 km)", () => {
  const km = distancia(CORUNA, MADRID) / 1000;
  assert.ok(km > 500 && km < 520, `${km}`);
});

test("puntoDestino avanza los metros pedidos en el rumbo pedido", () => {
  const p = puntoDestino(CORUNA, 90, 500);
  assert.ok(Math.abs(distancia(CORUNA, p) - 500) < 0.5);
  assert.ok(Math.abs(rumbo(CORUNA, p) - 90) < 0.1);
});

test("puntoAdelanteEnRuta sigue la ruta aunque gire", () => {
  // Ruta en L: 400 m al norte y luego al este.
  const a = CORUNA;
  const b = puntoDestino(a, 0, 400);
  const c = puntoDestino(b, 90, 1000);
  const r = puntoAdelanteEnRuta([a, b, c], a, 500);
  // Debe estar 100 m al este de la esquina, no 500 m al norte.
  assert.ok(Math.abs(distancia(b, r.punto) - 100) < 2, `${distancia(b, r.punto)}`);
  assert.ok(Math.abs(r.restante - 1400) < 2);
  assert.ok(r.desvio < 1);
});

test("puntoAdelanteEnRuta mide el desvío y no pasa del final", () => {
  const a = CORUNA;
  const b = puntoDestino(a, 0, 300);
  const fuera = puntoDestino(a, 90, 200);
  const r = puntoAdelanteEnRuta([a, b], fuera, 500);
  assert.ok(Math.abs(r.desvio - 200) < 2);
  assert.ok(distancia(r.punto, b) < 1);
});

test("velocidadNecesaria: posible dentro del límite", () => {
  const v = velocidadNecesaria(150000, 90 * 60000, 120);
  assert.equal(Math.round(v.kmh), 100);
  assert.equal(v.posible, true);
});

test("velocidadNecesaria: A Coruña-Madrid en 1 h 30 no es posible a 120", () => {
  const v = velocidadNecesaria(590000, 90 * 60000, 120);
  assert.equal(v.posible, false);
  assert.ok(v.kmh > 390);
  // A 120 km/h se tarda casi 5 h.
  assert.ok(Math.abs(v.llegadaALimiteMs / 3600000 - 590 / 120) < 0.01);
});

test("velocidadNecesaria: tiempo agotado", () => {
  const v = velocidadNecesaria(1000, -5, 120);
  assert.equal(v.posible, false);
  assert.equal(v.kmh, Infinity);
});

test("sin alertas con buen tiempo", () => {
  assert.deepEqual(
    evaluarAlertas({ precipMmH: 0.5, visibilidadM: 20000, rachasKmH: 20, lluvia24h: 3, codigo: 61 }),
    [],
  );
});

test("lluvia intensa y muy intensa", () => {
  assert.equal(evaluarAlertas({ precipMmH: 18 })[0].nivel, "aviso");
  const a = evaluarAlertas({ precipMmH: 35 });
  assert.equal(a[0].tipo, "lluvia");
  assert.equal(a[0].nivel, "peligro");
  assert.equal(evaluarAlertas({ precipMmH: 3, codigo: 82 })[0].tipo, "lluvia");
});

test("visibilidad baja y niebla", () => {
  assert.equal(evaluarAlertas({ visibilidadM: 600 })[0].nivel, "aviso");
  const a = evaluarAlertas({ visibilidadM: 120 })[0];
  assert.equal(a.nivel, "peligro");
  assert.match(a.texto, /120 metros/);
  assert.equal(evaluarAlertas({ codigo: 45 })[0].tipo, "visibilidad");
});

test("desbordamiento por caudal del río o lluvia acumulada", () => {
  assert.equal(evaluarAlertas({ caudalRatio: 2.5 })[0].tipo, "desbordamiento");
  assert.equal(evaluarAlertas({ caudalRatio: 5 })[0].nivel, "peligro");
  assert.equal(evaluarAlertas({ lluvia24h: 85 }).find((a) => a.tipo === "desbordamiento").nivel, "peligro");
});

test("derrumbes por lluvia acumulada", () => {
  assert.equal(evaluarAlertas({ lluvia72h: 110 }).find((a) => a.tipo === "derrumbe").nivel, "aviso");
  const a = evaluarAlertas({ lluvia24h: 65, precipMmH: 20 });
  assert.equal(a.find((x) => x.tipo === "derrumbe").nivel, "peligro");
});

test("las alertas de peligro van primero", () => {
  const a = evaluarAlertas({ visibilidadM: 800, precipMmH: 40 });
  assert.equal(a[0].nivel, "peligro");
  assert.equal(a[1].nivel, "aviso");
});

test("frase de voz con alertas y velocidad", () => {
  const f = fraseVoz({
    tiempo: { precipMmH: 40 },
    alertas: evaluarAlertas({ precipMmH: 40 }),
    velocidad: { kmh: 98.4, posible: true },
    destino: "Madrid",
    completa: true,
  });
  assert.match(f, /^Atención\. Lluvia muy intensa/);
  assert.match(f, /llegar a Madrid a tiempo, media de 98 kilómetros por hora/);
});

test("frase de voz cuando no se llega respetando el límite", () => {
  const f = fraseVoz({
    tiempo: { precipMmH: 0 },
    alertas: [],
    velocidad: { kmh: 400, posible: false },
    destino: "Madrid",
    completa: true,
  });
  assert.match(f, /A 500 metros, sin lluvia\./);
  assert.match(f, /No se llega a Madrid a tiempo respetando el límite/);
  assert.doesNotMatch(f, /400/);
});

test("odómetro: un aviso cada 100 m e ignora el ruido del GPS", () => {
  const o = new Odometro(100);
  let p = CORUNA;
  assert.equal(o.anadir(p), 0);
  // Temblor del GPS parado: no suma.
  assert.equal(o.anadir(puntoDestino(p, 45, 3)), 0);
  // Posición muy imprecisa: se ignora.
  assert.equal(o.anadir(puntoDestino(p, 0, 500), 200), 0);
  let avisos = 0;
  for (let i = 0; i < 10; i++) {
    p = puntoDestino(p, 0, 33);
    avisos += o.anadir(p);
  }
  assert.equal(avisos, 3); // 330 m
  // Un salto largo cuenta varios tramos.
  assert.equal(o.anadir(puntoDestino(p, 0, 250)), 2);
});

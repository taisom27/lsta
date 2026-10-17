// Lógica pura de la app (sin red ni navegador): geometría, velocidad y alertas.
// Se importa desde app.js y desde los tests de Node.

const RADIO_TIERRA = 6371000;
const rad = (g) => (g * Math.PI) / 180;
const grad = (r) => (r * 180) / Math.PI;

// Distancia en metros entre dos puntos {lat, lon} (fórmula del haversine).
export function distancia(a, b) {
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * RADIO_TIERRA * Math.asin(Math.min(1, Math.sqrt(h)));
}

// Rumbo inicial en grados (0 = norte, 90 = este) para ir de a hacia b.
export function rumbo(a, b) {
  const y = Math.sin(rad(b.lon - a.lon)) * Math.cos(rad(b.lat));
  const x =
    Math.cos(rad(a.lat)) * Math.sin(rad(b.lat)) -
    Math.sin(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.cos(rad(b.lon - a.lon));
  return (grad(Math.atan2(y, x)) + 360) % 360;
}

// Punto situado a `metros` de p siguiendo el rumbo dado.
export function puntoDestino(p, rumboGrados, metros) {
  const d = metros / RADIO_TIERRA;
  const r = rad(rumboGrados);
  const lat1 = rad(p.lat);
  const lon1 = rad(p.lon);
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(r),
  );
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(r) * Math.sin(d) * Math.cos(lat1),
      Math.cos(d) - Math.sin(lat1) * Math.sin(lat2),
    );
  return { lat: grad(lat2), lon: ((grad(lon2) + 540) % 360) - 180 };
}

function interpolar(a, b, t) {
  return { lat: a.lat + (b.lat - a.lat) * t, lon: a.lon + (b.lon - a.lon) * t };
}

// Proyección de p sobre el segmento a-b (aproximación plana, válida a escala de tramo).
function proyectar(p, a, b) {
  const kx = Math.cos(rad(p.lat));
  const ax = a.lon * kx, ay = a.lat;
  const bx = b.lon * kx, by = b.lat;
  const px = p.lon * kx, py = p.lat;
  const dx = bx - ax, dy = by - ay;
  const l2 = dx * dx + dy * dy;
  const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2));
  return { t, punto: interpolar(a, b, t) };
}

// Sitúa `pos` sobre la ruta (lista de {lat, lon}) y devuelve:
// - punto: el punto `metros` más adelante siguiendo la ruta
// - desvio: metros entre pos y la ruta
// - restante: metros de ruta que quedan desde pos hasta el final
export function puntoAdelanteEnRuta(ruta, pos, metros) {
  if (!ruta || ruta.length < 2) return null;
  let mejor = { desvio: Infinity, i: 0, t: 0, punto: ruta[0] };
  for (let i = 0; i < ruta.length - 1; i++) {
    const { t, punto } = proyectar(pos, ruta[i], ruta[i + 1]);
    const d = distancia(pos, punto);
    if (d < mejor.desvio) mejor = { desvio: d, i, t, punto };
  }

  // Recorre la ruta desde la proyección hasta completar `metros`.
  let falta = metros;
  let actual = mejor.punto;
  let punto = null;
  let restante = 0;
  for (let i = mejor.i; i < ruta.length - 1; i++) {
    const siguiente = ruta[i + 1];
    const tramo = distancia(actual, siguiente);
    if (punto === null && tramo >= falta) {
      punto = interpolar(actual, siguiente, tramo === 0 ? 0 : falta / tramo);
    } else if (punto === null) {
      falta -= tramo;
    }
    restante += tramo;
    actual = siguiente;
  }
  return { punto: punto ?? ruta[ruta.length - 1], desvio: mejor.desvio, restante };
}

// Velocidad media necesaria para recorrer `metrosRestantes` en `msRestantes`.
// Nunca anima a pasarse del límite: si hace falta más, lo indica como imposible.
export function velocidadNecesaria(metrosRestantes, msRestantes, limiteKmh = 120) {
  const horasALimite = metrosRestantes / 1000 / limiteKmh;
  const llegadaALimiteMs = horasALimite * 3600 * 1000;
  if (msRestantes <= 0) {
    return { kmh: Infinity, posible: false, llegadaALimiteMs };
  }
  const kmh = metrosRestantes / 1000 / (msRestantes / 3600000);
  return { kmh, posible: kmh <= limiteKmh, llegadaALimiteMs };
}

// Umbrales (lluvia según la escala de intensidad de AEMET).
export const UMBRALES = {
  lluviaIntensa: 15, // mm/h: lluvia fuerte
  lluviaMuyIntensa: 30, // mm/h: lluvia muy fuerte
  visibilidadBaja: 1000, // m
  visibilidadMuyBaja: 200, // m: niebla densa
  rachas: 70, // km/h
  rachasPeligro: 90, // km/h
  caudalAviso: 2, // veces el caudal habitual del río más cercano
  caudalPeligro: 4,
};

const NIVEL = { aviso: 1, peligro: 2 };

// Convierte los datos del tiempo en una lista de alertas ordenada por gravedad.
// t: { precipMmH, visibilidadM, rachasKmH, lluvia24h, lluvia72h, caudalRatio, codigo }
export function evaluarAlertas(t) {
  const alertas = [];
  const add = (tipo, nivel, texto) => alertas.push({ tipo, nivel, texto });
  const u = UMBRALES;
  const precip = t.precipMmH ?? 0;
  const codigo = t.codigo ?? -1;

  if (precip >= u.lluviaMuyIntensa) {
    add("lluvia", "peligro", `Lluvia muy intensa, ${Math.round(precip)} litros por hora`);
  } else if (precip >= u.lluviaIntensa || [65, 82].includes(codigo)) {
    add("lluvia", "aviso", "Lluvia intensa");
  }
  if (codigo >= 95) add("tormenta", "aviso", "Tormenta");

  const vis = t.visibilidadM;
  if (vis != null && vis < u.visibilidadMuyBaja) {
    add("visibilidad", "peligro", `Visibilidad muy baja, ${redondearVis(vis)} metros`);
  } else if (vis != null && vis < u.visibilidadBaja) {
    add("visibilidad", "aviso", `Visibilidad baja, ${redondearVis(vis)} metros`);
  } else if (vis == null && [45, 48].includes(codigo)) {
    add("visibilidad", "aviso", "Niebla, visibilidad reducida");
  }

  const l24 = t.lluvia24h ?? 0;
  const l72 = t.lluvia72h ?? 0;
  const caudal = t.caudalRatio ?? 0;
  if (caudal >= u.caudalPeligro || l24 >= 80 || precip >= 60) {
    add("desbordamiento", "peligro", "Peligro de desbordamiento e inundación en la vía");
  } else if (caudal >= u.caudalAviso || l24 >= 40) {
    add("desbordamiento", "aviso", "Riesgo de desbordamiento de ríos y balsas de agua");
  }

  if (l24 >= 100 || (l24 >= 60 && precip >= u.lluviaIntensa)) {
    add("derrumbe", "peligro", "Peligro de derrumbes y desprendimientos");
  } else if (l24 >= 60 || l72 >= 100) {
    add("derrumbe", "aviso", "Riesgo de derrumbes y desprendimientos");
  }

  const rachas = t.rachasKmH ?? 0;
  if (rachas >= u.rachasPeligro) {
    add("viento", "peligro", `Rachas de viento de ${Math.round(rachas)} kilómetros por hora`);
  } else if (rachas >= u.rachas) {
    add("viento", "aviso", `Viento fuerte, rachas de ${Math.round(rachas)}`);
  }

  return alertas.sort((a, b) => NIVEL[b.nivel] - NIVEL[a.nivel]);
}

function redondearVis(m) {
  return m < 200 ? Math.round(m / 10) * 10 : Math.round(m / 50) * 50;
}

// Descripción corta del tiempo para cuando no hay alertas.
export function describirTiempo(t) {
  const p = t.precipMmH ?? 0;
  if (p >= 2) return "lluvia moderada";
  if (p > 0.1) return "lluvia débil";
  if ([45, 48].includes(t.codigo)) return "niebla";
  if ([71, 73, 75, 77, 85, 86].includes(t.codigo)) return "nieve";
  return "sin lluvia";
}

// Frase que se lee en voz alta en cada aviso.
export function fraseVoz({ tiempo, alertas, velocidad, destino, completa }) {
  const partes = [];
  if (alertas.length) {
    // Si la situación no ha cambiado, cada 100 m basta con recordar la alerta principal.
    const lista = completa ? alertas : alertas.slice(0, 1);
    const prefijo = alertas[0].nivel === "peligro" ? "Atención. " : "Aviso. ";
    partes.push(prefijo + lista.map((a) => a.texto).join(". ") + " a 500 metros.");
  } else if (tiempo) {
    partes.push(`A 500 metros, ${describirTiempo(tiempo)}.`);
  }
  if (velocidad && Number.isFinite(velocidad.kmh)) {
    if (velocidad.posible) {
      partes.push(
        completa
          ? `Para llegar a ${destino} a tiempo, media de ${Math.round(velocidad.kmh)} kilómetros por hora.`
          : `Media ${Math.round(velocidad.kmh)}.`,
      );
    } else if (completa) {
      partes.push(`No se llega a ${destino} a tiempo respetando el límite de velocidad.`);
    }
  } else if (velocidad && completa) {
    partes.push(`Se ha superado la hora prevista de llegada a ${destino}.`);
  }
  return partes.join(" ");
}

// Cuenta la distancia recorrida y avisa cada vez que se cruza un múltiplo de `paso` metros.
// Ignora el ruido del GPS: posiciones imprecisas o saltos menores que el error.
export class Odometro {
  constructor(paso = 100) {
    this.paso = paso;
    this.total = 0;
    this.ultima = null;
  }

  // Devuelve cuántos tramos de `paso` metros se han completado con esta posición.
  anadir(pos, precision = 10) {
    if (precision > 50) return 0;
    if (!this.ultima) {
      this.ultima = pos;
      return 0;
    }
    const d = distancia(this.ultima, pos);
    if (d < Math.max(5, Math.min(precision, 30) / 2)) return 0;
    const antes = Math.floor(this.total / this.paso);
    this.total += d;
    this.ultima = pos;
    return Math.floor(this.total / this.paso) - antes;
  }
}

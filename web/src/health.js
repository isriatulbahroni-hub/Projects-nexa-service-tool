// Skor kesehatan heuristik dari data baca-saja (baterai, suhu, penyimpanan, RAM, patch).
// Tidak menguji layar, kamera, atau audio.
export function assess({ bat, storage, mem, patch }) {
  const reasons = [];
  let score = 100;
  const hit = (pts, level, title, detail) => { score -= pts; reasons.push({ level, title, detail }); };
  if (bat.healthCode > 2) hit(35, "bad", "Baterai", `Kesehatan baterai: ${bat.health}`);
  if (bat.temp != null) {
    if (bat.temp >= 50) hit(25, "bad", "Suhu baterai", `${bat.temp.toFixed(1)} °C, terlalu panas`);
    else if (bat.temp >= 42) hit(10, "warn", "Suhu baterai", `${bat.temp.toFixed(1)} °C, di atas batas wajar 42 °C`);
  }
  if (storage) {
    if (storage.percent >= 95) hit(20, "bad", "Penyimpanan", `${storage.percent}% terpakai, hampir penuh`);
    else if (storage.percent >= 85) hit(8, "warn", "Penyimpanan", `${storage.percent}% terpakai`);
  }
  if (mem && mem.percentFree < 5) hit(10, "warn", "RAM", "Hampir habis");
  const age = patch ? Math.floor((Date.now() - new Date(patch).getTime()) / 86400000) : null;
  if (age != null && age > 365) hit(5, "warn", "Security patch", `${age} hari lalu`);
  score = Math.max(0, score);
  const [level, verdict] = score >= 85 ? ["ok", "Kondisi baik"] : score >= 60 ? ["warn", "Perlu dicek"] : ["bad", "Perlu servis"];
  return { score, level, verdict, reasons };
}

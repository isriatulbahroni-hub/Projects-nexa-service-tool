// Pantauan langsung: ambil data baterai tiap beberapa detik dan gambar sparkline SVG.
export function startLive(box, read, every = 3000, max = 40) {
  const temp = [], level = [];
  let dead = false, timer = null;
  const spark = (title, arr, unit, lo, hi) => {
    const last = arr[arr.length - 1];
    let pts = "";
    if (arr.length > 1) {
      const min = lo ?? Math.min(...arr) - 1, top = hi ?? Math.max(...arr) + 1;
      pts = arr.map((v, i) => `${((i / (max - 1)) * 200).toFixed(1)},${(48 - ((v - min) / (top - min || 1)) * 44).toFixed(1)}`).join(" ");
    }
    return `<div class="spark"><small>${title}</small> <b>${last != null ? last + unit : "-"}</b>
      <svg viewBox="0 0 200 50" preserveAspectRatio="none" role="img" aria-label="${title}">${pts ? `<polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/>` : ""}</svg>
      ${arr.length < 2 ? `<small>Mengumpulkan data…</small>` : ""}</div>`;
  };
  const draw = () => { if (!dead) box.innerHTML = spark("Suhu baterai", temp, " °C") + spark("Level baterai", level, "%", 0, 100); };
  const tick = async () => {
    if (dead) return;
    try {
      const b = await read();
      if (b.temp != null) temp.push(Number(b.temp.toFixed(1)));
      if (b.level != null) level.push(Number(b.level));
      if (temp.length > max) temp.shift();
      if (level.length > max) level.shift();
      draw();
    } catch {}
    if (!dead) timer = setTimeout(tick, every);
  };
  draw();
  tick();
  return () => { dead = true; clearTimeout(timer); };
}

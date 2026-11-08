// Riwayat pengukuran per HP, disimpan di browser ini saja (localStorage).
const key = (serial) => `nexa-hist:${serial || "unknown"}`;

export function listSnaps(serial) {
  try { return JSON.parse(localStorage.getItem(key(serial))) || []; } catch { return []; }
}

export function addSnap(serial, snap, minGapMs = 60000) {
  const list = listSnaps(serial);
  const last = list[list.length - 1];
  if (!snap.tag && last && !last.tag && snap.t - last.t < minGapMs) return list;
  const next = [...list, snap].slice(-60);
  try { localStorage.setItem(key(serial), JSON.stringify(next)); } catch {}
  return next;
}

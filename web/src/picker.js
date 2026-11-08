// Pemilih aplikasi untuk halaman Perbaikan: daftar paket pihak ketiga dan yang dinonaktifkan,
// ketuk salah satu untuk mengisi kolom nama paket.
export function attachPkgPicker(view, { sh, esc }) {
  const pkg = view.querySelector("#pkg");
  if (!pkg) return;
  const row = pkg.closest(".row");
  if (!row) return;
  row.insertAdjacentHTML(
    "afterend",
    `<div class="row"><input id="pkgq" placeholder="Cari aplikasi terpasang, ketuk untuk memilih…" /></div>
     <div id="pkgbox" style="max-height:220px;overflow:auto"></div>`,
  );
  const q = view.querySelector("#pkgq");
  const box = view.querySelector("#pkgbox");
  let all = [];
  let disabled = new Set();

  const draw = () => {
    const f = q.value.trim().toLowerCase();
    const list = all.filter((p) => !f || p.toLowerCase().includes(f)).slice(0, 200);
    box.innerHTML = list.length
      ? `<table>${list.map((p) => `<tr><td><span class="link" data-p="${esc(p)}">${esc(p)}</span></td><td class="muted">${disabled.has(p) ? "nonaktif" : ""}</td></tr>`).join("")}</table>`
      : `<p class="muted">Tidak ada aplikasi yang cocok.</p>`;
  };

  box.innerHTML = `<p class="muted">Memuat daftar aplikasi…</p>`;
  const toList = (t) => t.split("\n").map((l) => l.replace("package:", "").trim()).filter(Boolean);
  Promise.all([sh("pm list packages -3"), sh("pm list packages -d")]).then(([user, dis]) => {
    disabled = new Set(toList(dis));
    all = [...new Set([...toList(user), ...disabled])].sort();
    draw();
  });

  q.oninput = draw;
  box.onclick = (e) => {
    const p = e.target.dataset?.p;
    if (!p) return;
    pkg.value = p;
    pkg.scrollIntoView?.({ block: "nearest" });
  };
}

# Kenapa workflow ini dinonaktifkan

`integrate-hardware-ui.yml` awalnya dibuat sebagai jembatan otomatis untuk
mengintegrasikan fitur Hardware Test (saat itu masih eksperimental) ke
`app.py` setiap ada push, lengkap dengan kill-switch `[skip hardware ui]`
di pesan commit.

Sejak Hardware Test permanen terintegrasi langsung di `app.py` (nav button,
page, dan seluruh handler sudah ada secara native), workflow ini jadi
berisiko: setiap push baru akan mencoba re-inject versi lama dari kode
Hardware Test, berpotensi menimpa perubahan manual di `app.py` tanpa
review manusia.

Workflow dipindah ke folder ini (bukan dihapus) supaya riwayatnya tetap
bisa dilihat. `tools/integrate_hardware_ui.py` juga sudah tidak dipanggil
oleh workflow manapun.

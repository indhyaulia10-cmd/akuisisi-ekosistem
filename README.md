# Dashboard Akuisisi Ekosistem Bisnis (lokal)

Berjalan 100% di komputer sendiri (SQLite + Streamlit), tanpa hosting.

## Menjalankan
    cd akuisisi_ekosistem
    pip install -r requirements.txt
    python -m streamlit run app.py

Browser terbuka di http://localhost:8501 (jangan jalankan dengan `python app.py`).

## Menu
1. Peta Ekosistem Bisnis      : total simpanan per minggu/bulan/tahun, peta segmen (treemap), perbandingan perusahaan
2. Progres Akuisisi & Performa Ritel : profil singkat, produk eksisting, potensi bisnis, tabel CIF ekosistem
3. Fokus Akuisisi             : profil, transformasi valas, pertumbuhan dana, pipeline cross-selling
4. Timeline Akuisisi          : Gantt tahapan akuisisi + status
5. Kelola Data                : input simpanan mingguan, valas bulanan, tambah/ubah/hapus perusahaan

## Berkas
- app.py     : tampilan dashboard
- db.py      : skema SQLite, data contoh, fungsi baca/tulis
- utils.py   : format Rupiah/USD + agregasi time series
- akuisisi_ekosistem.db : dibuat otomatis (hapus untuk reset ke data contoh)

Data bawaan adalah DATA CONTOH (fiktif). Tabel CIF hanya menyimpan jumlah agregat per segmen,
bukan data nasabah per orang.

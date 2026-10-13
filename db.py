"""Database lokal (SQLite) untuk dashboard akuisisi ekosistem bisnis.

File database: akuisisi_ekosistem.db (di folder yang sama).
Pertama kali dijalankan, tabel dibuat otomatis dan diisi DATA CONTOH (fiktif).
Reset: hapus file akuisisi_ekosistem.db lalu jalankan ulang aplikasi.
"""
import random
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).parent / "akuisisi_ekosistem.db"

# --------------------------------------------------------------------------
# Konstanta domain
# --------------------------------------------------------------------------
SEGMENTS = ["Perusahaan (Anchor)", "Karyawan", "Supplier & Vendor", "Distributor & Mitra", "Pelanggan"]
RETAIL_SEGMENTS = ["Karyawan", "Pelanggan"]

STAGES = ["Lead", "Presentasi", "Penawaran", "Negosiasi", "Closing (Won)"]
STAGE_PROB = {"Lead": 0.10, "Presentasi": 0.25, "Penawaran": 0.50, "Negosiasi": 0.75, "Closing (Won)": 1.0}

CATEGORIES = ["Dana", "Transaksi", "Valas", "Kredit", "Digital", "Fee-based"]
# (produk, kategori, bulan ke-berapa sejak mulai akuisisi produk ini mulai aktif)
PRODUCT_CATALOG = [
    ("Giro Operasional", "Dana", 0),
    ("Deposito Berjangka", "Dana", 3),
    ("Payroll", "Transaksi", 4),
    ("Cash Management (Virtual Account)", "Transaksi", 5),
    ("BRImo Karyawan", "Digital", 7),
    ("QRIS & EDC Merchant", "Digital", 9),
    ("Valas & Trade Finance", "Valas", 10),
    ("Kredit Modal Kerja", "Kredit", 13),
    ("Asuransi & Dana Pensiun", "Fee-based", 16),
]
PRODUCT_NAMES = [p[0] for p in PRODUCT_CATALOG]

STATUSES = ["Rencana", "Berjalan", "Selesai"]

PHASES = [  # (judul, mulai_bulan, selesai_bulan, PIC, catatan)
    ("Identifikasi & Pemetaan Ekosistem", 0, 1, "RM Korporasi", "Mapping anchor, karyawan, supplier, distributor, pelanggan."),
    ("Presentasi & Penawaran Solusi", 1, 2, "RM Korporasi", "Paparan solusi transaksi, dana, valas, dan ritel."),
    ("Negosiasi & Kesepakatan Kerja Sama", 2, 4, "Tim Korporasi", "Finalisasi MoU/PKS dan skema layanan."),
    ("Onboarding Anchor", 4, 6, "Tim Korporasi", "Pembukaan rekening, cash management, fasilitas operasional."),
    ("Akuisisi Karyawan", 5, 9, "Tim Ritel", "Payroll, rekening karyawan, dan mobile banking."),
    ("Akuisisi Supplier & Distributor", 8, 12, "Tim Bisnis", "Onboarding mitra rantai pasok dan penyaluran dana."),
    ("Transformasi Valas", 9, 14, "Tim Treasury", "Pengalihan transaksi valas ke BRI."),
    ("Cross-selling & Evaluasi", 12, 20, "RM Korporasi", "Produk lanjutan dan evaluasi capaian akuisisi."),
]

# Kolom yang bisa diedit lewat tabel (urutan kolom pertama = kunci wajib terisi)
EDITABLE = {
    "cif_segments": ["segment", "potensi_cif", "cif_terakuisisi", "cif_aktif"],
    "products_existing": ["product", "category", "status", "volume", "notes"],
    "business_potential": ["source", "est_value", "probability", "notes"],
    "pipeline": ["product", "stage", "est_value", "pic", "target_date"],
    "timeline": ["title", "urutan", "start_date", "end_date", "status", "pic", "notes"],
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sector TEXT, city TEXT, founded_year INTEGER, employees INTEGER,
    annual_revenue REAL, rm_name TEXT, acq_start TEXT, description TEXT
);
-- Saldo simpanan per MINGGU per segmen ekosistem (posisi akhir minggu, tanggal Senin)
CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    week_start TEXT NOT NULL, segment TEXT NOT NULL,
    giro REAL DEFAULT 0, tabungan REAL DEFAULT 0, deposito REAL DEFAULT 0,
    UNIQUE (company_id, week_start, segment)
);
-- Volume transaksi valas per bulan (USD): via BRI vs via bank lain
CREATE TABLE IF NOT EXISTS fx_monthly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    month TEXT NOT NULL, bri_volume REAL DEFAULT 0, other_volume REAL DEFAULT 0,
    UNIQUE (company_id, month)
);
-- Tabel CIF ekosistem (agregat jumlah CIF per segmen, bukan data nasabah per orang)
CREATE TABLE IF NOT EXISTS cif_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    segment TEXT NOT NULL, potensi_cif INTEGER DEFAULT 0,
    cif_terakuisisi INTEGER DEFAULT 0, cif_aktif INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS products_existing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    product TEXT NOT NULL, category TEXT, status TEXT DEFAULT 'Aktif',
    volume REAL DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS business_potential (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    source TEXT NOT NULL, est_value REAL DEFAULT 0, probability REAL DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS pipeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    product TEXT NOT NULL, stage TEXT DEFAULT 'Lead', est_value REAL DEFAULT 0,
    pic TEXT, target_date TEXT
);
CREATE TABLE IF NOT EXISTS timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    urutan INTEGER DEFAULT 0, title TEXT NOT NULL,
    start_date TEXT, end_date TEXT, status TEXT DEFAULT 'Rencana', pic TEXT, notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_dep ON deposits (company_id, week_start);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def months_between(d1: date, d2: date) -> float:
    return (d2 - d1).days / 30.4


# --------------------------------------------------------------------------
# Pembangun data standar (dipakai seed dan saat menambah perusahaan baru)
# --------------------------------------------------------------------------
def _build_timeline(conn, cid, start: date):
    today = date.today()
    rows = []
    for i, (title, s, e, pic, note) in enumerate(PHASES, start=1):
        sd = start + timedelta(days=int(s * 30.4))
        ed = start + timedelta(days=int(e * 30.4))
        status = "Selesai" if ed < today else ("Berjalan" if sd <= today else "Rencana")
        rows.append((cid, i, title, sd.isoformat(), ed.isoformat(), status, pic, note))
    conn.executemany(
        "INSERT INTO timeline (company_id, urutan, title, start_date, end_date, status, pic, notes) "
        "VALUES (?,?,?,?,?,?,?,?)", rows)


# segmen: (faktor potensi terhadap jumlah karyawan, bulan mulai, durasi bulan, rasio maks)
CIF_RULES = {
    "Perusahaan (Anchor)": (None, 3, 3, 1.0),
    "Karyawan": (1.0, 5, 14, 0.85),
    "Supplier & Vendor": (0.12, 8, 14, 0.60),
    "Distributor & Mitra": (0.06, 8, 14, 0.60),
    "Pelanggan": (2.5, 10, 20, 0.30),
}


def _build_cif(conn, cid, employees, start: date):
    m = months_between(start, date.today())
    rows = []
    for seg in SEGMENTS:
        factor, s, dur, mx = CIF_RULES[seg]
        potensi = 5 if factor is None else max(1, round((employees or 0) * factor))
        ratio = min(1.0, max(0.0, (m - s) / dur)) * mx
        acq = round(potensi * ratio)
        rows.append((cid, seg, potensi, acq, round(acq * 0.78)))
    conn.executemany(
        "INSERT INTO cif_segments (company_id, segment, potensi_cif, cif_terakuisisi, cif_aktif) "
        "VALUES (?,?,?,?,?)", rows)


# --------------------------------------------------------------------------
# Data contoh (FIKTIF)
# --------------------------------------------------------------------------
SEED = [
    dict(name="PT Karya Tekstil Prima", sector="Manufaktur Tekstil & Ekspor", city="Bandung", founded=2001,
         employees=3400, revenue=3.1e12, rm="Dimas Prasetyo", acq=date(2025, 2, 3), base=14e9, g_post=0.010,
         fx_base=4.5e6, fx_s1=0.55,
         desc="Produsen tekstil dan garmen berorientasi ekspor dengan jaringan supplier bahan baku dan distributor di beberapa negara."),
    dict(name="PT Mitra Logistik Bahari", sector="Logistik & Pelayaran", city="Semarang", founded=2012,
         employees=1200, revenue=1.6e12, rm="Rina Kusuma", acq=date(2025, 9, 1), base=9e9, g_post=0.012,
         fx_base=2.2e6, fx_s1=0.50,
         desc="Penyedia layanan pengiriman laut, darat, dan pergudangan dengan banyak vendor pelabuhan dan armada."),
    dict(name="PT Samudra Pangan Nusantara", sector="Perikanan & Pangan", city="Surabaya", founded=2009,
         employees=1850, revenue=2.4e12, rm="Agus Santoso", acq=date(2026, 2, 2), base=12e9, g_post=0.014,
         fx_base=3.0e6, fx_s1=0.50,
         desc="Pengolahan dan ekspor hasil laut dengan ribuan mitra nelayan dan distributor pangan."),
    dict(name="PT Cahaya Energi Mandiri", sector="Energi", city="Jakarta", founded=2006,
         employees=2600, revenue=5.2e12, rm="Maya Lestari", acq=date(2026, 6, 1), base=25e9, g_post=0.018,
         fx_base=6.0e6, fx_s1=0.45,
         desc="Pengelola pembangkit dan distribusi energi dengan kontraktor, vendor O&M, dan pelanggan industri."),
    dict(name="PT Medika Sehat Sentosa", sector="Kesehatan", city="Yogyakarta", founded=2015,
         employees=900, revenue=0.9e12, rm="Fajar Nugroho", acq=date(2026, 9, 1), base=3e9, g_post=0.020,
         fx_base=0.3e6, fx_s1=0.40,
         desc="Jaringan klinik dan farmasi dengan pemasok alat kesehatan, apotek mitra, dan pasien berlangganan."),
]

SEG_SHARE = {"Perusahaan (Anchor)": 0.34, "Karyawan": 0.26, "Supplier & Vendor": 0.14,
             "Distributor & Mitra": 0.16, "Pelanggan": 0.10}
SEG_BOOST = {"Perusahaan (Anchor)": 0.8, "Karyawan": 1.3, "Supplier & Vendor": 1.0,
             "Distributor & Mitra": 1.0, "Pelanggan": 1.1}
SEG_MIX = {  # proporsi (giro, tabungan, deposito)
    "Perusahaan (Anchor)": (0.55, 0.10, 0.35),
    "Karyawan": (0.05, 0.80, 0.15),
    "Supplier & Vendor": (0.40, 0.40, 0.20),
    "Distributor & Mitra": (0.45, 0.35, 0.20),
    "Pelanggan": (0.10, 0.75, 0.15),
}
PICS = ["RM Korporasi", "Tim Ritel", "Tim Treasury", "Tim Bisnis", "Tim Digital"]


def _seed(conn):
    rnd = random.Random(7)
    today = date.today()
    start = date(2023, 1, 2)
    end = monday_of(today)

    for c in SEED:
        cur = conn.execute(
            "INSERT INTO companies (name, sector, city, founded_year, employees, annual_revenue, rm_name, "
            "acq_start, description) VALUES (?,?,?,?,?,?,?,?,?)",
            (c["name"], c["sector"], c["city"], c["founded"], c["employees"], c["revenue"], c["rm"],
             c["acq"].isoformat(), c["desc"]))
        cid = cur.lastrowid

        # ---- Simpanan mingguan per segmen
        levels = {s: c["base"] * SEG_SHARE[s] * rnd.uniform(0.9, 1.1) for s in SEGMENTS}
        rows, wk = [], start
        while wk <= end:
            post = wk >= c["acq"]
            for s in SEGMENTS:
                g = c["g_post"] * SEG_BOOST[s] if post else 0.0012
                levels[s] *= (1 + g) * rnd.uniform(0.985, 1.015)
                w = [x * rnd.uniform(0.98, 1.02) for x in SEG_MIX[s]]
                tot = sum(w)
                giro, tab, dep = (levels[s] * x / tot for x in w)
                rows.append((cid, wk.isoformat(), s, round(giro), round(tab), round(dep)))
            wk += timedelta(weeks=1)
        conn.executemany(
            "INSERT INTO deposits (company_id, week_start, segment, giro, tabungan, deposito) "
            "VALUES (?,?,?,?,?,?)", rows)

        # ---- Valas bulanan (pangsa BRI naik setelah fase Transformasi Valas)
        ramp_start = c["acq"] + timedelta(days=int(9 * 30.4))
        m, i, fx_rows = date(2023, 1, 1), 0, []
        while m <= date(today.year, today.month, 1):
            total = c["fx_base"] * (1.012 ** i) * rnd.uniform(0.85, 1.15)
            ramp = min(1.0, max(0.0, months_between(ramp_start, m) / 10))
            share = 0.10 + (c["fx_s1"] - 0.10) * ramp + rnd.uniform(-0.02, 0.02)
            share = min(0.95, max(0.02, share))
            fx_rows.append((cid, m.strftime("%Y-%m"), round(total * share), round(total * (1 - share))))
            m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
            i += 1
        conn.executemany(
            "INSERT INTO fx_monthly (company_id, month, bri_volume, other_volume) VALUES (?,?,?,?)", fx_rows)

        # ---- CIF, timeline
        _build_cif(conn, cid, c["employees"], c["acq"])
        _build_timeline(conn, cid, c["acq"])

        # ---- Produk eksisting
        m_now = months_between(c["acq"], today)
        for prod, cat, off in PRODUCT_CATALOG:
            if m_now >= off:
                status = "Aktif" if rnd.random() > 0.12 else "Dormant"
                conn.execute(
                    "INSERT INTO products_existing (company_id, product, category, status, volume, notes) "
                    "VALUES (?,?,?,?,?,?)",
                    (cid, prod, cat, status, round(c["revenue"] * rnd.uniform(0.0008, 0.006)), "Data contoh"))

        # ---- Potensi bisnis
        emp, rev = c["employees"], c["revenue"]
        for src, val, prob, note in [
            ("Dana ekosistem (CASA & deposito)", rev * 0.02, 60, "Konsolidasi dana anchor dan mitra"),
            ("Payroll & ritel karyawan", emp * 15e6, 70, "Rata-rata saldo karyawan"),
            ("Transaksi valas & trade finance", rev * 0.012, 50, "Ekspor-impor dan lindung nilai"),
            ("Supply chain financing", rev * 0.03, 40, "Pembiayaan supplier & distributor"),
            ("Merchant, QRIS & digital pelanggan", emp * 8e6, 35, "Basis pelanggan ekosistem"),
            ("Kredit modal kerja", rev * 0.04, 30, "Kebutuhan modal kerja anchor"),
        ]:
            conn.execute(
                "INSERT INTO business_potential (company_id, source, est_value, probability, notes) "
                "VALUES (?,?,?,?,?)", (cid, src, round(val), prob, note))

        # ---- Pipeline cross-selling
        weights = [5, 3, 1, 0.3, 0] if m_now < 3 else ([3, 3, 3, 2, 0.5] if m_now < 9 else [1, 2, 3, 3, 3])
        belum = [p[0] for p in PRODUCT_CATALOG if m_now < p[2]]
        pool = belum + [p for p in PRODUCT_NAMES if p not in belum]
        for prod in pool[:rnd.randint(5, 7)]:
            conn.execute(
                "INSERT INTO pipeline (company_id, product, stage, est_value, pic, target_date) VALUES (?,?,?,?,?,?)",
                (cid, prod, rnd.choices(STAGES, weights)[0], round(rev * rnd.uniform(0.002, 0.01)),
                 rnd.choice(PICS), (today + timedelta(days=rnd.randint(15, 180))).isoformat()))


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0:
            _seed(conn)


# --------------------------------------------------------------------------
# Baca
# --------------------------------------------------------------------------
def list_companies() -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query("SELECT * FROM companies ORDER BY name", conn)


def get_deposits(company_id=None) -> pd.DataFrame:
    sql = ("SELECT d.company_id, c.name AS company_name, d.week_start, d.segment, d.giro, d.tabungan, "
           "d.deposito, (d.giro + d.tabungan + d.deposito) AS total "
           "FROM deposits d JOIN companies c ON c.id = d.company_id")
    params = ()
    if company_id is not None:
        sql += " WHERE d.company_id = ?"
        params = (int(company_id),)
    sql += " ORDER BY d.week_start"
    with connect() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def get_fx(company_id) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT month, bri_volume, other_volume FROM fx_monthly WHERE company_id = ? ORDER BY month",
            conn, params=(int(company_id),))


def get_table(table: str, company_id) -> pd.DataFrame:
    if table not in EDITABLE:
        raise ValueError("Tabel tidak dikenal")
    order = "urutan, id" if table == "timeline" else "id"
    with connect() as conn:
        return pd.read_sql_query(
            f"SELECT * FROM {table} WHERE company_id = ? ORDER BY {order}", conn, params=(int(company_id),))


# --------------------------------------------------------------------------
# Tulis
# --------------------------------------------------------------------------
def _clean(v):
    if v is None:
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return None if pd.isna(v) else pd.Timestamp(v).date().isoformat()
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        v = v.item()
    return v.strip() if isinstance(v, str) else v


def replace_rows(table: str, company_id, df: pd.DataFrame):
    """Ganti seluruh baris tabel untuk satu perusahaan dengan isi tabel editor."""
    cols = EDITABLE[table]
    rows = []
    for _, r in df.iterrows():
        vals = [_clean(r.get(c)) for c in cols]
        if vals[0] in (None, ""):          # baris kosong -> lewati
            continue
        if table == "timeline" and vals[1] is None:
            vals[1] = len(rows) + 1
        rows.append((int(company_id), *vals))
    with connect() as conn:
        conn.execute(f"DELETE FROM {table} WHERE company_id = ?", (int(company_id),))
        conn.executemany(
            f"INSERT INTO {table} (company_id, {', '.join(cols)}) VALUES ({', '.join(['?'] * (len(cols) + 1))})",
            rows)


def upsert_deposits(company_id, week_date: date, items: list):
    """items: [(segment, giro, tabungan, deposito), ...] untuk satu minggu."""
    week = monday_of(week_date).isoformat()
    with connect() as conn:
        for seg, giro, tab, dep in items:
            conn.execute(
                """INSERT INTO deposits (company_id, week_start, segment, giro, tabungan, deposito)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT (company_id, week_start, segment) DO UPDATE SET
                     giro = excluded.giro, tabungan = excluded.tabungan, deposito = excluded.deposito""",
                (int(company_id), week, seg, float(giro or 0), float(tab or 0), float(dep or 0)))
    return week


def upsert_fx(company_id, month_date: date, bri, other):
    month = month_date.strftime("%Y-%m")
    with connect() as conn:
        conn.execute(
            """INSERT INTO fx_monthly (company_id, month, bri_volume, other_volume) VALUES (?,?,?,?)
               ON CONFLICT (company_id, month) DO UPDATE SET
                 bri_volume = excluded.bri_volume, other_volume = excluded.other_volume""",
            (int(company_id), month, float(bri), float(other)))
    return month


_COMPANY_COLS = ["name", "sector", "city", "founded_year", "employees", "annual_revenue", "rm_name",
                 "acq_start", "description"]


def add_company(d: dict) -> int:
    """Tambah perusahaan + timeline standar + tabel CIF awal."""
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO companies ({', '.join(_COMPANY_COLS)}) VALUES ({', '.join(['?'] * len(_COMPANY_COLS))})",
            [d.get(c) for c in _COMPANY_COLS])
        cid = cur.lastrowid
        start = date.fromisoformat(d["acq_start"])
        _build_timeline(conn, cid, start)
        _build_cif(conn, cid, d.get("employees") or 0, start)
        return cid


def update_company(company_id, d: dict):
    with connect() as conn:
        conn.execute(
            f"UPDATE companies SET {', '.join(c + ' = ?' for c in _COMPANY_COLS)} WHERE id = ?",
            [d.get(c) for c in _COMPANY_COLS] + [int(company_id)])


def delete_company(company_id):
    with connect() as conn:
        conn.execute("DELETE FROM companies WHERE id = ?", (int(company_id),))


def create_default_timeline(company_id, start: date):
    with connect() as conn:
        _build_timeline(conn, int(company_id), start)


if __name__ == "__main__":
    init_db()
    print("Database siap:", DB_PATH)

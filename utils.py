"""Utilitas: format angka gaya Indonesia + agregasi time series simpanan."""
import pandas as pd

PERIODS = ["Mingguan", "Bulanan", "Tahunan"]
_BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


# --------------------------------------------------------------------------
# Format
# --------------------------------------------------------------------------
def id_number(v: float, decimals: int = 2) -> str:
    s = f"{v:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _bad(v) -> bool:
    return v is None or pd.isna(v) or v in (float("inf"), float("-inf"))


def rp(v) -> str:
    if _bad(v):
        return "-"
    a, sign = abs(v), "-" if v < 0 else ""
    if a >= 1e12:
        return f"{sign}Rp {id_number(a / 1e12)} T"
    if a >= 1e9:
        return f"{sign}Rp {id_number(a / 1e9)} M"
    if a >= 1e6:
        return f"{sign}Rp {id_number(a / 1e6)} Jt"
    return f"{sign}Rp {id_number(a, 0)}"


def usd(v) -> str:
    if _bad(v):
        return "-"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e9:
        return f"{sign}USD {id_number(a / 1e9)} M"
    if a >= 1e6:
        return f"{sign}USD {id_number(a / 1e6)} Jt"
    if a >= 1e3:
        return f"{sign}USD {id_number(a / 1e3, 1)} Rb"
    return f"{sign}USD {id_number(a, 0)}"


def pct(v, decimals: int = 1) -> str:
    if _bad(v):
        return "-"
    return f"{id_number(v, decimals)}%"


def num(v) -> str:
    if _bad(v):
        return "-"
    return f"{int(round(v)):,}".replace(",", ".")


def fmt_date(v) -> str:
    t = pd.to_datetime(v, errors="coerce")
    if pd.isna(t):
        return "-"
    return f"{t.day:02d} {_BULAN[t.month - 1]} {t.year}"


def period_label(ts, period: str) -> str:
    ts = pd.Timestamp(ts)
    if period == "Mingguan":
        return fmt_date(ts)
    if period == "Bulanan":
        return f"{_BULAN[ts.month - 1]} {ts.year}"
    return str(ts.year)


# --------------------------------------------------------------------------
# Agregasi time series untuk SALDO (stock)
# --------------------------------------------------------------------------
def add_period(df: pd.DataFrame, period: str, col: str = "week_start") -> pd.DataFrame:
    d = df.copy()
    d["tanggal"] = pd.to_datetime(d[col])
    if period == "Mingguan":
        d["periode"] = d["tanggal"]
    elif period == "Bulanan":
        d["periode"] = d["tanggal"].dt.to_period("M").dt.to_timestamp()
    else:
        d["periode"] = d["tanggal"].dt.to_period("Y").dt.to_timestamp()
    return d


def snapshot_by_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Saldo adalah posisi (stock), jadi nilai bulanan/tahunan = posisi minggu
    terakhir pada periode tersebut (bukan dijumlahkan)."""
    d = add_period(df, period)
    d["_last"] = d.groupby(["company_id", "periode"])["tanggal"].transform("max")
    return d[d["tanggal"] == d["_last"]].drop(columns="_last")


def total_series(df: pd.DataFrame, period: str, by=None) -> pd.DataFrame:
    """Total simpanan per periode (+ CASA ratio dan pertumbuhan)."""
    snap = snapshot_by_period(df, period)
    keys = list(by or []) + ["periode"]
    g = snap.groupby(keys, as_index=False)[["giro", "tabungan", "deposito", "total"]].sum()
    g = g.sort_values(keys).reset_index(drop=True)
    g["casa_ratio"] = (g["giro"] + g["tabungan"]) / g["total"].where(g["total"] > 0) * 100
    if by:
        g["growth"] = g.groupby(by)["total"].pct_change() * 100
    else:
        g["growth"] = g["total"].pct_change() * 100
    return g

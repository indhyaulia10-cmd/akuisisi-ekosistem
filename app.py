"""Dashboard Akuisisi Ekosistem Bisnis (lokal, tanpa hosting).

Jalankan:  python -m streamlit run app.py
"""
import sqlite3
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import db
from utils import (PERIODS, fmt_date, num, pct, period_label, rp, snapshot_by_period,
                   total_series, usd)

st.set_page_config(page_title="Akuisisi Ekosistem Bisnis", page_icon="🏦", layout="wide")
db.init_db()

PAGES = ["Peta Ekosistem Bisnis", "Progres Akuisisi & Performa Ritel", "Fokus Akuisisi",
         "Timeline Akuisisi", "Kelola Data"]
STATUS_COLORS = {"Selesai": "#2e7d32", "Berjalan": "#f9a825", "Rencana": "#9e9e9e"}

# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
companies = db.list_companies()
st.sidebar.title("🏦 Akuisisi Ekosistem")
page = st.sidebar.radio("Menu", PAGES)

if companies.empty:
    st.sidebar.caption("Belum ada perusahaan.")
    company, cid, sel_name = None, None, None
else:
    sel_name = st.sidebar.selectbox("Perusahaan", companies["name"].tolist())
    company = companies[companies["name"] == sel_name].iloc[0]
    cid = int(company["id"])
st.sidebar.divider()
st.sidebar.caption("Database lokal: " + db.DB_PATH.name)
st.sidebar.caption("⚠️ Data bawaan adalah data contoh (fiktif).")


# --------------------------------------------------------------------------
# Helper
# --------------------------------------------------------------------------
def kv(col, label, value):
    col.caption(label)
    col.markdown(f"**{value}**")


def safe_int(v, default=0):
    return default if pd.isna(v) else int(v)


def phase_now(company_id) -> str:
    tl = db.get_table("timeline", company_id)
    if tl.empty:
        return "-"
    run = tl[tl["status"] == "Berjalan"]
    if not run.empty:
        return " + ".join(run["title"].head(2).tolist())
    if (tl["status"] == "Selesai").all():
        return "Seluruh tahap selesai"
    nxt = tl[tl["status"] == "Rencana"]
    return "Berikutnya: " + nxt.iloc[0]["title"] if not nxt.empty else "-"


def table_editor(table, company_id, key, column_config=None, date_cols=()):
    """Editor tabel generik: tampilkan, ubah, lalu simpan (ganti semua baris perusahaan)."""
    cols = db.EDITABLE[table]
    df = db.get_table(table, company_id)[cols].copy()
    for c in date_cols:
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    vkey = f"ver_{key}_{company_id}"
    ver = st.session_state.get(vkey, 0)
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, column_config=column_config,
                            key=f"ed_{key}_{company_id}_{ver}")
    if st.button("💾 Simpan perubahan", key=f"sv_{key}_{company_id}"):
        try:
            db.replace_rows(table, company_id, edited)
        except sqlite3.Error as e:
            st.error(f"Gagal menyimpan: {e}")
        else:
            st.session_state[vkey] = ver + 1
            st.toast("Perubahan tersimpan ✅")
            st.rerun()


def render_profile():
    st.markdown(f"#### {company['name']}")
    st.write(company["description"] or "-")
    a, b, c, d = st.columns(4)
    kv(a, "Sektor", company["sector"] or "-")
    kv(b, "Kota", company["city"] or "-")
    kv(c, "Tahun berdiri", safe_int(company["founded_year"]) or "-")
    kv(d, "Jumlah karyawan", num(company["employees"]))
    e, f, g, h = st.columns(4)
    kv(e, "Omzet tahunan", rp(company["annual_revenue"]))
    kv(f, "Mulai akuisisi", fmt_date(company["acq_start"]))
    kv(g, "Relationship Manager", company["rm_name"] or "-")
    kv(h, "Fase saat ini", phase_now(cid))


# --------------------------------------------------------------------------
# Halaman 1: Peta Ekosistem Bisnis
# --------------------------------------------------------------------------
def page_map():
    st.title("🗺️ Peta Ekosistem Bisnis")
    st.caption(f"Total simpanan (giro + tabungan + deposito) ekosistem **{sel_name}**. "
               "Nilai bulanan/tahunan adalah posisi saldo akhir periode, bukan penjumlahan.")
    period = st.radio("Periode", PERIODS, horizontal=True, index=1, key="map_period")
    dep = db.get_deposits(cid)

    if dep.empty:
        st.info("Belum ada data simpanan untuk perusahaan ini. Isi lewat menu Kelola Data.")
    else:
        g = total_series(dep, period)
        last = g.iloc[-1]
        snap = snapshot_by_period(dep, period)
        cur = snap[snap["periode"] == snap["periode"].max()]
        seg_tot = cur.groupby("segment")["total"].sum().sort_values(ascending=False)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total simpanan", rp(last["total"]),
                  delta=pct(last["growth"]) if pd.notna(last["growth"]) else None)
        k2.metric("CASA ratio (giro + tabungan)", pct(last["casa_ratio"]))
        k3.metric("Segmen terbesar", seg_tot.index[0])
        k4.metric("Posisi data per", fmt_date(cur["tanggal"].max()))

        left, right = st.columns(2)
        with left:
            m = cur.melt(id_vars=["segment"], value_vars=["giro", "tabungan", "deposito"],
                         var_name="jenis", value_name="saldo")
            m["jenis"] = m["jenis"].str.capitalize()
            fig = px.treemap(m, path=[px.Constant(sel_name), "segment", "jenis"], values="saldo",
                             color="segment", title="Peta ekosistem: segmen → jenis simpanan")
            fig.update_traces(textinfo="label+percent parent")
            fig.update_layout(margin=dict(l=5, r=5, t=50, b=5))
            st.plotly_chart(fig)
        with right:
            gs = total_series(dep, period, by=["segment"])
            labels = {"periode": "Periode", "total": "Total simpanan (Rp)", "segment": "Segmen"}
            if period == "Tahunan":
                fig = px.bar(gs, x="periode", y="total", color="segment", labels=labels,
                             title="Total simpanan per segmen (tahunan)")
                fig.update_xaxes(dtick="M12", tickformat="%Y")
            else:
                fig = px.area(gs, x="periode", y="total", color="segment", labels=labels,
                              title=f"Total simpanan per segmen ({period.lower()})")
            fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=-0.25))
            st.plotly_chart(fig)

        st.subheader("Komposisi segmen (periode terakhir)")
        comp = seg_tot.reset_index()
        comp.columns = ["Segmen", "Total"]
        comp["Porsi"] = comp["Total"] / comp["Total"].sum() * 100
        st.dataframe(pd.DataFrame({"Segmen": comp["Segmen"], "Total simpanan": comp["Total"].map(rp),
                                   "Porsi": comp["Porsi"].map(pct)}), hide_index=True)

        st.subheader(f"Total simpanan {period.lower()}")
        tbl = g.sort_values("periode", ascending=False)
        st.dataframe(pd.DataFrame({
            "Periode": tbl["periode"].map(lambda t: period_label(t, period)),
            "Total simpanan": tbl["total"].map(rp), "Giro": tbl["giro"].map(rp),
            "Tabungan": tbl["tabungan"].map(rp), "Deposito": tbl["deposito"].map(rp),
            "CASA ratio": tbl["casa_ratio"].map(pct), "Pertumbuhan": tbl["growth"].map(pct),
        }), hide_index=True)
        st.download_button("⬇️ Unduh CSV", g.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"simpanan_{period.lower()}_{sel_name.replace(' ', '_')}.csv",
                           mime="text/csv")

    # Perbandingan seluruh perusahaan
    st.divider()
    st.subheader("Perbandingan seluruh perusahaan")
    alld = db.get_deposits()
    if alld.empty:
        return
    ga = total_series(alld, period, by=["company_name"])
    fig = px.line(ga, x="periode", y="total", color="company_name",
                  labels={"periode": "Periode", "total": "Total simpanan (Rp)", "company_name": "Perusahaan"})
    fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig)
    lastrows = ga.sort_values("periode").groupby("company_name").tail(1).sort_values("total", ascending=False)
    st.dataframe(pd.DataFrame({
        "Perusahaan": lastrows["company_name"], "Total simpanan": lastrows["total"].map(rp),
        "CASA ratio": lastrows["casa_ratio"].map(pct), "Pertumbuhan": lastrows["growth"].map(pct),
        "Posisi per": lastrows["periode"].map(lambda t: period_label(t, period)),
    }), hide_index=True)


# --------------------------------------------------------------------------
# Halaman 2: Progres Akuisisi & Performa Ritel
# --------------------------------------------------------------------------
def page_progress():
    st.title("📈 Progres Akuisisi & Performa Ritel")
    st.caption(f"Perusahaan: **{sel_name}**")
    tl = db.get_table("timeline", cid)
    cif = db.get_table("cif_segments", cid)
    dep = db.get_deposits(cid)

    done, n_tl = int((tl["status"] == "Selesai").sum()), len(tl)
    pot = float(cif["potensi_cif"].fillna(0).sum())
    acq = float(cif["cif_terakuisisi"].fillna(0).sum())
    aktif = float(cif["cif_aktif"].fillna(0).sum())

    ret_total, ret_growth = None, None
    if not dep.empty:
        snap = snapshot_by_period(dep, "Bulanan")
        ret = snap[snap["segment"].isin(db.RETAIL_SEGMENTS)].groupby("periode", as_index=False)["total"].sum()
        if not ret.empty:
            ret["growth"] = ret["total"].pct_change() * 100
            ret_total, ret_growth = ret["total"].iloc[-1], ret["growth"].iloc[-1]

    st.markdown(f"**Fase saat ini:** {phase_now(cid)}")
    st.progress(done / n_tl if n_tl else 0.0, text=f"Tahap akuisisi selesai: {done} dari {n_tl}")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Penetrasi CIF ekosistem", pct(acq / pot * 100 if pot else None))
    k2.metric("CIF terakuisisi", num(acq))
    k3.metric("CIF aktif", num(aktif), help="CIF dengan transaksi/saldo aktif")
    k4.metric("Simpanan segmen ritel", rp(ret_total),
              delta=pct(ret_growth) if ret_growth is not None and pd.notna(ret_growth) else None,
              help="Karyawan + Pelanggan, saldo akhir bulan terakhir, delta vs bulan sebelumnya")

    if not dep.empty and ret_total is not None:
        fig = px.line(ret, x="periode", y="total", markers=True,
                      labels={"periode": "Bulan", "total": "Simpanan ritel (Rp)"},
                      title="Tren simpanan segmen ritel (Karyawan + Pelanggan), bulanan")
        st.plotly_chart(fig)

    t_prof, t_prod, t_pot, t_cif = st.tabs(
        ["🏢 Profil Singkat", "📦 Produk Eksisting", "💡 Potensi Bisnis", "🧾 Tabel CIF Ekosistem"])

    with t_prof:
        render_profile()

    with t_prod:
        prod = db.get_table("products_existing", cid)
        n_aktif = int((prod["status"] == "Aktif").sum())
        a, b, c = st.columns(3)
        a.metric("Produk aktif", f"{n_aktif} dari {len(db.PRODUCT_NAMES)}")
        b.metric("Cakupan produk", pct(n_aktif / len(db.PRODUCT_NAMES) * 100))
        c.metric("Total volume/saldo produk", rp(prod["volume"].fillna(0).sum()))
        if prod.empty:
            st.info("Belum ada produk eksisting.")
        else:
            fig = px.bar(prod.sort_values("volume"), x="volume", y="product", color="status",
                         orientation="h", labels={"volume": "Volume/saldo (Rp)", "product": "", "status": "Status"},
                         title="Volume/saldo per produk eksisting")
            st.plotly_chart(fig)
            st.dataframe(pd.DataFrame({
                "Produk": prod["product"], "Kategori": prod["category"], "Status": prod["status"],
                "Volume/saldo": prod["volume"].map(rp), "Catatan": prod["notes"]}), hide_index=True)
        belum = [p for p in db.PRODUCT_NAMES if p not in prod["product"].tolist()]
        if belum:
            st.caption("Belum digunakan (peluang cross-selling): " + ", ".join(belum))
        with st.expander("✏️ Ubah produk eksisting"):
            table_editor("products_existing", cid, "prod", {
                "product": st.column_config.TextColumn("Produk", required=True),
                "category": st.column_config.SelectboxColumn("Kategori", options=db.CATEGORIES),
                "status": st.column_config.SelectboxColumn("Status", options=["Aktif", "Dormant"]),
                "volume": st.column_config.NumberColumn("Volume/saldo (Rp)", min_value=0, format="%.0f"),
                "notes": st.column_config.TextColumn("Catatan"),
            })

    with t_pot:
        pt = db.get_table("business_potential", cid)
        pt["weighted"] = pt["est_value"].fillna(0) * pt["probability"].fillna(0) / 100
        a, b = st.columns(2)
        a.metric("Total potensi", rp(pt["est_value"].fillna(0).sum()))
        b.metric("Potensi terbobot probabilitas", rp(pt["weighted"].sum()))
        if pt.empty:
            st.info("Belum ada data potensi bisnis.")
        else:
            m = pt.melt(id_vars=["source"], value_vars=["est_value", "weighted"], var_name="jenis",
                        value_name="nilai")
            m["jenis"] = m["jenis"].map({"est_value": "Potensi bruto", "weighted": "Terbobot probabilitas"})
            fig = px.bar(m, x="nilai", y="source", color="jenis", barmode="group", orientation="h",
                         labels={"nilai": "Nilai (Rp)", "source": "", "jenis": ""},
                         title="Potensi bisnis per sumber")
            st.plotly_chart(fig)
            st.dataframe(pd.DataFrame({
                "Sumber potensi": pt["source"], "Estimasi nilai": pt["est_value"].map(rp),
                "Probabilitas": pt["probability"].map(lambda v: pct(v, 0)),
                "Terbobot": pt["weighted"].map(rp), "Catatan": pt["notes"]}), hide_index=True)
        with st.expander("✏️ Ubah potensi bisnis"):
            table_editor("business_potential", cid, "pot", {
                "source": st.column_config.TextColumn("Sumber potensi", required=True),
                "est_value": st.column_config.NumberColumn("Estimasi nilai (Rp)", min_value=0, format="%.0f"),
                "probability": st.column_config.NumberColumn("Probabilitas (%)", min_value=0, max_value=100),
                "notes": st.column_config.TextColumn("Catatan"),
            })

    with t_cif:
        c = cif.copy()
        for col in ["potensi_cif", "cif_terakuisisi", "cif_aktif"]:
            c[col] = c[col].fillna(0)
        c["pen"] = c["cif_terakuisisi"] / c["potensi_cif"].where(c["potensi_cif"] > 0) * 100
        c["akt"] = c["cif_aktif"] / c["cif_terakuisisi"].where(c["cif_terakuisisi"] > 0) * 100
        c["gap"] = c["potensi_cif"] - c["cif_terakuisisi"]
        if c.empty:
            st.info("Belum ada data CIF.")
        else:
            if ((c["cif_terakuisisi"] > c["potensi_cif"]) | (c["cif_aktif"] > c["cif_terakuisisi"])).any():
                st.warning("Ada baris dengan CIF terakuisisi > potensi atau CIF aktif > terakuisisi. Periksa datanya.")
            tot = pd.DataFrame({
                "Segmen": ["TOTAL"], "Potensi CIF": [num(c["potensi_cif"].sum())],
                "CIF terakuisisi": [num(c["cif_terakuisisi"].sum())], "CIF aktif": [num(c["cif_aktif"].sum())],
                "Penetrasi": [pct(c["cif_terakuisisi"].sum() / c["potensi_cif"].sum() * 100
                                  if c["potensi_cif"].sum() else None)],
                "Aktivasi": [pct(c["cif_aktif"].sum() / c["cif_terakuisisi"].sum() * 100
                                 if c["cif_terakuisisi"].sum() else None)],
                "Gap CIF": [num(c["gap"].sum())]})
            body = pd.DataFrame({
                "Segmen": c["segment"], "Potensi CIF": c["potensi_cif"].map(num),
                "CIF terakuisisi": c["cif_terakuisisi"].map(num), "CIF aktif": c["cif_aktif"].map(num),
                "Penetrasi": c["pen"].map(pct), "Aktivasi": c["akt"].map(pct), "Gap CIF": c["gap"].map(num)})
            st.dataframe(pd.concat([body, tot], ignore_index=True), hide_index=True)
            fig = px.bar(c, x="segment", y="pen", range_y=[0, 100], text=c["pen"].map(pct),
                         labels={"segment": "Segmen", "pen": "Penetrasi CIF (%)"},
                         title="Penetrasi CIF per segmen ekosistem")
            st.plotly_chart(fig)
            st.caption("Penetrasi = CIF terakuisisi ÷ potensi CIF. Aktivasi = CIF aktif ÷ CIF terakuisisi. "
                       "Tabel ini berisi jumlah agregat, bukan data nasabah per orang.")
        with st.expander("✏️ Ubah tabel CIF ekosistem"):
            table_editor("cif_segments", cid, "cif", {
                "segment": st.column_config.SelectboxColumn("Segmen", options=db.SEGMENTS, required=True),
                "potensi_cif": st.column_config.NumberColumn("Potensi CIF", min_value=0, step=1),
                "cif_terakuisisi": st.column_config.NumberColumn("CIF terakuisisi", min_value=0, step=1),
                "cif_aktif": st.column_config.NumberColumn("CIF aktif", min_value=0, step=1),
            })


# --------------------------------------------------------------------------
# Halaman 3: Fokus Akuisisi
# --------------------------------------------------------------------------
def page_focus():
    st.title("🎯 Fokus Akuisisi")
    st.caption(f"Perusahaan fokus: **{sel_name}**")
    t_prof, t_fx, t_fund, t_pipe = st.tabs(
        ["🏢 Profil Perusahaan", "💱 Transformasi Valas", "💰 Pertumbuhan Dana", "🔀 Pipeline Cross-Selling"])

    with t_prof:
        render_profile()
        cif = db.get_table("cif_segments", cid)
        pot, acq = cif["potensi_cif"].fillna(0).sum(), cif["cif_terakuisisi"].fillna(0).sum()
        pt = db.get_table("business_potential", cid)
        w = (pt["est_value"].fillna(0) * pt["probability"].fillna(0) / 100).sum()
        a, b = st.columns(2)
        a.metric("Penetrasi CIF ekosistem", pct(acq / pot * 100 if pot else None))
        b.metric("Potensi bisnis terbobot", rp(w))

    with t_fx:
        fx = db.get_fx(cid)
        if fx.empty:
            st.info("Belum ada data valas. Isi lewat menu Kelola Data.")
        else:
            view = st.radio("Periode", ["Bulanan", "Tahunan"], horizontal=True, key="fx_view")
            d = fx.copy()
            d["bulan"] = pd.to_datetime(d["month"] + "-01")
            d["periode"] = d["bulan"] if view == "Bulanan" else d["bulan"].dt.to_period("Y").dt.to_timestamp()
            g = d.groupby("periode", as_index=False)[["bri_volume", "other_volume"]].sum()
            g["total"] = g["bri_volume"] + g["other_volume"]
            g["share"] = g["bri_volume"] / g["total"].where(g["total"] > 0) * 100
            first, last = g.iloc[0], g.iloc[-1]

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Pangsa transaksi via BRI", pct(last["share"]),
                      delta=f"{last['share'] - first['share']:+.1f} poin vs awal".replace(".", ",")
                      if pd.notna(last["share"]) and pd.notna(first["share"]) else None)
            k2.metric("Volume via BRI (periode terakhir)", usd(last["bri_volume"]))
            k3.metric("Volume via bank lain", usd(last["other_volume"]))
            k4.metric("Total volume valas", usd(last["total"]))

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=g["periode"], y=g["bri_volume"], name="Via BRI"), secondary_y=False)
            fig.add_trace(go.Bar(x=g["periode"], y=g["other_volume"], name="Via bank lain"), secondary_y=False)
            fig.add_trace(go.Scatter(x=g["periode"], y=g["share"], name="Pangsa BRI (%)", mode="lines+markers"),
                          secondary_y=True)
            fig.update_layout(barmode="stack", hovermode="x unified", title=f"Transformasi valas ({view.lower()})",
                              legend=dict(orientation="h", y=-0.2))
            fig.update_yaxes(title_text="Volume (USD)", secondary_y=False)
            fig.update_yaxes(title_text="Pangsa BRI (%)", range=[0, 100], secondary_y=True)
            st.plotly_chart(fig)

            t = g.sort_values("periode", ascending=False)
            st.dataframe(pd.DataFrame({
                "Periode": t["periode"].map(lambda x: period_label(x, view)),
                "Via BRI": t["bri_volume"].map(usd), "Via bank lain": t["other_volume"].map(usd),
                "Total": t["total"].map(usd), "Pangsa BRI": t["share"].map(pct)}), hide_index=True)
            st.caption("Transformasi valas = pengalihan transaksi valas perusahaan dan ekosistemnya dari bank lain ke BRI.")

    with t_fund:
        dep = db.get_deposits(cid)
        if dep.empty:
            st.info("Belum ada data simpanan.")
        else:
            gm = total_series(dep, "Bulanan")
            gm["yoy"] = gm["total"].pct_change(12) * 100
            last = gm.iloc[-1]
            prev_year = gm[gm["periode"].dt.year == last["periode"].year - 1]
            ytd = (last["total"] / prev_year["total"].iloc[-1] - 1) * 100 if not prev_year.empty else None

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Saldo terakhir", rp(last["total"]),
                      delta=pct(last["growth"]) if pd.notna(last["growth"]) else None, help="Delta = vs bulan lalu")
            k2.metric("Pertumbuhan YoY", pct(last["yoy"]))
            k3.metric("Pertumbuhan YTD", pct(ytd))
            k4.metric("CASA ratio", pct(last["casa_ratio"]))

            fig = px.line(gm, x="periode", y="total", markers=True,
                          labels={"periode": "Bulan", "total": "Total simpanan (Rp)"},
                          title="Pertumbuhan total simpanan (bulanan)")
            st.plotly_chart(fig)
            m = gm.melt(id_vars=["periode"], value_vars=["giro", "tabungan", "deposito"], var_name="jenis",
                        value_name="saldo")
            m["jenis"] = m["jenis"].str.capitalize()
            fig = px.bar(m, x="periode", y="saldo", color="jenis", barmode="stack",
                         labels={"periode": "Bulan", "saldo": "Saldo (Rp)", "jenis": "Jenis"},
                         title="Komposisi simpanan: giro, tabungan, deposito")
            st.plotly_chart(fig)

            t = gm.sort_values("periode", ascending=False).head(24)
            st.dataframe(pd.DataFrame({
                "Bulan": t["periode"].map(lambda x: period_label(x, "Bulanan")), "Total": t["total"].map(rp),
                "MoM": t["growth"].map(pct), "YoY": t["yoy"].map(pct), "CASA ratio": t["casa_ratio"].map(pct)}),
                hide_index=True)

    with t_pipe:
        pl = db.get_table("pipeline", cid)
        pl["bobot"] = pl["stage"].map(db.STAGE_PROB).fillna(0)
        pl["weighted"] = pl["est_value"].fillna(0) * pl["bobot"]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Jumlah peluang", len(pl))
        k2.metric("Total pipeline", rp(pl["est_value"].fillna(0).sum()))
        k3.metric("Pipeline terbobot", rp(pl["weighted"].sum()))
        k4.metric("Closing (Won)", rp(pl.loc[pl["stage"] == "Closing (Won)", "est_value"].fillna(0).sum()))
        if not pl.empty:
            fs = pl.groupby("stage").agg(jumlah=("product", "count"), nilai=("est_value", "sum"))
            fs = fs.reindex(db.STAGES).fillna(0).reset_index()
            fig = px.funnel(fs, x="jumlah", y="stage", labels={"jumlah": "Jumlah peluang", "stage": "Tahap"},
                            title="Funnel pipeline cross-selling")
            st.plotly_chart(fig)
            order = {s: i for i, s in enumerate(db.STAGES)}
            t = pl.assign(_o=pl["stage"].map(order).fillna(-1)).sort_values(["_o", "target_date"], ascending=[False, True])
            st.dataframe(pd.DataFrame({
                "Produk": t["product"], "Tahap": t["stage"], "Estimasi nilai": t["est_value"].map(rp),
                "Probabilitas": (t["bobot"] * 100).map(lambda v: pct(v, 0)), "Terbobot": t["weighted"].map(rp),
                "PIC": t["pic"], "Target": t["target_date"].map(fmt_date)}), hide_index=True)
        else:
            st.info("Belum ada peluang cross-selling.")
        with st.expander("✏️ Ubah pipeline cross-selling"):
            table_editor("pipeline", cid, "pipe", {
                "product": st.column_config.TextColumn("Produk", required=True),
                "stage": st.column_config.SelectboxColumn("Tahap", options=db.STAGES),
                "est_value": st.column_config.NumberColumn("Estimasi nilai (Rp)", min_value=0, format="%.0f"),
                "pic": st.column_config.TextColumn("PIC"),
                "target_date": st.column_config.DateColumn("Target"),
            }, date_cols=["target_date"])


# --------------------------------------------------------------------------
# Halaman 4: Timeline Akuisisi
# --------------------------------------------------------------------------
def page_timeline():
    st.title("🗓️ Timeline Akuisisi")
    st.caption(f"Perusahaan: **{sel_name}**")
    tl = db.get_table("timeline", cid)

    if tl.empty:
        st.info("Belum ada timeline untuk perusahaan ini.")
        start = pd.to_datetime(company["acq_start"], errors="coerce")
        if st.button("Buat timeline standar") and not pd.isna(start):
            db.create_default_timeline(cid, start.date())
            st.rerun()
    else:
        d = tl.copy()
        d["start"] = pd.to_datetime(d["start_date"])
        d["end"] = pd.to_datetime(d["end_date"])
        n, done = len(d), int((d["status"] == "Selesai").sum())
        run = int((d["status"] == "Berjalan").sum())

        k1, k2, k3 = st.columns(3)
        k1.metric("Tahap selesai", f"{done} dari {n}")
        k2.metric("Tahap berjalan", run)
        k3.metric("Fase saat ini", phase_now(cid))
        st.progress(done / n if n else 0.0)

        fig = px.timeline(d, x_start="start", x_end="end", y="title", color="status",
                          color_discrete_map=STATUS_COLORS, hover_data=["pic", "notes"],
                          category_orders={"title": d.sort_values("urutan")["title"].tolist()},
                          labels={"title": "", "status": "Status"})
        fig.update_yaxes(autorange="reversed")
        today = date.today().isoformat()
        fig.add_shape(type="line", x0=today, x1=today, y0=0, y1=1, yref="paper", line=dict(dash="dash", width=2))
        fig.add_annotation(x=today, y=1, yref="paper", text="Hari ini", showarrow=False, yanchor="bottom")
        fig.update_layout(legend=dict(orientation="h", y=-0.15), margin=dict(t=40))
        st.plotly_chart(fig)

        st.dataframe(pd.DataFrame({
            "No": d["urutan"], "Tahap": d["title"], "Mulai": d["start_date"].map(fmt_date),
            "Selesai": d["end_date"].map(fmt_date), "Status": d["status"], "PIC": d["pic"], "Catatan": d["notes"]}),
            hide_index=True)

    with st.expander("✏️ Ubah timeline akuisisi"):
        table_editor("timeline", cid, "tl", {
            "title": st.column_config.TextColumn("Tahap", required=True),
            "urutan": st.column_config.NumberColumn("No", min_value=1, step=1),
            "start_date": st.column_config.DateColumn("Mulai"),
            "end_date": st.column_config.DateColumn("Selesai"),
            "status": st.column_config.SelectboxColumn("Status", options=db.STATUSES),
            "pic": st.column_config.TextColumn("PIC"),
            "notes": st.column_config.TextColumn("Catatan"),
        }, date_cols=["start_date", "end_date"])

    st.divider()
    st.subheader("Ringkasan semua perusahaan")
    rows = []
    for _, r in companies.iterrows():
        t = db.get_table("timeline", int(r["id"]))
        rows.append({"Perusahaan": r["name"], "Mulai akuisisi": fmt_date(r["acq_start"]),
                     "Fase saat ini": phase_now(int(r["id"])),
                     "Tahap selesai": f"{int((t['status'] == 'Selesai').sum())} / {len(t)}"})
    st.dataframe(pd.DataFrame(rows), hide_index=True)


# --------------------------------------------------------------------------
# Halaman 5: Kelola Data
# --------------------------------------------------------------------------
def company_form(key, p=None):
    p = p or {}
    acq = pd.to_datetime(p.get("acq_start"), errors="coerce")
    with st.form(key):
        name = st.text_input("Nama perusahaan *", value=p.get("name", ""))
        c1, c2 = st.columns(2)
        sector = c1.text_input("Sektor", value=p.get("sector") or "")
        city = c2.text_input("Kota", value=p.get("city") or "")
        c3, c4 = st.columns(2)
        founded = c3.number_input("Tahun berdiri", 1800, 2100, value=safe_int(p.get("founded_year"), 2010))
        employees = c4.number_input("Jumlah karyawan", 0, 10_000_000, value=safe_int(p.get("employees"), 0), step=10)
        c5, c6 = st.columns(2)
        revenue = c5.number_input("Omzet tahunan (Rp)", 0.0, value=float(p.get("annual_revenue") or 0),
                                  step=1e9, format="%.0f")
        rm = c6.text_input("Relationship Manager", value=p.get("rm_name") or "")
        start = st.date_input("Tanggal mulai akuisisi", value=date.today() if pd.isna(acq) else acq.date())
        desc = st.text_area("Profil singkat", value=p.get("description") or "")
        ok = st.form_submit_button("Simpan")
    data = dict(name=name.strip(), sector=sector.strip(), city=city.strip(), founded_year=int(founded),
                employees=int(employees), annual_revenue=float(revenue), rm_name=rm.strip(),
                acq_start=start.isoformat(), description=desc.strip())
    return ok, data


def page_manage():
    st.title("🛠️ Kelola Data")
    t_dep, t_fx, t_edit, t_new = st.tabs(
        ["Simpanan mingguan", "Valas bulanan", "Edit perusahaan", "Perusahaan baru / hapus"])

    with t_dep:
        if company is None:
            st.info("Tambahkan perusahaan terlebih dahulu.")
        else:
            st.write(f"Catat saldo simpanan **{sel_name}** per segmen ekosistem (posisi akhir minggu).")
            dep = db.get_deposits(cid)
            last_week = dep["week_start"].max() if not dep.empty else "kosong"
            prev = dep[dep["week_start"] == last_week].set_index("segment") if not dep.empty else None
            init = pd.DataFrame({"Segmen": db.SEGMENTS})
            for col, src in [("Giro", "giro"), ("Tabungan", "tabungan"), ("Deposito", "deposito")]:
                init[col] = [float(prev.loc[s, src]) if prev is not None and s in prev.index else 0.0
                             for s in db.SEGMENTS]
            wk = st.date_input("Tanggal (otomatis disesuaikan ke hari Senin minggu tersebut)", value=date.today())
            edited = st.data_editor(
                init, hide_index=True, disabled=["Segmen"], key=f"dep_{cid}_{last_week}",
                column_config={c: st.column_config.NumberColumn(f"{c} (Rp)", min_value=0, format="%.0f")
                               for c in ["Giro", "Tabungan", "Deposito"]})
            if st.button("💾 Simpan simpanan mingguan"):
                week = db.upsert_deposits(cid, wk, list(zip(edited["Segmen"], edited["Giro"],
                                                            edited["Tabungan"], edited["Deposito"])))
                st.success(f"Data minggu {fmt_date(week)} tersimpan (data minggu yang sama akan ditimpa).")

    with t_fx:
        if company is None:
            st.info("Tambahkan perusahaan terlebih dahulu.")
        else:
            with st.form("fx_form"):
                mth = st.date_input("Bulan (pilih tanggal mana saja pada bulan tersebut)", value=date.today())
                c1, c2 = st.columns(2)
                bri = c1.number_input("Volume valas via BRI (USD)", min_value=0.0, step=100_000.0, format="%.0f")
                oth = c2.number_input("Volume valas via bank lain (USD)", min_value=0.0, step=100_000.0, format="%.0f")
                if st.form_submit_button("Simpan"):
                    m = db.upsert_fx(cid, mth, bri, oth)
                    st.success(f"Data valas {m} tersimpan.")

    with t_edit:
        if company is None:
            st.info("Belum ada perusahaan.")
        else:
            ok, data = company_form(f"edit_company_{cid}", company.to_dict())
            if ok:
                if not data["name"]:
                    st.error("Nama perusahaan wajib diisi.")
                else:
                    try:
                        db.update_company(cid, data)
                    except sqlite3.IntegrityError:
                        st.error("Nama perusahaan sudah dipakai.")
                    else:
                        st.success("Profil diperbarui.")
                        st.rerun()

    with t_new:
        st.subheader("Tambah perusahaan baru")
        ok, data = company_form("new_company")
        if ok:
            if not data["name"]:
                st.error("Nama perusahaan wajib diisi.")
            else:
                try:
                    db.add_company(data)
                except sqlite3.IntegrityError:
                    st.error("Nama perusahaan sudah ada.")
                else:
                    st.success("Perusahaan ditambahkan dengan timeline standar dan tabel CIF awal. "
                               "Pilih di sidebar untuk melengkapi datanya.")
                    st.rerun()
        if company is not None:
            with st.expander("🗑️ Hapus perusahaan terpilih"):
                st.warning(f"Menghapus **{sel_name}** juga menghapus seluruh data simpanan, valas, CIF, "
                           "produk, potensi, pipeline, dan timeline-nya.")
                sure = st.checkbox("Saya paham data akan dihapus permanen.")
                if st.button("Hapus perusahaan", disabled=not sure):
                    db.delete_company(cid)
                    st.rerun()


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------
if company is None and page != "Kelola Data":
    st.warning("Belum ada perusahaan. Tambahkan lewat menu Kelola Data.")
elif page == PAGES[0]:
    page_map()
elif page == PAGES[1]:
    page_progress()
elif page == PAGES[2]:
    page_focus()
elif page == PAGES[3]:
    page_timeline()
else:
    page_manage()

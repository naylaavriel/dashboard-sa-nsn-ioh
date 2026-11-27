import html
import os
import re
from datetime import timedelta
import pandas as pd
import plotly.express as px
import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ==============================================================================
# KONFIGURASI HALAMAN & GOOGLE SHEETS
# ==============================================================================
st.set_page_config(
    page_title="Monitoring SA Tower & SA Ground",
    page_icon="📡",
    layout="wide",
)


def load_css(file_path: str = "style.css"):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css("style.css")

st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif !important;
    }
    .tbl-wrap {
        width: 100%;
        overflow-x: auto;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        background: #ffffff;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }
    table.styled-tbl {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        text-align: left;
    }
    table.styled-tbl thead th {
        background: #f8fafc;
        color: #1B365D;
        font-weight: 700;
        padding: 11px 14px;
        border-bottom: 1px solid #e2e8f0;
        white-space: nowrap;
    }
    table.styled-tbl tbody td {
        padding: 10px 14px;
        border-bottom: 1px solid #f1f5f9;
        color: #1e293b;
        vertical-align: middle;
        white-space: nowrap;
    }
    table.styled-tbl tbody tr:hover {
        background-color: #f8fafc;
    }
    .pill {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 11.5px;
        font-weight: 700;
    }
    .pill-ok {
        background: #dcfce7;
        color: #15803d;
        border: 1px solid #bbf7d0;
    }
    .pill-bad {
        background: #fee2e2;
        color: #b91c1c;
        border: 1px solid #fecaca;
    }
    .pill-warn {
        background: #fef3c7;
        color: #b45309;
        border: 1px solid #fde68a;
    }
    .pill-info {
        background: #e0f2fe;
        color: #005A9C;
        border: 1px solid #bae6fd;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/17I1icQx6YUcUXI6lsmuqJviqnn9HMqYmgCDYuCrrPCg/edit?usp=sharing"
TAB_LOG = "Log_Daily_Activity"
TAB_MASTER = "Master_Validasi_Site"
TAB_ATP = "Log_ATP_History"


# ==============================================================================
# FUNGSI OTENTIKASI & PENARIKAN DATA GOOGLE SHEETS
# ==============================================================================
def get_sheets_service():
    try:
        if "gcp_service_account" in st.secrets:
            sa_info = dict(st.secrets["gcp_service_account"])
            if "private_key" in sa_info and isinstance(sa_info["private_key"], str):
                sa_info["private_key"] = sa_info["private_key"].replace("\\n", "\n")
            creds = service_account.Credentials.from_service_account_info(
                sa_info, scopes=SCOPES
            )
            return build("sheets", "v4", credentials=creds)
    except Exception:
        pass

    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("client_secret.json"):
                raise FileNotFoundError(
                    "Secrets belum dikonfigurasi dan 'client_secret.json' tidak ditemukan di folder project."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                "client_secret.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def extract_spreadsheet_id(url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not match:
        raise ValueError("Format URL Google Sheets tidak valid.")
    return match.group(1)


@st.cache_data(ttl=60, show_spinner=False)
def load_sheet_tab(sheet_url: str, tab_name: str, cache_buster: int = 0) -> pd.DataFrame:
    service = get_sheets_service()
    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab_name}'!A:AZ")
        .execute()
    )
    values = result.get("values", [])
    if len(values) < 4:
        return pd.DataFrame()

    raw_headers = [str(h).strip() for h in values[2]]
    rows = values[4:]

    headers = []
    seen = {}
    for idx, h in enumerate(raw_headers):
        col_name = h if h else f"Col_{idx+1}"
        if col_name in seen:
            seen[col_name] += 1
            col_name = f"{col_name}_{seen[col_name]}"
        else:
            seen[col_name] = 0
        headers.append(col_name)

    normalized_rows = []
    for r in rows:
        if not any(str(cell).strip() for cell in r):
            continue
        padded = r + [""] * (len(headers) - len(r))
        normalized_rows.append(padded[: len(headers)])

    return pd.DataFrame(normalized_rows, columns=headers)


# ==============================================================================
# HELPER NORMALISASI, TANGGAL & BADGE
# ==============================================================================
def normalize_sa_item(val: str) -> str:
    v = str(val).strip().lower()
    if "tower" in v:
        return "SA Tower"
    if "ground" in v:
        return "SA Ground"
    return str(val).strip()


def categorize_final_status(val: str) -> str:
    v = str(val).strip().upper()
    if "HOLD" in v or "REVISION" in v:
        return "HOLD - NEED REVISION"
    if "INCOMPLETE" in v:
        return "INCOMPLETE"
    if "READY" in v:
        return "READY TO SUBMIT ATP"
    return "LAINNYA / KOSONG"


def categorize_audit_verdict(val: str) -> str:
    v = str(val).strip()
    v_upper = v.upper()
    if v_upper == "COMPLIANT":
        return "COMPLIANT"
    if "LEGACY" in v_upper or "PRE-QC" in v_upper:
        return "LEGACY / PRE-QC GATE"
    if "NOT SUBMITTED" in v_upper or not v:
        return "Not Submitted Yet"
    return v


def extract_activity_date(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="datetime64[ns]")
    tgl_s = (
        pd.to_datetime(df["Tgl"], errors="coerce")
        if "Tgl" in df.columns
        else pd.Series(pd.NaT, index=df.index)
    )
    ts_s = (
        pd.to_datetime(df["Timestamp"], errors="coerce")
        if "Timestamp" in df.columns
        else pd.Series(pd.NaT, index=df.index)
    )
    return tgl_s.fillna(ts_s).dt.normalize()


def extract_atp_event_date(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="datetime64[ns]")
    combined = pd.Series(pd.NaT, index=df.index)
    for col in ["Actual_Approved_Nokia", "Actual_Submit_Nokia", "Timestamp"]:
        if col in df.columns:
            combined = combined.fillna(pd.to_datetime(df[col], errors="coerce"))
    return combined.dt.normalize()


def make_badge(val) -> str:
    txt = str(val).strip()
    up = txt.upper()
    esc = html.escape(txt if txt else "-")
    if any(k in up for k in ["OK", "APPROVE", "COMPLIANT", "READY"]):
        return f'<span class="pill pill-ok">{esc}</span>'
    if any(k in up for k in ["REJECT", "HOLD", "REVISI", "ILLEGAL", "VIOLATION"]):
        return f'<span class="pill pill-bad">{esc}</span>'
    if any(k in up for k in ["REVIEW", "SUBMIT", "PROGRESS"]):
        return f'<span class="pill pill-info">{esc}</span>'
    return f'<span class="pill pill-warn">{esc}</span>'


def render_styled_table(df: pd.DataFrame, columns: list[str], badge_cols: set[str] = None, max_rows: int = 15):
    badge_cols = badge_cols or set()
    avail_cols = [c for c in columns if c in df.columns]
    if df.empty or not avail_cols:
        st.info("Tidak ada data untuk ditampilkan pada tabel ini.")
        return

    th_html = "".join(f"<th>{html.escape(c)}</th>" for c in avail_cols)
    tbody_rows = []
    for _, row in df.head(max_rows).iterrows():
        tds = []
        for c in avail_cols:
            raw_val = row.get(c, "-")
            if c in badge_cols:
                tds.append(f"<td>{make_badge(raw_val)}</td>")
            else:
                tds.append(f"<td>{html.escape(str(raw_val) if str(raw_val).strip() else '-')}</td>")
        tbody_rows.append(f"<tr>{''.join(tds)}</tr>")

    st.markdown(
        f"""
        <div class="tbl-wrap">
            <table class="styled-tbl">
                <thead><tr>{th_html}</tr></thead>
                <tbody>{''.join(tbody_rows)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if len(df) > max_rows:
        st.caption(f"Menampilkan {max_rows} dari {len(df)} baris agar halaman tetap ringan.")


# ==============================================================================
# SIDEBAR KONTROL
# ==============================================================================
if "cache_buster" not in st.session_state:
    st.session_state.cache_buster = 0

st.sidebar.header("⚙️ Sumber Data")
sheet_url = st.sidebar.text_input("Link Google Sheets:", value=DEFAULT_SHEET_URL)

if st.sidebar.button("🔄 Refresh Data Sekarang", use_container_width=True):
    st.session_state.cache_buster += 1
    st.rerun()

st.sidebar.caption(f"Sumber Tab:\n- `{TAB_LOG}`\n- `{TAB_MASTER}`\n- `{TAB_ATP}`")


# ==============================================================================
# BANNER & PENARIKAN DATA
# ==============================================================================
st.markdown(
    """
    <div class="top-hero-banner">
        <div class="top-hero-title">Dashboard Review Log Activity PIC PUSAT | NSN - IOH</div>
        <div class="top-hero-subtitle"></div>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    with st.spinner("Mengambil data dari Google Sheets..."):
        df_log_raw = load_sheet_tab(sheet_url.strip(), TAB_LOG, st.session_state.cache_buster)
        df_master_raw = load_sheet_tab(sheet_url.strip(), TAB_MASTER, st.session_state.cache_buster)
        try:
            df_atp_raw = load_sheet_tab(sheet_url.strip(), TAB_ATP, st.session_state.cache_buster)
        except Exception as atp_err:
            st.warning(f"Tab '{TAB_ATP}' belum dapat dimuat: {atp_err}")
            df_atp_raw = pd.DataFrame()
except Exception as e:
    st.error(f"Gagal mengambil data dari Google Sheets: {e}")
    st.stop()


# ==============================================================================
# PEMROSESAN DATA 3 TAB
# ==============================================================================
if df_log_raw.empty:
    df_sa_all = pd.DataFrame()
else:
    required_log_cols = ["Timestamp", "Email_Validator", "Site_ID", "Item_Validasi", "Status_Validasi"]
    missing_log = [c for c in required_log_cols if c not in df_log_raw.columns]
    if missing_log:
        st.error(f"Kolom wajib tidak ditemukan di '{TAB_LOG}': {', '.join(missing_log)}")
        st.stop()

    item_lower = df_log_raw["Item_Validasi"].astype(str).str.strip().str.lower()
    df_sa_all = df_log_raw[item_lower.str.contains("tower|ground", regex=True, na=False)].copy()
    df_sa_all["Item_Kategori"] = df_sa_all["Item_Validasi"].apply(normalize_sa_item)
    df_sa_all["_activity_date"] = extract_activity_date(df_sa_all)
    df_sa_all["_ts"] = pd.to_datetime(df_sa_all["Timestamp"], errors="coerce")

if df_master_raw.empty:
    df_master_clean = pd.DataFrame()
else:
    df_master_clean = df_master_raw.copy()
    df_master_clean["Final_Status_Group"] = (
        df_master_clean["Final_Status"].apply(categorize_final_status)
        if "Final_Status" in df_master_clean.columns
        else "KOLOM TIDAK DITEMUKAN"
    )
    df_master_clean["Audit_Verdict_Group"] = (
        df_master_clean["Audit_Verdict"].apply(categorize_audit_verdict)
        if "Audit_Verdict" in df_master_clean.columns
        else "KOLOM TIDAK DITEMUKAN"
    )

if df_atp_raw.empty:
    df_atp_clean = pd.DataFrame()
else:
    df_atp_clean = df_atp_raw.copy()
    df_atp_clean["_event_date"] = extract_atp_event_date(df_atp_clean)
    df_atp_clean["Event_Type_Clean"] = (
        df_atp_clean["Event_Type"].astype(str).str.strip().str.upper()
        if "Event_Type" in df_atp_clean.columns
        else "UNKNOWN"
    )


# ==============================================================================
# FILTER & PENCARIAN + KALENDER
# ==============================================================================
st.subheader("Filter & Pencarian")
col_f1, col_f2, col_f3 = st.columns([2, 2, 1.3])

with col_f1:
    validator_list = (
        sorted(
            [
                v
                for v in df_sa_all["Email_Validator"].dropna().astype(str).str.strip().unique()
                if v
            ]
        )
        if not df_sa_all.empty
        else []
    )
    selected_validators = st.multiselect(
        "Pilih / Cari Validator:",
        options=validator_list,
        placeholder="Semua Validator...",
    )

with col_f2:
    search_query = st.text_input(
        "Cari System Key atau SMP ID:",
        placeholder="Ketik System Key atau SMP ID...",
    ).strip().lower()

with col_f3:
    selected_items = st.multiselect(
        "Item Validasi:",
        options=["SA Tower", "SA Ground"],
        default=["SA Tower", "SA Ground"],
    )

valid_dates = []
if not df_sa_all.empty and "_activity_date" in df_sa_all.columns:
    valid_dates.extend(df_sa_all["_activity_date"].dropna().dt.date.tolist())
if not df_atp_clean.empty and "_event_date" in df_atp_clean.columns:
    valid_dates.extend(df_atp_clean["_event_date"].dropna().dt.date.tolist())

date_range_selected = None
if valid_dates:
    min_d, max_d = min(valid_dates), max(valid_dates)
    if "date_range" not in st.session_state:
        st.session_state["date_range"] = (min_d, max_d)

    c_cal, c_b1, c_b2, c_b3 = st.columns([2.4, 0.8, 0.8, 0.8], vertical_alignment="bottom")
    with c_cal:
        picked = st.date_input(
            "Rentang Tanggal (Kalender):",
            value=st.session_state["date_range"],
            min_value=min_d,
            max_value=max_d,
            format="DD/MM/YYYY",
        )
        if isinstance(picked, (list, tuple)) and len(picked) == 2:
            date_range_selected = (picked[0], picked[1])
            st.session_state["date_range"] = date_range_selected
        elif isinstance(picked, (list, tuple)) and len(picked) == 1:
            date_range_selected = (picked[0], picked[0])
        else:
            date_range_selected = (picked, picked)

    with c_b1:
        if st.button("7 Hari", use_container_width=True):
            st.session_state["date_range"] = (max(min_d, max_d - timedelta(days=6)), max_d)
            st.rerun()

    with c_b2:
        if st.button("30 Hari", use_container_width=True):
            st.session_state["date_range"] = (max(min_d, max_d - timedelta(days=29)), max_d)
            st.rerun()

    with c_b3:
        if st.button("Semua", use_container_width=True):
            st.session_state["date_range"] = (min_d, max_d)
            st.rerun()

# ==============================================================================
# TERAPKAN FILTER KE 3 DATAFRAME
# ==============================================================================
df_sa_filtered = df_sa_all.copy()
if not df_sa_filtered.empty:
    if date_range_selected:
        s_dt, e_dt = pd.Timestamp(date_range_selected[0]), pd.Timestamp(date_range_selected[1])
        df_sa_filtered = df_sa_filtered[
            df_sa_filtered["_activity_date"].notna()
            & (df_sa_filtered["_activity_date"] >= s_dt)
            & (df_sa_filtered["_activity_date"] <= e_dt)
        ]
    if selected_validators:
        df_sa_filtered = df_sa_filtered[
            df_sa_filtered["Email_Validator"].astype(str).str.strip().isin(selected_validators)
        ]
    if selected_items:
        df_sa_filtered = df_sa_filtered[df_sa_filtered["Item_Kategori"].isin(selected_items)]
    if search_query:
        s_key = (
            df_sa_filtered["System_Key"].astype(str).str.lower()
            if "System_Key" in df_sa_filtered.columns
            else pd.Series("", index=df_sa_filtered.index)
        )
        smp = (
            df_sa_filtered["SMP_ID"].astype(str).str.lower()
            if "SMP_ID" in df_sa_filtered.columns
            else pd.Series("", index=df_sa_filtered.index)
        )
        df_sa_filtered = df_sa_filtered[
            s_key.str.contains(search_query, na=False) | smp.str.contains(search_query, na=False)
        ]

    df_log_view = (
        df_sa_filtered.dropna(subset=["_ts"])
        .sort_values("_ts", ascending=True)
        .drop_duplicates(subset=["Email_Validator", "Site_ID", "Item_Kategori"], keep="last")
        .sort_values("_ts", ascending=False)
        .drop(columns=["_ts", "_activity_date"], errors="ignore")
    )
else:
    df_log_view = pd.DataFrame()

df_master_view = df_master_clean.copy()
if not df_master_view.empty:
    if search_query:
        m_skey = (
            df_master_view["System_Key"].astype(str).str.lower()
            if "System_Key" in df_master_view.columns
            else pd.Series("", index=df_master_view.index)
        )
        m_smp = (
            df_master_view["SMP_ID"].astype(str).str.lower()
            if "SMP_ID" in df_master_view.columns
            else pd.Series("", index=df_master_view.index)
        )
        df_master_view = df_master_view[
            m_skey.str.contains(search_query, na=False) | m_smp.str.contains(search_query, na=False)
        ]
    elif selected_validators and not df_log_view.empty:
        related_keys = set(df_log_view["System_Key"].astype(str).str.strip()) if "System_Key" in df_log_view.columns else set()
        related_smps = set(df_log_view["SMP_ID"].astype(str).str.strip()) if "SMP_ID" in df_log_view.columns else set()
        cond_key = df_master_view["System_Key"].astype(str).str.strip().isin(related_keys) if "System_Key" in df_master_view.columns else False
        cond_smp = df_master_view["SMP_ID"].astype(str).str.strip().isin(related_smps) if "SMP_ID" in df_master_view.columns else False
        df_master_view = df_master_view[cond_key | cond_smp]

df_atp_view = df_atp_clean.copy()
if not df_atp_view.empty:
    if date_range_selected:
        s_dt, e_dt = pd.Timestamp(date_range_selected[0]), pd.Timestamp(date_range_selected[1])
        df_atp_view = df_atp_view[
            df_atp_view["_event_date"].notna()
            & (df_atp_view["_event_date"] >= s_dt)
            & (df_atp_view["_event_date"] <= e_dt)
        ]
    if search_query:
        a_skey = df_atp_view["System_Key"].astype(str).str.lower() if "System_Key" in df_atp_view.columns else pd.Series("", index=df_atp_view.index)
        a_smp = df_atp_view["SMP_ID"].astype(str).str.lower() if "SMP_ID" in df_atp_view.columns else pd.Series("", index=df_atp_view.index)
        df_atp_view = df_atp_view[a_skey.str.contains(search_query, na=False) | a_smp.str.contains(search_query, na=False)]


# ==============================================================================
# GRAFIK RINGKAS DARI 3 SHEET
# ==============================================================================
st.divider()
st.subheader("Ringkasan Grafik")

g1, g2, g3 = st.columns(3)

with g1:
    st.caption("Log per Status Validasi (Log_Daily_Activity)")
    if not df_log_view.empty and "Status_Validasi" in df_log_view.columns:
        s_cnt = df_log_view["Status_Validasi"].value_counts().reset_index()
        s_cnt.columns = ["Status", "Jumlah"]
        fig1 = px.bar(
            s_cnt,
            x="Jumlah",
            y="Status",
            orientation="h",
            color="Status",
            color_discrete_sequence=["#005A9C", "#1B365D", "#16a34a", "#dc2626", "#f59e0b"],
        )
        fig1.update_layout(height=250, showlegend=False, margin=dict(l=5, r=5, t=5, b=5), plot_bgcolor="white")
        st.plotly_chart(fig1, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})
    else:
        st.info("Belum ada data grafik log.")

with g2:
    st.caption("Site per Audit Verdict (Master_Validasi_Site)")
    if not df_master_view.empty and "Audit_Verdict_Group" in df_master_view.columns:
        v_cnt = df_master_view["Audit_Verdict_Group"].value_counts().reset_index()
        v_cnt.columns = ["Verdict", "Jumlah"]
        fig2 = px.bar(
            v_cnt,
            x="Jumlah",
            y="Verdict",
            orientation="h",
            color="Verdict",
            color_discrete_sequence=["#16a34a", "#dc2626", "#64748b", "#005A9C"],
        )
        fig2.update_layout(height=250, showlegend=False, margin=dict(l=5, r=5, t=5, b=5), plot_bgcolor="white")
        st.plotly_chart(fig2, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})
    else:
        st.info("Belum ada data grafik master.")

with g3:
    st.caption("Tren Event ATP per Tanggal (Log_ATP_History)")
    if not df_atp_view.empty and "_event_date" in df_atp_view.columns and "Event_Type" in df_atp_view.columns:
        tr = (
            df_atp_view.dropna(subset=["_event_date"])
            .assign(Tanggal=lambda d: d["_event_date"].dt.strftime("%Y-%m-%d"))
            .groupby(["Tanggal", "Event_Type"], as_index=False)
            .size()
        )
        fig3 = px.line(
            tr,
            x="Tanggal",
            y="size",
            color="Event_Type",
            markers=True,
            color_discrete_sequence=["#16a34a", "#005A9C", "#dc2626", "#f59e0b"],
            labels={"size": "Jumlah"},
        )
        fig3.update_layout(height=250, margin=dict(l=5, r=5, t=5, b=5), plot_bgcolor="white")
        st.plotly_chart(fig3, use_container_width=True, config={"staticPlot": True, "displayModeBar": False})
    else:
        st.info("Belum ada data grafik ATP.")

# ==============================================================================
# TABEL 1: LOG AKTIVITAS TERBARU (BER-STYLE)
# ==============================================================================
st.divider()
st.header("Log Aktivitas Terbaru (SA Tower & SA Ground)")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Record Terbaru", len(df_log_view))
m2.metric("Total Site Unik", df_log_view["Site_ID"].nunique() if not df_log_view.empty else 0)
m3.metric("SA Tower", int((df_log_view["Item_Kategori"] == "SA Tower").sum()) if not df_log_view.empty else 0)
m4.metric("SA Ground", int((df_log_view["Item_Kategori"] == "SA Ground").sum()) if not df_log_view.empty else 0)

render_styled_table(
    df_log_view,
    columns=[
        "Log_ID",
        "Timestamp",
        "Tgl",
        "Email_Validator",
        "Region",
        "System_Key",
        "SMP_ID",
        "Site_ID",
        "Item_Kategori",
        "Item_Validasi",
        "Status_Validasi",
        "Catatan_Revisi",
    ],
    badge_cols={"Item_Kategori", "Status_Validasi"},
)


# ==============================================================================
# TABEL 2: MASTER VALIDASI SITE (BER-STYLE)
# ==============================================================================
st.divider()
st.header("Status Validasi Site & Audit Verdict")

col_fs, col_av = st.columns(2)
with col_fs:
    st.subheader("Final Status (3 Kategori)")
    fs_counts = df_master_view["Final_Status_Group"].value_counts() if not df_master_view.empty else pd.Series(dtype=int)
    f1, f2, f3 = st.columns(3)
    f1.metric("HOLD - NEED REVISION", int(fs_counts.get("HOLD - NEED REVISION", 0)))
    f2.metric("INCOMPLETE (0/10–6/10)", int(fs_counts.get("INCOMPLETE", 0)))
    f3.metric("READY TO SUBMIT ATP", int(fs_counts.get("READY TO SUBMIT ATP", 0)))

with col_av:
    st.subheader("Audit Verdict (3 Kategori)")
    av_counts = df_master_view["Audit_Verdict_Group"].value_counts() if not df_master_view.empty else pd.Series(dtype=int)
    a1, a2, a3 = st.columns(3)
    a1.metric("COMPLIANT", int(av_counts.get("COMPLIANT", 0)))
    a2.metric("LEGACY / PRE-QC GATE", int(av_counts.get("LEGACY / PRE-QC GATE", 0)))
    a3.metric("Not Submitted Yet", int(av_counts.get("Not Submitted Yet", 0)))

cf1, cf2 = st.columns(2)
with cf1:
    filter_fs = st.multiselect(
        "Filter Final Status:",
        options=["HOLD - NEED REVISION", "INCOMPLETE", "READY TO SUBMIT ATP"],
        placeholder="Semua kategori Final Status...",
    )
with cf2:
    filter_av = st.multiselect(
        "Filter Audit Verdict:",
        options=["COMPLIANT", "LEGACY / PRE-QC GATE", "Not Submitted Yet"],
        placeholder="Semua kategori Audit Verdict...",
    )

df_master_table = df_master_view.copy()
if not df_master_table.empty:
    if filter_fs:
        df_master_table = df_master_table[df_master_table["Final_Status_Group"].isin(filter_fs)]
    if filter_av:
        df_master_table = df_master_table[df_master_table["Audit_Verdict_Group"].isin(filter_av)]

render_styled_table(
    df_master_table,
    columns=[
        "Region",
        "Project_Phase",
        "System_Key",
        "SMP_ID",
        "Site_ID",
        "Site_Name",
        "01_Review_SA_Ground",
        "02_Review_SA_Tower",
        "Final_Status_Group",
        "Final_Status",
        "Last_Validator_Email",
        "Audit_Verdict_Group",
    ],
    badge_cols={
        "01_Review_SA_Ground",
        "02_Review_SA_Tower",
        "Final_Status_Group",
        "Final_Status",
        "Audit_Verdict_Group",
    },
)


# ==============================================================================
# TABEL 3: RIWAYAT ATP (LOG_ATP_HISTORY)
# ==============================================================================
st.divider()
st.header(f"Riwayat ATP ({TAB_ATP})")

render_styled_table(
    df_atp_view,
    columns=[
        "Timestamp",
        "System_Key",
        "SMP_ID",
        "Site_ID",
        "Actual_Submit_Nokia",
        "Actual_Approved_Nokia",
        "Status_ATP",
        "Event_Type",
    ],
    badge_cols={"Status_ATP", "Event_Type"},
)

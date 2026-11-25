import os
import re
import html
from datetime import timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
    page_title="NOKIA - IOH QC Gate Dashboard",
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
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }
    .kpi-title {
        font-size: 12px;
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 28px;
        font-weight: 800;
        color: #1B365D;
        line-height: 1.15;
    }
    .kpi-sub {
        font-size: 12px;
        color: #64748b;
        margin-top: 6px;
    }
    .section-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px 18px;
        margin-bottom: 14px;
    }
    .mockup-table-wrap {
        width: 100%;
        overflow-x: auto;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        background: #ffffff;
    }
    table.mockup-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        text-align: left;
    }
    table.mockup-table thead th {
        background: #f8fafc;
        color: #475569;
        font-weight: 700;
        padding: 12px 14px;
        border-bottom: 1px solid #e2e8f0;
        white-space: nowrap;
    }
    table.mockup-table tbody td {
        padding: 11px 14px;
        border-bottom: 1px solid #f1f5f9;
        color: #1e293b;
        vertical-align: middle;
    }
    table.mockup-table tbody tr:hover {
        background-color: #f8fafc;
    }
    .site-id-main {
        font-weight: 700;
        color: #0f172a;
        font-size: 13px;
    }
    .site-name-sub {
        font-size: 11px;
        color: #64748b;
        margin-top: 2px;
    }
    .pill {
        display: inline-block;
        padding: 4px 11px;
        border-radius: 999px;
        font-size: 11.5px;
        font-weight: 700;
        white-space: nowrap;
    }
    .pill-amber { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
    .pill-red   { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
    .pill-green { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
    .pill-blue  { background: #e0e7ff; color: #1d4ed8; border: 1px solid #c7d2fe; }
    .pill-gray  { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
    .reject-hot { color: #dc2626; font-weight: 800; }
    .reject-zero { color: #334155; font-weight: 600; }
    .qc-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
        gap: 10px;
        margin-top: 10px;
    }
    .qc-item-box {
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 10px 12px;
        background: #f8fafc;
    }
    .qc-item-label {
        font-size: 11.5px;
        font-weight: 700;
        color: #334155;
        margin-bottom: 4px;
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
                    "Service account belum dikonfigurasi di Secrets dan 'client_secret.json' tidak ditemukan."
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
# HELPER NORMALISASI & BADGE
# ==============================================================================
def categorize_final_status(val: str) -> str:
    v = str(val).strip().upper()
    if "HOLD" in v or "REVISION" in v:
        return "HOLD - NEED REVISION"
    if "INCOMPLETE" in v or "PROGRESS" in v:
        return "IN PROGRESS"
    if "READY" in v:
        return "READY TO SUBMIT ATP"
    return v if v else "LAINNYA"


def categorize_audit_verdict(val: str) -> str:
    v = str(val).strip()
    v_upper = v.upper()
    if "ILLEGAL" in v_upper or "VIOLATION" in v_upper or "BYPASS" in v_upper:
        return "VIOLATION - ILLEGAL BYPASS"
    if v_upper == "COMPLIANT":
        return "COMPLIANT"
    if "LEGACY" in v_upper or "PRE-QC" in v_upper:
        return "LEGACY / PRE-QC GATE"
    if "NOT SUBMITTED" in v_upper or not v:
        return "Not Submitted Yet"
    return v


def normalize_qc_item_status(val: str) -> str:
    v = str(val).strip().upper()
    if v in ["OK", "APPROVED", "DONE", "PASS", "PASSED", "COMPLETE", "COMPLETED"]:
        return "OK"
    if "REV" in v or "HOLD" in v or "REJECT" in v:
        return "Revisi"
    if v in ["N/A", "NA", "NOT APPLICABLE", "-"]:
        return "N/A"
    return "Open / NY"


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


def pill_final_status(val: str) -> str:
    v = str(val).strip().upper()
    label = html.escape(str(val).strip() or "-")
    if "READY" in v or "COMPLETE" == v:
        cls = "pill-green"
    elif "HOLD" in v or "REV" in v:
        cls = "pill-red"
    else:
        cls = "pill-amber"
    return f'<span class="pill {cls}">{label}</span>'


def pill_audit_verdict(val: str) -> str:
    v = str(val).strip().upper()
    label = html.escape(str(val).strip() or "-")
    if "VIOLATION" in v or "ILLEGAL" in v or "BYPASS" in v:
        cls = "pill-red"
    elif "COMPLIANT" in v:
        cls = "pill-green"
    else:
        cls = "pill-gray"
    return f'<span class="pill {cls}">{label}</span>'


def pill_atp_status(val: str) -> str:
    v = str(val).strip().upper()
    label = html.escape(str(val).strip() or "01. ATP NY Complete")
    if "APPROVED" in v or "04" in v:
        cls = "pill-green"
    elif "REJECT" in v or "02" in v:
        cls = "pill-red"
    elif "REVIEW" in v or "03" in v:
        cls = "pill-blue"
    else:
        cls = "pill-gray"
    return f'<span class="pill {cls}">{label}</span>'


def pill_qc_status(val: str) -> str:
    norm = normalize_qc_item_status(val)
    raw_lbl = html.escape(str(val).strip() or "Open / NY")
    if norm == "OK":
        cls = "pill-green"
    elif norm == "Revisi":
        cls = "pill-red"
    elif norm == "N/A":
        cls = "pill-gray"
    else:
        cls = "pill-amber"
    return f'<span class="pill {cls}">{raw_lbl}</span>'


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
# BANNER HEADER & MODE SWITCHER
# ==============================================================================
st.markdown(
    """
    <div class="top-hero-banner">
        <div class="top-hero-title">Dashboard Review Log Activity PIC PUSAT | NSN - IOH</div>
        <div class="top-hero-subtitle">NOKIA - IOH QC Gate & Daily Validator Monitoring</div>
    </div>
    """,
    unsafe_allow_html=True,
)

mode_view = st.radio(
    "Pilih Tampilan Dashboard:",
    options=["Executive & Audit Gate", "Operational & Tren ATP"],
    horizontal=True,
    label_visibility="collapsed",
)


# ==============================================================================
# PENARIKAN DATA DARI 3 TAB SHEETS
# ==============================================================================
try:
    with st.spinner("Mengambil data dari Google Sheets..."):
        df_log_raw = load_sheet_tab(sheet_url.strip(), TAB_LOG, st.session_state.cache_buster)
        df_master_raw = load_sheet_tab(sheet_url.strip(), TAB_MASTER, st.session_state.cache_buster)
        try:
            df_atp_raw = load_sheet_tab(sheet_url.strip(), TAB_ATP, st.session_state.cache_buster)
        except Exception:
            df_atp_raw = pd.DataFrame()
except Exception as e:
    st.error(f"Gagal mengambil data dari Google Sheets: {e}")
    st.stop()


# ==============================================================================
# PROSES & NORMALISASI DATA
# ==============================================================================
df_log = df_log_raw.copy()
if not df_log.empty:
    df_log["_activity_date"] = extract_activity_date(df_log)
    df_log["_ts"] = pd.to_datetime(df_log.get("Timestamp", pd.Series(dtype=str)), errors="coerce")

df_master = df_master_raw.copy()
if not df_master.empty:
    df_master["Final_Status_Group"] = (
        df_master["Final_Status"].apply(categorize_final_status)
        if "Final_Status" in df_master.columns
        else "IN PROGRESS"
    )
    df_master["Audit_Verdict_Group"] = (
        df_master["Audit_Verdict"].apply(categorize_audit_verdict)
        if "Audit_Verdict" in df_master.columns
        else "Not Submitted Yet"
    )

df_atp = df_atp_raw.copy()
if not df_atp.empty:
    df_atp["_event_date"] = extract_atp_event_date(df_atp)
    df_atp["Event_Type_Clean"] = (
        df_atp["Event_Type"].astype(str).str.strip().str.upper()
        if "Event_Type" in df_atp.columns
        else "UNKNOWN"
    )

# Gabungkan info ATP terbaru & jumlah Reject ke Master_Validasi_Site jika kolom belum ada di Master
if not df_master.empty and "System_Key" in df_master.columns:
    if not df_atp.empty and "System_Key" in df_atp.columns:
        atp_sorted = df_atp.sort_values("_event_date", ascending=True)
        latest_atp = (
            atp_sorted.drop_duplicates(subset=["System_Key"], keep="last")
            .set_index("System_Key")
        )
        reject_counts = (
            df_atp[df_atp["Event_Type_Clean"].str.contains("REJECT", na=False)]
            .groupby("System_Key")
            .size()
        )
        if "Status_ATP" not in df_master.columns:
            df_master["Status_ATP"] = (
                df_master["System_Key"].map(latest_atp["Status_ATP"]).fillna("01. ATP NY Complete")
                if "Status_ATP" in latest_atp.columns
                else "01. ATP NY Complete"
            )
        if "Reject_Count" not in df_master.columns:
            df_master["Reject_Count"] = (
                df_master["System_Key"].map(reject_counts).fillna(0).astype(int)
            )
    else:
        if "Status_ATP" not in df_master.columns:
            df_master["Status_ATP"] = "01. ATP NY Complete"
        if "Reject_Count" not in df_master.columns:
            df_master["Reject_Count"] = 0

    # Hitung Aksi SA Pertama dari Log_Daily_Activity jika belum ada di Master
    if not df_log.empty and "System_Key" in df_log.columns and "_activity_date" in df_log.columns:
        sa_logs = df_log[
            df_log["Item_Validasi"].astype(str).str.lower().str.contains("sa ", na=False)
        ] if "Item_Validasi" in df_log.columns else df_log
        first_sa = sa_logs.groupby("System_Key")["_activity_date"].min()
        df_master["Aksi_SA_Pertama"] = df_master["System_Key"].map(first_sa)
    else:
        df_master["Aksi_SA_Pertama"] = pd.NaT


# ==============================================================================
# GLOBAL FILTER BAR (REGION + VALIDATOR + KALENDER + PRESET + PENCARIAN)
# ==============================================================================
regions_avail = sorted(
    set(
        (df_master["Region"].dropna().astype(str).str.strip().tolist() if "Region" in df_master.columns else [])
        + (df_log["Region"].dropna().astype(str).str.strip().tolist() if "Region" in df_log.columns else [])
    )
    - {""}
)
validators_avail = sorted(
    set(
        (df_log["Email_Validator"].dropna().astype(str).str.strip().tolist() if "Email_Validator" in df_log.columns else [])
        + (df_master["Last_Validator_Email"].dropna().astype(str).str.strip().tolist() if "Last_Validator_Email" in df_master.columns else [])
    )
    - {""}
)

all_dates = []
if not df_log.empty and "_activity_date" in df_log.columns:
    all_dates.extend(df_log["_activity_date"].dropna().dt.date.tolist())
if not df_atp.empty and "_event_date" in df_atp.columns:
    all_dates.extend(df_atp["_event_date"].dropna().dt.date.tolist())

gf1, gf2, gf3, gf4 = st.columns([1.4, 1.8, 2.2, 1.8])

with gf1:
    sel_regions = st.multiselect("Region:", options=regions_avail, placeholder="Semua Region")

with gf2:
    sel_validators = st.multiselect("PIC Validator:", options=validators_avail, placeholder="Semua Validator")

date_range = None
with gf3:
    if all_dates:
        min_d, max_d = min(all_dates), max(all_dates)
        if "date_range" not in st.session_state:
            st.session_state["date_range"] = (min_d, max_d)
        picked = st.date_input(
            "Rentang Tanggal (Kalender):",
            value=st.session_state["date_range"],
            min_value=min_d,
            max_value=max_d,
            format="DD/MM/YYYY",
        )
        if isinstance(picked, (list, tuple)) and len(picked) == 2:
            date_range = (picked[0], picked[1])
            st.session_state["date_range"] = date_range
        elif isinstance(picked, (list, tuple)) and len(picked) == 1:
            date_range = (picked[0], picked[0])
        else:
            date_range = (picked, picked)

with gf4:
    st.write("")
    if all_dates:
        b1, b2, b3, b4 = st.columns(4)
        if b1.button("7H", use_container_width=True):
            st.session_state["date_range"] = (max(min_d, max_d - timedelta(days=6)), max_d)
            st.rerun()
        if b2.button("30H", use_container_width=True):
            st.session_state["date_range"] = (max(min_d, max_d - timedelta(days=29)), max_d)
            st.rerun()
        if b3.button("Hari Ini", use_container_width=True):
            st.session_state["date_range"] = (max_d, max_d)
            st.rerun()
        if b4.button("Semua", use_container_width=True):
            st.session_state["date_range"] = (min_d, max_d)
            st.rerun()


# ==============================================================================
# TERAPKAN FILTER KE DATAFRAME
# ==============================================================================
df_log_f = df_log.copy()
if not df_log_f.empty:
    if date_range:
        s_dt, e_dt = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
        df_log_f = df_log_f[
            df_log_f["_activity_date"].notna()
            & (df_log_f["_activity_date"] >= s_dt)
            & (df_log_f["_activity_date"] <= e_dt)
        ]
    if sel_regions and "Region" in df_log_f.columns:
        df_log_f = df_log_f[df_log_f["Region"].astype(str).str.strip().isin(sel_regions)]
    if sel_validators and "Email_Validator" in df_log_f.columns:
        df_log_f = df_log_f[df_log_f["Email_Validator"].astype(str).str.strip().isin(sel_validators)]

df_atp_f = df_atp.copy()
if not df_atp_f.empty and date_range:
    s_dt, e_dt = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    df_atp_f = df_atp_f[
        df_atp_f["_event_date"].notna()
        & (df_atp_f["_event_date"] >= s_dt)
        & (df_atp_f["_event_date"] <= e_dt)
    ]

df_master_f = df_master.copy()
if not df_master_f.empty:
    if sel_regions and "Region" in df_master_f.columns:
        df_master_f = df_master_f[df_master_f["Region"].astype(str).str.strip().isin(sel_regions)]
    if sel_validators:
        cond_last = (
            df_master_f["Last_Validator_Email"].astype(str).str.strip().isin(sel_validators)
            if "Last_Validator_Email" in df_master_f.columns
            else pd.Series(False, index=df_master_f.index)
        )
        related_keys = (
            set(df_log_f["System_Key"].astype(str).str.strip())
            if not df_log_f.empty and "System_Key" in df_log_f.columns
            else set()
        )
        cond_log = (
            df_master_f["System_Key"].astype(str).str.strip().isin(related_keys)
            if "System_Key" in df_master_f.columns
            else pd.Series(False, index=df_master_f.index)
        )
        df_master_f = df_master_f[cond_last | cond_log]

# Terapkan filter region/validator ke df_atp_f lewat System_Key Master
if not df_atp_f.empty and not df_master_f.empty and "System_Key" in df_atp_f.columns and "System_Key" in df_master_f.columns:
    if sel_regions or sel_validators:
        valid_keys = set(df_master_f["System_Key"].astype(str).str.strip())
        df_atp_f = df_atp_f[df_atp_f["System_Key"].astype(str).str.strip().isin(valid_keys)]


# ==============================================================================
# KPI CARDS UTAMA (4 KARTU SEPERTI MOCKUP)
# ==============================================================================
total_scope = len(df_master_f)
ready_not_sub = int(
    (
        (df_master_f["Final_Status_Group"] == "READY TO SUBMIT ATP")
        & (~df_master_f["Status_ATP"].astype(str).str.upper().str.contains("APPROVED|REVIEW", na=False))
    ).sum()
) if not df_master_f.empty else 0

atp_approved_cnt = int(
    df_master_f["Status_ATP"].astype(str).str.upper().str.contains("APPROVED|04", na=False).sum()
) if not df_master_f.empty else 0
atp_submitted_cnt = int(
    df_master_f["Status_ATP"].astype(str).str.upper().str.contains("APPROVED|REVIEW|REJECT|02|03|04", na=False).sum()
) if not df_master_f.empty else 0
approval_rate = round((atp_approved_cnt / atp_submitted_cnt) * 100, 1) if atp_submitted_cnt > 0 else 0.0

illegal_bypass_cnt = int(
    (df_master_f["Audit_Verdict_Group"] == "VIOLATION - ILLEGAL BYPASS").sum()
) if not df_master_f.empty else 0

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        f"""<div class="kpi-card">
            <div class="kpi-title">Total Active Scope</div>
            <div class="kpi-value">{total_scope}</div>
            <div class="kpi-sub">Site terdaftar di Master Validasi</div>
        </div>""",
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        f"""<div class="kpi-card">
            <div class="kpi-title">Ready QC – Belum Submit ATP</div>
            <div class="kpi-value" style="color:#005A9C;">{ready_not_sub}</div>
            <div class="kpi-sub">Siap submit ke Nokia ATP</div>
        </div>""",
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        f"""<div class="kpi-card">
            <div class="kpi-title">ATP Approval Rate</div>
            <div class="kpi-value" style="color:#15803d;">{approval_rate}%</div>
            <div class="kpi-sub">{atp_approved_cnt} approved dari {atp_submitted_cnt} submitted</div>
        </div>""",
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        f"""<div class="kpi-card">
            <div class="kpi-title">Violation – Illegal Bypass</div>
            <div class="kpi-value" style="color:#b91c1c;">{illegal_bypass_cnt}</div>
            <div class="kpi-sub">Submit ATP sebelum QC gate lengkap</div>
        </div>""",
        unsafe_allow_html=True,
    )

st.write("")


# ==============================================================================
# MODE 1: EXECUTIVE & AUDIT GATE
# ==============================================================================
if mode_view == "Executive & Audit Gate":
    c_chart1, c_chart2 = st.columns(2)

    # --- GRAFIK 1: AUDIT VERDICT PER REGION ---
    with c_chart1:
        st.markdown("#### Audit Verdict per Region")
        if not df_master_f.empty and "Region" in df_master_f.columns:
            df_reg = (
                df_master_f.assign(Region=df_master_f["Region"].replace("", "Unknown"))
                .groupby(["Region", "Audit_Verdict_Group"], as_index=False)
                .size()
            )
            color_map_av = {
                "COMPLIANT": "#16a34a",
                "VIOLATION - ILLEGAL BYPASS": "#dc2626",
                "LEGACY / PRE-QC GATE": "#64748b",
                "Not Submitted Yet": "#cbd5e1",
            }
            fig_av = px.bar(
                df_reg,
                x="size",
                y="Region",
                color="Audit_Verdict_Group",
                orientation="h",
                barmode="stack",
                color_discrete_map=color_map_av,
                labels={"size": "Jumlah Site", "Region": "", "Audit_Verdict_Group": "Verdict"},
            )
            fig_av.update_layout(
                height=340,
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                plot_bgcolor="white",
            )
            st.plotly_chart(fig_av, use_container_width=True)
        else:
            st.info("Data Region belum tersedia.")

    # --- GRAFIK 2: BOTTLENECK 10 ITEM VALIDASI QC ---
    with c_chart2:
        st.markdown("#### Bottleneck Item Validasi QC")
        qc_cols = [
            c
            for c in df_master_f.columns
            if re.match(r"^(0[1-9]|10)[_\s\.]", str(c).strip())
        ]
        if not df_master_f.empty and qc_cols:
            records_qc = []
            for col in qc_cols:
                clean_label = col.replace("_", " ")
                statuses = df_master_f[col].apply(normalize_qc_item_status).value_counts()
                for st_name, cnt in statuses.items():
                    records_qc.append({"Item": clean_label, "Status": st_name, "Jumlah": int(cnt)})
            df_qc_chart = pd.DataFrame(records_qc)
            fig_qc = px.bar(
                df_qc_chart,
                x="Jumlah",
                y="Item",
                color="Status",
                orientation="h",
                barmode="stack",
                color_discrete_map={
                    "OK": "#16a34a",
                    "Revisi": "#dc2626",
                    "Open / NY": "#f59e0b",
                    "N/A": "#94a3b8",
                },
                labels={"Jumlah": "Jumlah Site", "Item": ""},
            )
            fig_qc.update_layout(
                height=340,
                margin=dict(l=10, r=10, t=10, b=10),
                yaxis=dict(autorange="reversed"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                plot_bgcolor="white",
            )
            st.plotly_chart(fig_qc, use_container_width=True)
        else:
            st.info("Kolom item validasi (01_... s/d 10_...) belum terdeteksi di Master Validasi.")

    # --- BARIS GRAFIK BAWAH: DISTRIBUSI STATUS ATP & REPEAT REJECTION ---
    c_sub1, c_sub2 = st.columns(2)
    with c_sub1:
        st.markdown("#### Distribusi Status ATP")
        if not df_master_f.empty and "Status_ATP" in df_master_f.columns:
            atp_dist = (
                df_master_f["Status_ATP"]
                .replace("", "01. ATP NY Complete")
                .value_counts()
                .reset_index()
            )
            atp_dist.columns = ["Status_ATP", "Jumlah"]
            fig_atp_dist = px.bar(
                atp_dist,
                x="Jumlah",
                y="Status_ATP",
                orientation="h",
                text="Jumlah",
                color="Status_ATP",
                color_discrete_sequence=["#005A9C", "#16a34a", "#f59e0b", "#dc2626", "#64748b"],
            )
            fig_atp_dist.update_layout(
                height=260,
                showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10),
                plot_bgcolor="white",
                yaxis_title="",
                xaxis_title="Jumlah Site",
            )
            st.plotly_chart(fig_atp_dist, use_container_width=True)

    with c_sub2:
        st.markdown("#### Distribusi Repeat Rejection")
        if not df_master_f.empty and "Reject_Count" in df_master_f.columns:
            def bucket_rej(x):
                if x == 0:
                    return "0x (Clean)"
                if x == 1:
                    return "1x Reject"
                if x == 2:
                    return "2x Reject"
                return ">= 3x Reject"

            rej_dist = (
                df_master_f["Reject_Count"].apply(bucket_rej).value_counts().reset_index()
            )
            rej_dist.columns = ["Kategori", "Jumlah"]
            fig_rej = px.bar(
                rej_dist,
                x="Kategori",
                y="Jumlah",
                text="Jumlah",
                color="Kategori",
                color_discrete_map={
                    "0x (Clean)": "#16a34a",
                    "1x Reject": "#f59e0b",
                    "2x Reject": "#ea580c",
                    ">= 3x Reject": "#dc2626",
                },
            )
            fig_rej.update_layout(
                height=260,
                showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10),
                plot_bgcolor="white",
                xaxis_title="",
                yaxis_title="Jumlah Site",
            )
            st.plotly_chart(fig_rej, use_container_width=True)

    # ==========================================================================
    # WATCHLIST PRIORITAS TINDAKAN (TABEL GAYA MOCKUP + BADGE WARNA-WARNI)
    # ==========================================================================
    st.divider()
    st.markdown("### Watchlist Prioritas Tindakan (Briefing Pagi)")

    wf1, wf2, wf3 = st.columns([1.8, 2.2, 1])
    with wf1:
        watchlist_mode = st.selectbox(
            "Filter Prioritas:",
            options=["Semua Site", "Illegal Bypass", "Repeat Reject (>=1x)", "Hold - Need Revision"],
        )
    with wf2:
        search_site = st.text_input(
            "Cari Site ID / System Key / SMP ID / PIC:",
            placeholder="Ketik kata kunci pencarian...",
        ).strip().lower()

    df_watch = df_master_f.copy()
    if not df_watch.empty:
        if watchlist_mode == "Illegal Bypass":
            df_watch = df_watch[df_watch["Audit_Verdict_Group"] == "VIOLATION - ILLEGAL BYPASS"]
        elif watchlist_mode == "Repeat Reject (>=1x)":
            df_watch = df_watch[df_watch["Reject_Count"] >= 1]
        elif watchlist_mode == "Hold - Need Revision":
            df_watch = df_watch[df_watch["Final_Status_Group"] == "HOLD - NEED REVISION"]

        if search_site:
            cols_search = [
                c
                for c in ["Site_ID", "Site_Name", "System_Key", "SMP_ID", "Last_Validator_Email", "Region"]
                if c in df_watch.columns
            ]
            mask = pd.Series(False, index=df_watch.index)
            for c in cols_search:
                mask = mask | df_watch[c].astype(str).str.lower().str.contains(search_site, na=False)
            df_watch = df_watch[mask]

    with wf3:
        st.write("")
        csv_data = df_watch.drop(columns=["Aksi_SA_Pertama"], errors="ignore").to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Export CSV",
            data=csv_data,
            file_name="watchlist_qc_gate.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.caption(f"Menampilkan **{len(df_watch)}** site.")

    if df_watch.empty:
        st.info("Tidak ada site yang cocok dengan filter watchlist saat ini.")
    else:
        rows_html = []
        for _, r in df_watch.head(100).iterrows():
            site_id = html.escape(str(r.get("Site_ID", "-")))
            site_name = html.escape(str(r.get("Site_Name", "")))
            sys_key = html.escape(str(r.get("System_Key", "-")))
            smp_id = html.escape(str(r.get("SMP_ID", "-")))
            region = html.escape(str(r.get("Region", "-")))

            sa_dt = r.get("Aksi_SA_Pertama", pd.NaT)
            sa_str = sa_dt.strftime("%d %b %Y") if pd.notna(sa_dt) else "-"

            fs_html = pill_final_status(r.get("Final_Status_Group", r.get("Final_Status", "-")))
            av_html = pill_audit_verdict(r.get("Audit_Verdict_Group", r.get("Audit_Verdict", "-")))
            atp_html = pill_atp_status(r.get("Status_ATP", "01. ATP NY Complete"))

            rej_val = int(r.get("Reject_Count", 0))
            rej_cls = "reject-hot" if rej_val > 0 else "reject-zero"
            rej_html = f'<span class="{rej_cls}">{rej_val}x</span>'

            val_email = str(r.get("Last_Validator_Email", "-")).strip()
            val_display = html.escape(val_email.split("@")[0].replace(".", " ").title() if "@" in val_email else (val_email or "-"))

            rows_html.append(
                f"""<tr>
                    <td>
                        <div class="site-id-main">{site_id}</div>
                        <div class="site-name-sub">{site_name}</div>
                    </td>
                    <td>{sys_key}</td>
                    <td>{smp_id}</td>
                    <td>{region}</td>
                    <td>{sa_str}</td>
                    <td>{fs_html}</td>
                    <td>{av_html}</td>
                    <td>{atp_html}</td>
                    <td>{rej_html}</td>
                    <td>{val_display}</td>
                </tr>"""
            )

        table_html = f"""
        <div class="mockup-table-wrap">
            <table class="mockup-table">
                <thead>
                    <tr>
                        <th>Site ID / Nama</th>
                        <th>System_Key</th>
                        <th>SMP_ID</th>
                        <th>Region</th>
                        <th>Aksi SA Pertama</th>
                        <th>Final Status</th>
                        <th>Audit Verdict</th>
                        <th>Status ATP</th>
                        <th>Reject</th>
                        <th>Validator Terakhir</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows_html)}
                </tbody>
            </table>
        </div>
        """
        st.markdown(table_html, unsafe_allow_html=True)
        if len(df_watch) > 100:
            st.caption("Menampilkan 100 baris pertama agar halaman tetap ringan. Gunakan pencarian/filter atau Export CSV untuk melihat seluruh data.")

        # ======================================================================
        # PANEL DETAIL SITE (PENGGANTI MODAL POP-UP SAAT SITE DIPILIH)
        # ======================================================================
        st.write("")
        with st.expander("🔍 Lihat Detail 10 Item Validasi QC & Riwayat Log per Site", expanded=False):
            site_options = (
                df_watch["System_Key"].astype(str)
                + " | "
                + df_watch["Site_ID"].astype(str)
                + " ("
                + df_watch.get("Site_Name", pd.Series("", index=df_watch.index)).astype(str)
                + ")"
            ).tolist()
            selected_label = st.selectbox("Pilih Site untuk Inspeksi Detail:", options=site_options)
            sel_sys_key = selected_label.split(" | ")[0].strip()
            site_row = df_watch[df_watch["System_Key"].astype(str).str.strip() == sel_sys_key].iloc[0]

            st.markdown("**Status 10 Item Validasi QC:**")
            qc_cols_detail = [
                c for c in df_watch.columns if re.match(r"^(0[1-9]|10)[_\s\.]", str(c).strip())
            ]
            if qc_cols_detail:
                boxes = []
                for c in qc_cols_detail:
                    lbl = html.escape(c.replace("_", " "))
                    badge = pill_qc_status(site_row.get(c, ""))
                    boxes.append(
                        f'<div class="qc-item-box"><div class="qc-item-label">{lbl}</div>{badge}</div>'
                    )
                st.markdown(f'<div class="qc-grid">{"".join(boxes)}</div>', unsafe_allow_html=True)

            st.write("")
            st.markdown("**Riwayat Log Daily Activity Site Ini:**")
            if not df_log.empty and "System_Key" in df_log.columns:
                site_logs = df_log[df_log["System_Key"].astype(str).str.strip() == sel_sys_key].copy()
                if site_logs.empty:
                    st.info("Belum ada riwayat log aktivitas untuk site ini.")
                else:
                    cols_l = [
                        c
                        for c in [
                            "Timestamp",
                            "Email_Validator",
                            "Item_Validasi",
                            "Status_Validasi",
                            "Catatan_Revisi",
                        ]
                        if c in site_logs.columns
                    ]
                    st.dataframe(site_logs[cols_l], use_container_width=True, hide_index=True)


# ==============================================================================
# MODE 2: OPERATIONAL & TREN ATP
# ==============================================================================
else:
    op1, op2 = st.columns(2)

    # --- GRAFIK TREN HARIAN EVENT ATP ---
    with op1:
        st.markdown("#### Tren Harian Event ATP")
        if not df_atp_f.empty and "_event_date" in df_atp_f.columns:
            trend = (
                df_atp_f.dropna(subset=["_event_date"])
                .assign(Tanggal=lambda d: d["_event_date"].dt.strftime("%Y-%m-%d"))
                .groupby(["Tanggal", "Event_Type_Clean"], as_index=False)
                .size()
            )
            fig_trend = px.line(
                trend,
                x="Tanggal",
                y="size",
                color="Event_Type_Clean",
                markers=True,
                color_discrete_map={
                    "APPROVED": "#16a34a",
                    "SUBMITTED": "#005A9C",
                    "REJECT": "#dc2626",
                    "REJECTED": "#dc2626",
                },
                labels={"size": "Jumlah Site", "Tanggal": "", "Event_Type_Clean": "Event"},
            )
            fig_trend.update_layout(
                height=320,
                margin=dict(l=10, r=10, t=10, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                plot_bgcolor="white",
            )
            st.plotly_chart(fig_trend, use_container_width=True)
        else:
            st.info("Tidak ada data event ATP pada rentang tanggal terpilih.")

    # --- GRAFIK PRODUKTIVITAS VALIDATOR PUSAT ---
    with op2:
        st.markdown("#### Produktivitas Validator Pusat")
        if not df_log_f.empty and "Email_Validator" in df_log_f.columns:
            df_prod = df_log_f.copy()
            df_prod["Validator"] = df_prod["Email_Validator"].apply(
                lambda x: str(x).split("@")[0].replace(".", " ").title() if "@" in str(x) else str(x)
            )
            df_prod["Hasil"] = df_prod["Status_Validasi"].apply(normalize_qc_item_status)
            prod_grp = (
                df_prod[df_prod["Hasil"].isin(["OK", "Revisi"])]
                .groupby(["Validator", "Hasil"], as_index=False)
                .size()
            )
            if not prod_grp.empty:
                fig_prod = px.bar(
                    prod_grp,
                    x="size",
                    y="Validator",
                    color="Hasil",
                    orientation="h",
                    barmode="stack",
                    color_discrete_map={"OK": "#16a34a", "Revisi": "#dc2626"},
                    labels={"size": "Jumlah Review", "Validator": ""},
                )
                fig_prod.update_layout(
                    height=320,
                    margin=dict(l=10, r=10, t=10, b=10),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                    plot_bgcolor="white",
                )
                st.plotly_chart(fig_prod, use_container_width=True)
            else:
                st.info("Belum ada data status OK / Revisi pada rentang tanggal ini.")
        else:
            st.info("Data aktivitas validator belum tersedia.")

    # --- AKTIVITAS VALIDATOR PER HARI ---
    st.divider()
    st.markdown("### Aktivitas Validator per Hari")
    if not df_log.empty and "_activity_date" in df_log.columns and df_log["_activity_date"].notna().any():
        avail_days = sorted(df_log["_activity_date"].dropna().dt.date.unique())
        da1, da2, da3 = st.columns([1.5, 2, 1])
        with da1:
            sel_day = st.date_input(
                "Pilih Tanggal Aktivitas:",
                value=avail_days[-1],
                min_value=avail_days[0],
                max_value=avail_days[-1],
                format="DD/MM/YYYY",
            )
        items_avail = sorted(df_log["Item_Validasi"].dropna().astype(str).unique().tolist()) if "Item_Validasi" in df_log.columns else []
        with da2:
            sel_item_op = st.multiselect("Filter Item Validasi:", options=items_avail, placeholder="Semua Item")

        df_day = df_log[df_log["_activity_date"] == pd.Timestamp(sel_day)].copy()
        if sel_regions and "Region" in df_day.columns:
            df_day = df_day[df_day["Region"].astype(str).str.strip().isin(sel_regions)]
        if sel_validators and "Email_Validator" in df_day.columns:
            df_day = df_day[df_day["Email_Validator"].astype(str).str.strip().isin(sel_validators)]
        if sel_item_op and "Item_Validasi" in df_day.columns:
            df_day = df_day[df_day["Item_Validasi"].isin(sel_item_op)]

        with da3:
            st.write("")
            st.download_button(
                "⬇️ Export Log Harian",
                data=df_day.drop(columns=["_activity_date", "_ts"], errors="ignore").to_csv(index=False).encode("utf-8"),
                file_name=f"log_validator_{sel_day}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        if df_day.empty:
            st.info(f"Tidak ada aktivitas validator tercatat pada {sel_day.strftime('%d/%m/%Y')}.")
        else:
            display_day_cols = [
                c
                for c in [
                    "Timestamp",
                    "Email_Validator",
                    "Region",
                    "Site_ID",
                    "System_Key",
                    "SMP_ID",
                    "Item_Validasi",
                    "Status_Validasi",
                    "Catatan_Revisi",
                ]
                if c in df_day.columns
            ]
            st.dataframe(df_day[display_day_cols], use_container_width=True, hide_index=True)

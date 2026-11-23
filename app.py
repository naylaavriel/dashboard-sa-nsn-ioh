import os
import re
import pandas as pd
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
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">',
    unsafe_allow_html=True,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/17I1icQx6YUcUXI6lsmuqJviqnn9HMqYmgCDYuCrrPCg/edit?usp=sharing"
TAB_LOG = "Log_Daily_Activity"
TAB_MASTER = "Master_Validasi_Site"


# ==============================================================================
# FUNGSI OTENTIKASI & PENARIKAN DATA GOOGLE SHEETS
# ==============================================================================
def get_sheets_service():
    # 1. Prioritaskan Service Account dari Streamlit Secrets (untuk Cloud / deployment)
    if "gcp_service_account" in st.secrets:
        sa_info = dict(st.secrets["gcp_service_account"])
        if "private_key" in sa_info and isinstance(sa_info["private_key"], str):
            sa_info["private_key"] = sa_info["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=SCOPES
        )
        return build("sheets", "v4", credentials=creds)

    # 2. Fallback ke OAuth lokal jika dijalankan di komputer lokal tanpa st.secrets
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("client_secret.json"):
                raise FileNotFoundError(
                    "Service account belum dikonfigurasi di Secrets dan 'client_secret.json' tidak ditemukan di folder project."
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
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab_name}'!A:Z")
        .execute()
    )
    values = result.get("values", [])
    if len(values) < 4:
        return pd.DataFrame()

    # Header berada di baris ke-3 (index 2), baris ke-4 adalah filter, data mulai baris ke-5 (index 4)
    raw_headers = [str(h).strip() for h in values[2]]
    rows = values[4:]

    # Pastikan nama kolom unik & tidak kosong
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
# HELPER NORMALISASI KATEGORI
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
    if "NOT SUBMITTED" in v_upper:
        return "Not Submitted Yet"
    return v if v else "KOSONG"


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

st.sidebar.caption(f"Sumber Tab:\n- `{TAB_LOG}`\n- `{TAB_MASTER}`")


# ==============================================================================
# JUDUL & PENARIKAN DATA
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
except Exception as e:
    st.error(f"Gagal mengambil data dari Google Sheets: {e}")
    st.stop()


# ==============================================================================
# PEMROSESAN TAB 1: LOG_DAILY_ACTIVITY (POIN 1 & POIN 2)
# ==============================================================================
if df_log_raw.empty:
    st.warning(f"Data pada tab '{TAB_LOG}' kosong.")
    df_log_latest = pd.DataFrame()
else:
    required_log_cols = ["Timestamp", "Email_Validator", "Site_ID", "Item_Validasi", "Status_Validasi"]
    missing_log = [c for c in required_log_cols if c not in df_log_raw.columns]
    if missing_log:
        st.error(f"Kolom wajib tidak ditemukan di '{TAB_LOG}': {', '.join(missing_log)}")
        st.write("Kolom yang terbaca:", list(df_log_raw.columns))
        st.stop()

    # Filter hanya item SA Tower dan SA Ground
    item_lower = df_log_raw["Item_Validasi"].astype(str).str.strip().str.lower()
    df_sa = df_log_raw[item_lower.str.contains("tower|ground", regex=True, na=False)].copy()
    df_sa["Item_Kategori"] = df_sa["Item_Validasi"].apply(normalize_sa_item)

    # Ambil record paling terbaru berdasarkan Timestamp per Validator + Site_ID + Item_Kategori
    df_sa["_ts"] = pd.to_datetime(df_sa["Timestamp"], errors="coerce")
    df_sa = df_sa.dropna(subset=["_ts"]).sort_values("_ts", ascending=True)
    df_log_latest = df_sa.drop_duplicates(
        subset=["Email_Validator", "Site_ID", "Item_Kategori"],
        keep="last",
    ).copy()
    df_log_latest = df_log_latest.sort_values("_ts", ascending=False).drop(columns=["_ts"])


# ==============================================================================
# PEMROSESAN TAB 2: MASTER_VALIDASI_SITE (POIN 3 & POIN 4)
# ==============================================================================
if df_master_raw.empty:
    st.warning(f"Data pada tab '{TAB_MASTER}' kosong.")
    df_master_clean = pd.DataFrame()
else:
    df_master_clean = df_master_raw.copy()
    if "Final_Status" in df_master_clean.columns:
        df_master_clean["Final_Status_Group"] = df_master_clean["Final_Status"].apply(
            categorize_final_status
        )
    else:
        df_master_clean["Final_Status_Group"] = "KOLOM TIDAK DITEMUKAN"

    if "Audit_Verdict" in df_master_clean.columns:
        df_master_clean["Audit_Verdict_Group"] = df_master_clean["Audit_Verdict"].apply(
            categorize_audit_verdict
        )
    else:
        df_master_clean["Audit_Verdict_Group"] = "KOLOM TIDAK DITEMUKAN"


# ==============================================================================
# FILTER GLOBAL (VALIDATOR + SYSTEM KEY / SMP ID)
# ==============================================================================
st.subheader("Filter & Pencarian")
col_f1, col_f2, col_f3 = st.columns([2, 2, 1])

with col_f1:
    validator_list = (
        sorted(
            [
                v
                for v in df_log_latest["Email_Validator"].dropna().astype(str).str.strip().unique()
                if v
            ]
        )
        if not df_log_latest.empty
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

# Terapkan filter ke Log Daily Activity
df_log_view = df_log_latest.copy()
if not df_log_view.empty:
    if selected_validators:
        df_log_view = df_log_view[
            df_log_view["Email_Validator"].astype(str).str.strip().isin(selected_validators)
        ]
    if selected_items:
        df_log_view = df_log_view[df_log_view["Item_Kategori"].isin(selected_items)]
    if search_query:
        s_key = (
            df_log_view["System_Key"].astype(str).str.lower()
            if "System_Key" in df_log_view.columns
            else pd.Series("", index=df_log_view.index)
        )
        smp = (
            df_log_view["SMP_ID"].astype(str).str.lower()
            if "SMP_ID" in df_log_view.columns
            else pd.Series("", index=df_log_view.index)
        )
        df_log_view = df_log_view[
            s_key.str.contains(search_query, na=False) | smp.str.contains(search_query, na=False)
        ]

# Terapkan filter ke Master Validasi Site (mengikuti pencarian System Key / SMP ID atau validator)
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
        # Jika memfilter validator tertentu, tampilkan site yang berkaitan dengan validator tersebut
        related_keys = set(df_log_view["System_Key"].astype(str).str.strip()) if "System_Key" in df_log_view.columns else set()
        related_smps = set(df_log_view["SMP_ID"].astype(str).str.strip()) if "SMP_ID" in df_log_view.columns else set()
        cond_key = df_master_view["System_Key"].astype(str).str.strip().isin(related_keys) if "System_Key" in df_master_view.columns else False
        cond_smp = df_master_view["SMP_ID"].astype(str).str.strip().isin(related_smps) if "SMP_ID" in df_master_view.columns else False
        df_master_view = df_master_view[cond_key | cond_smp]


# ==============================================================================
# TAMPILAN 1: LOG VALIDATOR SA TOWER & SA GROUND
# ==============================================================================
st.divider()
st.header("Log Aktivitas Terbaru (SA Tower & SA Ground)")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Record Terbaru", len(df_log_view))
m2.metric(
    "Total Site Unik",
    df_log_view["Site_ID"].nunique() if not df_log_view.empty else 0,
)
m3.metric(
    "SA Tower",
    int((df_log_view["Item_Kategori"] == "SA Tower").sum()) if not df_log_view.empty else 0,
)
m4.metric(
    "SA Ground",
    int((df_log_view["Item_Kategori"] == "SA Ground").sum()) if not df_log_view.empty else 0,
)

if df_log_view.empty:
    st.info("Tidak ada data Log Daily Activity yang cocok dengan filter saat ini.")
else:
    display_log_cols = [
        c
        for c in [
            "Timestamp",
            "Email_Validator",
            "Region",
            "System_Key",
            "SMP_ID",
            "Site_ID",
            "Item_Kategori",
            "Item_Validasi",
            "Status_Validasi",
            "Catatan_Revisi",
        ]
        if c in df_log_view.columns
    ]
    st.dataframe(df_log_view[display_log_cols], use_container_width=True, hide_index=True)


# ==============================================================================
# TAMPILAN 2: MASTER VALIDASI SITE (FINAL STATUS & AUDIT VERDICT)
# ==============================================================================
st.divider()
st.header("Status Validasi Site & Audit Verdict")

col_fs, col_av = st.columns(2)

with col_fs:
    st.subheader("Final Status (3 Kategori)")
    fs_counts = (
        df_master_view["Final_Status_Group"].value_counts()
        if not df_master_view.empty
        else pd.Series(dtype=int)
    )
    f1, f2, f3 = st.columns(3)
    f1.metric("HOLD - NEED REVISION", int(fs_counts.get("HOLD - NEED REVISION", 0)))
    f2.metric("INCOMPLETE", int(fs_counts.get("INCOMPLETE", 0)))
    f3.metric("READY TO SUBMIT ATP", int(fs_counts.get("READY TO SUBMIT ATP", 0)))

with col_av:
    st.subheader("Audit Verdict (3 Kategori)")
    av_counts = (
        df_master_view["Audit_Verdict_Group"].value_counts()
        if not df_master_view.empty
        else pd.Series(dtype=int)
    )
    a1, a2, a3 = st.columns(3)
    a1.metric("COMPLIANT", int(av_counts.get("COMPLIANT", 0)))
    a2.metric("LEGACY / PRE-QC GATE", int(av_counts.get("LEGACY / PRE-QC GATE", 0)))
    a3.metric("Not Submitted Yet", int(av_counts.get("Not Submitted Yet", 0)))

# Filter cepat berdasarkan Final Status & Audit Verdict
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

if df_master_table.empty:
    st.info("Tidak ada data Master Validasi Site yang cocok dengan filter saat ini.")
else:
    display_master_cols = [
        c
        for c in [
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
        ]
        if c in df_master_table.columns
    ]
    st.dataframe(df_master_table[display_master_cols], use_container_width=True, hide_index=True)

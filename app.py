import os
import re
from datetime import timedelta
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
TAB_ATP = "Log_ATP_History"


# ==============================================================================
# FUNGSI OTENTIKASI & PENARIKAN DATA GOOGLE SHEETS
# ==============================================================================
def get_sheets_service():
    if "gcp_service_account" in st.secrets:
        sa_info = dict(st.secrets["gcp_service_account"])
        if "private_key" in sa_info and isinstance(sa_info["private_key"], str):
            sa_info["private_key"] = sa_info["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=SCOPES
        )
        return build("sheets", "v4", credentials=creds)

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
# HELPER NORMALISASI KATEGORI & TANGGAL
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


def extract_activity_date(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="datetime64[ns]")
    tgl_series = (
        pd.to_datetime(df["Tgl"], errors="coerce")
        if "Tgl" in df.columns
        else pd.Series(pd.NaT, index=df.index)
    )
    ts_series = (
        pd.to_datetime(df["Timestamp"], errors="coerce")
        if "Timestamp" in df.columns
        else pd.Series(pd.NaT, index=df.index)
    )
    combined = tgl_series.fillna(ts_series)
    return combined.dt.normalize()


def extract_atp_event_date(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="datetime64[ns]")
    cols_priority = ["Actual_Approved_Nokia", "Actual_Submit_Nokia", "Timestamp"]
    combined = pd.Series(pd.NaT, index=df.index)
    for col in cols_priority:
        if col in df.columns:
            parsed = pd.to_datetime(df[col], errors="coerce")
            combined = combined.fillna(parsed)
    return combined.dt.normalize()


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
        try:
            df_atp_raw = load_sheet_tab(sheet_url.strip(), TAB_ATP, st.session_state.cache_buster)
        except Exception as atp_err:
            st.warning(f"Tab '{TAB_ATP}' belum dapat dimuat: {atp_err}")
            df_atp_raw = pd.DataFrame()
except Exception as e:
    st.error(f"Gagal mengambil data dari Google Sheets: {e}")
    st.stop()


# ==============================================================================
# PEMROSESAN TAB 1: LOG_DAILY_ACTIVITY
# ==============================================================================
if df_log_raw.empty:
    st.warning(f"Data pada tab '{TAB_LOG}' kosong.")
    df_sa_all = pd.DataFrame()
else:
    required_log_cols = ["Timestamp", "Email_Validator", "Site_ID", "Item_Validasi", "Status_Validasi"]
    missing_log = [c for c in required_log_cols if c not in df_log_raw.columns]
    if missing_log:
        st.error(f"Kolom wajib tidak ditemukan di '{TAB_LOG}': {', '.join(missing_log)}")
        st.write("Kolom yang terbaca:", list(df_log_raw.columns))
        st.stop()

    item_lower = df_log_raw["Item_Validasi"].astype(str).str.strip().str.lower()
    df_sa_all = df_log_raw[item_lower.str.contains("tower|ground", regex=True, na=False)].copy()
    df_sa_all["Item_Kategori"] = df_sa_all["Item_Validasi"].apply(normalize_sa_item)
    df_sa_all["_activity_date"] = extract_activity_date(df_sa_all)
    df_sa_all["_ts"] = pd.to_datetime(df_sa_all["Timestamp"], errors="coerce")


# ==============================================================================
# PEMROSESAN TAB 2: MASTER_VALIDASI_SITE
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
# PEMROSESAN TAB 3: LOG_ATP_HISTORY
# ==============================================================================
if df_atp_raw.empty:
    df_atp_clean = pd.DataFrame()
else:
    df_atp_clean = df_atp_raw.copy()
    df_atp_clean["_event_date"] = extract_atp_event_date(df_atp_clean)
    if "Event_Type" in df_atp_clean.columns:
        df_atp_clean["Event_Type_Clean"] = (
            df_atp_clean["Event_Type"].astype(str).str.strip().str.upper()
        )
    else:
        df_atp_clean["Event_Type_Clean"] = "UNKNOWN"


# ==============================================================================
# FILTER GLOBAL (VALIDATOR + SYSTEM KEY / SMP ID + ITEM + KALENDER)
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

# Rentang tanggal kalender
valid_dates = []
if not df_sa_all.empty and "_activity_date" in df_sa_all.columns:
    valid_dates.extend(df_sa_all["_activity_date"].dropna().dt.date.tolist())
if not df_atp_clean.empty and "_event_date" in df_atp_clean.columns:
    valid_dates.extend(df_atp_clean["_event_date"].dropna().dt.date.tolist())

col_cal, col_preset = st.columns([2.2, 2.8])
date_range_selected = None

if valid_dates:
    min_d = min(valid_dates)
    max_d = max(valid_dates)
    default_start = max(min_d, max_d - timedelta(days=29))

    with col_preset:
        st.write("")
        p1, p2, p3, p4 = st.columns(4)
        if p1.button("7 Hari", use_container_width=True):
            st.session_state["date_range"] = (max(min_d, max_d - timedelta(days=6)), max_d)
        if p2.button("30 Hari", use_container_width=True):
            st.session_state["date_range"] = (max(min_d, max_d - timedelta(days=29)), max_d)
        if p3.button("Hari Ini", use_container_width=True):
            st.session_state["date_range"] = (max_d, max_d)
        if p4.button("Semua", use_container_width=True):
            st.session_state["date_range"] = (min_d, max_d)

    if "date_range" not in st.session_state:
        st.session_state["date_range"] = (default_start, max_d)

    with col_cal:
        picked = st.date_input(
            "Rentang Tanggal Kalender (Log Aktivitas & ATP):",
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


# Terapkan filter ke Log Daily Activity
df_sa_filtered = df_sa_all.copy()
if not df_sa_filtered.empty:
    if date_range_selected:
        start_dt = pd.Timestamp(date_range_selected[0])
        end_dt = pd.Timestamp(date_range_selected[1])
        df_sa_filtered = df_sa_filtered[
            df_sa_filtered["_activity_date"].notna()
            & (df_sa_filtered["_activity_date"] >= start_dt)
            & (df_sa_filtered["_activity_date"] <= end_dt)
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

    # Ambil record paling terbaru berdasarkan Timestamp per Validator + Site_ID + Item_Kategori
    df_log_view = (
        df_sa_filtered.dropna(subset=["_ts"])
        .sort_values("_ts", ascending=True)
        .drop_duplicates(
            subset=["Email_Validator", "Site_ID", "Item_Kategori"],
            keep="last",
        )
        .sort_values("_ts", ascending=False)
        .drop(columns=["_ts", "_activity_date"], errors="ignore")
    )
else:
    df_log_view = pd.DataFrame()


# Terapkan filter ke Master Validasi Site
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
        related_keys = (
            set(df_log_view["System_Key"].astype(str).str.strip())
            if "System_Key" in df_log_view.columns
            else set()
        )
        related_smps = (
            set(df_log_view["SMP_ID"].astype(str).str.strip())
            if "SMP_ID" in df_log_view.columns
            else set()
        )
        cond_key = (
            df_master_view["System_Key"].astype(str).str.strip().isin(related_keys)
            if "System_Key" in df_master_view.columns
            else False
        )
        cond_smp = (
            df_master_view["SMP_ID"].astype(str).str.strip().isin(related_smps)
            if "SMP_ID" in df_master_view.columns
            else False
        )
        df_master_view = df_master_view[cond_key | cond_smp]


# Terapkan filter ke Log ATP History
df_atp_view = df_atp_clean.copy()
if not df_atp_view.empty:
    if date_range_selected:
        start_dt = pd.Timestamp(date_range_selected[0])
        end_dt = pd.Timestamp(date_range_selected[1])
        df_atp_view = df_atp_view[
            df_atp_view["_event_date"].notna()
            & (df_atp_view["_event_date"] >= start_dt)
            & (df_atp_view["_event_date"] <= end_dt)
        ]
    if search_query:
        a_skey = (
            df_atp_view["System_Key"].astype(str).str.lower()
            if "System_Key" in df_atp_view.columns
            else pd.Series("", index=df_atp_view.index)
        )
        a_smp = (
            df_atp_view["SMP_ID"].astype(str).str.lower()
            if "SMP_ID" in df_atp_view.columns
            else pd.Series("", index=df_atp_view.index)
        )
        a_site = (
            df_atp_view["Site_ID"].astype(str).str.lower()
            if "Site_ID" in df_atp_view.columns
            else pd.Series("", index=df_atp_view.index)
        )
        df_atp_view = df_atp_view[
            a_skey.str.contains(search_query, na=False)
            | a_smp.str.contains(search_query, na=False)
            | a_site.str.contains(search_query, na=False)
        ]


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
    f2.metric("INCOMPLETE (0/10–6/10)", int(fs_counts.get("INCOMPLETE", 0)))
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


# ==============================================================================
# TAMPILAN 3: RIWAYAT & TREN ATP (LOG_ATP_HISTORY)
# ==============================================================================
st.divider()
st.header(f"Riwayat & Tren ATP ({TAB_ATP})")

if df_atp_view.empty:
    st.info(f"Tidak ada data pada tab '{TAB_ATP}' yang cocok dengan filter kalender/pencarian.")
else:
    ev_counts = (
        df_atp_view["Event_Type_Clean"].value_counts()
        if "Event_Type_Clean" in df_atp_view.columns
        else pd.Series(dtype=int)
    )
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Total Event ATP", len(df_atp_view))
    t2.metric("Approved", int(ev_counts.get("APPROVED", 0)))
    t3.metric("Submitted", int(ev_counts.get("SUBMITTED", 0)))
    t4.metric("Reject", int(ev_counts.get("REJECT", 0) + ev_counts.get("REJECTED", 0)))

    if "_event_date" in df_atp_view.columns and "Event_Type_Clean" in df_atp_view.columns:
        trend_df = (
            df_atp_view.dropna(subset=["_event_date"])
            .assign(Tanggal=lambda d: d["_event_date"].dt.strftime("%Y-%m-%d"))
            .groupby(["Tanggal", "Event_Type_Clean"], as_index=False)
            .size()
            .pivot(index="Tanggal", columns="Event_Type_Clean", values="size")
            .fillna(0)
        )
        if not trend_df.empty:
            st.caption("Tren Harian Event ATP berdasarkan rentang tanggal terpilih:")
            st.line_chart(trend_df, use_container_width=True)

    display_atp_cols = [
        c
        for c in [
            "Timestamp",
            "System_Key",
            "SMP_ID",
            "Site_ID",
            "Actual_Submit_Nokia",
            "Actual_Approved_Nokia",
            "Status_ATP",
            "Event_Type",
        ]
        if c in df_atp_view.columns
    ]
    st.dataframe(
        df_atp_view.drop(columns=["_event_date", "Event_Type_Clean"], errors="ignore")[display_atp_cols],
        use_container_width=True,
        hide_index=True,
    )

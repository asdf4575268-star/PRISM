import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date
import time
import re
import xml.etree.ElementTree as ET
from supabase import create_client, Client

# -------------------- 공통 헬퍼 --------------------

DB_NAME = 'archive_prism_total_v5.db'

def get_conn():
    return sqlite3.connect(DB_NAME)

def is_valid_url(url):
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    return url.startswith("http://") or url.startswith("https://")

def safe_image(url, **kwargs):
    if is_valid_url(url):
        st.image(url, **kwargs)

CATEGORY_LABELS = {
    "BOOKS": "📖 출판사",
    "MUSIC": "💿 레이블",
    "MOVIES": "🎬 제작사",
    "SERIES": "📺 플랫폼",
    "STAGE": "📍 장소"
}

# -------------------- 설정 --------------------

st.set_page_config(
    layout="wide",
    page_title="PRISM",
    page_icon="🌈",
    initial_sidebar_state="collapsed"
)

TMDB_API_KEY = "YOUR_TMDB"
KOPIS_KEY = "YOUR_KOPIS"

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🌈PRISM ARCHIVE")

# -------------------- DB 초기화 --------------------

def init_db():
    with get_conn() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             category TEXT, title TEXT, creator TEXT,
             rel_date TEXT, venue TEXT,
             summary TEXT, brief TEXT,
             highlights TEXT, note TEXT,
             img_url TEXT, img_url2 TEXT,
             save_date TEXT, view_date TEXT)''')

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(archive)")
        columns = [c[1] for c in cursor.fetchall()]
        if "img_url2" not in columns:
            conn.execute("ALTER TABLE archive ADD COLUMN img_url2 TEXT")
            conn.commit()

init_db()

# -------------------- Supabase Sync --------------------

def migrate_to_supabase():
    try:
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            local_data = conn.execute("SELECT * FROM archive").fetchall()

        if not local_data:
            st.session_state.sync_msg = ("warning", "로컬 데이터가 없습니다.")
            return

        upload_list = [
            {k: v for k, v in dict(row).items() if k != "id"}
            for row in local_data
        ]

        supabase.table("archive").upsert(upload_list).execute()
        st.session_state.sync_msg = ("success", f"✅ {len(upload_list)}개 데이터 백업 완료")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ {e}")

def restore_from_supabase():
    try:
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, "data") else res

        if not cloud_data:
            st.session_state.sync_msg = ("warning", "클라우드가 비어있습니다.")
            return

        added = 0
        with get_conn() as conn:
            cursor = conn.cursor()
            for row in cloud_data:
                exists = cursor.execute(
                    "SELECT id FROM archive WHERE title=? AND view_date=?",
                    (row["title"], row["view_date"])
                ).fetchone()
                if not exists:
                    cursor.execute("""INSERT INTO archive
                        (category, title, creator, rel_date, venue,
                         summary, brief, highlights, note,
                         img_url, img_url2, save_date, view_date)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row["category"], row["title"], row["creator"],
                         row["rel_date"], row["venue"],
                         row["summary"], row["brief"],
                         row["highlights"], row["note"],
                         row["img_url"], row.get("img_url2",""),
                         row["save_date"], row["view_date"])
                    )
                    added += 1
            conn.commit()

        st.session_state.sync_msg = ("success", f"✅ {added}개 복구 완료")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ {e}")

# -------------------- 로그인 --------------------

if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False

if "view_mode" not in st.session_state:
    st.session_state.view_mode = "PC"

if st.session_state.get("user_password") == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True

is_admin = st.session_state.is_logged_in

with st.sidebar:
    st.markdown("### 🔐 Admin Access")

    if not is_admin:
        pw = st.text_input("Password", type="password")
        if pw == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.user_password = pw
            st.session_state.is_logged_in = True
            st.rerun()

    if is_admin:
        st.success("Admin Mode Active")
        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.clear()
            st.rerun()

        st.divider()
        if 'sync_msg' in st.session_state:
            t,m = st.session_state.sync_msg
            getattr(st, t)(m)
            del st.session_state.sync_msg

        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)

    st.divider()
    st.session_state.view_mode = st.radio(
        "보기 옵션", ["PC","Mobile"], horizontal=True,
        label_visibility="collapsed"
    )

is_mobile = st.session_state.view_mode == "Mobile"

# -------------------- 상세 다이얼로그 --------------------

@st.dialog("📋 기록", width="large")
def show_details(item):

    col_img, col_txt = (
        (st.container(), st.container())
        if is_mobile else
        st.columns([0.3,0.7])
    )

    with col_img:
        safe_image(item.get("img_url"), use_container_width=True)
        safe_image(item.get("img_url2"), use_container_width=True)

    with col_txt:
        st.markdown(f"# {item.get('title')}")
        st.write(f"#### [{item.get('category')}]")
        st.write(item.get("creator"))
        st.write(f"📅 {item.get('rel_date')} | 📍 {item.get('venue')}")
        st.write(f"🍿 감상일: {item.get('view_date')}")
        st.divider()

        for label,key in [
            ("📖 줄거리","summary"),
            ("📝 요약","brief"),
            ("✨ 인상 깊은 부분","highlights"),
            ("🌈 PRISM","note")
        ]:
            content = item.get(key)
            if content:
                st.markdown(f"**{label}**")
                st.write(content)

# -------------------- ARCHIVE --------------------

with get_conn() as conn:
    all_df = pd.read_sql_query(
        "SELECT * FROM archive ORDER BY view_date DESC",
        conn
    )

if not all_df.empty:

    all_df["v_dt"] = pd.to_datetime(all_df["view_date"], errors="coerce")
    grid_cols = 6

    years = sorted(all_df["v_dt"].dt.year.dropna().unique(), reverse=True)

    if years:
        sel_y = st.selectbox("📅 연도 선택", years)
        y_df = all_df[all_df["v_dt"].dt.year == sel_y]

        for m in range(12,0,-1):
            m_df = y_df[y_df["v_dt"].dt.month == m]
            if not m_df.empty:
                st.subheader(f"{m}월")
                items = m_df.to_dict("records")

                for i in range(0,len(items),grid_cols):
                    cols = st.columns(grid_cols)
                    for j in range(grid_cols):
                        if i+j < len(items):
                            row = items[i+j]
                            with cols[j]:
                                safe_image(row["img_url"], use_container_width=True)
                                if st.button(
                                    row["title"][:10],
                                    key=f"btn_{row['id']}"
                                ):
                                    show_details(row)

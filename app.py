import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date
import time
import re
import xml.etree.ElementTree as ET
from supabase import create_client, Client

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(layout="wide", page_title="PRISM", page_icon="🌈")

DB_NAME = "archive_prism_total_v5.db"

TMDB_API_KEY = st.secrets["TMDB_API_KEY"]
KAKAO_REST_KEY = st.secrets["KAKAO_REST_KEY"]
KOPIS_KEY = st.secrets["KOPIS_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

CATEGORIES = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]


# =========================================================
# DATABASE LAYER
# =========================================================

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            title TEXT,
            creator TEXT,
            rel_date TEXT,
            venue TEXT,
            summary TEXT,
            brief TEXT,
            highlights TEXT,
            note TEXT,
            img_url TEXT,
            img_url2 TEXT,
            save_date TEXT,
            view_date TEXT
        )
        """)

        cols = [c[1] for c in conn.execute("PRAGMA table_info(archive)")]
        if "img_url2" not in cols:
            conn.execute("ALTER TABLE archive ADD COLUMN img_url2 TEXT")

init_db()


class ArchiveRepository:

    @staticmethod
    def fetch_all():
        with get_conn() as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                "SELECT * FROM archive ORDER BY view_date DESC"
            ).fetchall()

    @staticmethod
    def insert(data):
        with get_conn() as conn:
            conn.execute("""
            INSERT INTO archive 
            (category,title,creator,rel_date,venue,summary,brief,highlights,
             note,img_url,img_url2,save_date,view_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                data["category"], data["title"], data["creator"],
                data["rel_date"], data["venue"], data["summary"],
                data["brief"], data["highlights"], data["note"],
                data["img_url"], data["img_url2"],
                data["save_date"], data["view_date"]
            ))

    @staticmethod
    def update(item_id, data):
        with get_conn() as conn:
            conn.execute("""
            UPDATE archive SET
            title=?, creator=?, rel_date=?, venue=?,
            summary=?, brief=?, highlights=?, note=?,
            view_date=?, img_url=?, img_url2=?
            WHERE id=?
            """, (
                data["title"], data["creator"], data["rel_date"], data["venue"],
                data["summary"], data["brief"], data["highlights"], data["note"],
                data["view_date"], data["img_url"], data["img_url2"],
                item_id
            ))

    @staticmethod
    def delete(item_id):
        with get_conn() as conn:
            conn.execute("DELETE FROM archive WHERE id=?", (item_id,))


# =========================================================
# SYNC SERVICE (ID 기반 정합성)
# =========================================================

class SyncService:

    @staticmethod
    def backup():
        rows = ArchiveRepository.fetch_all()
        upload = [dict(r) for r in rows]
        supabase.table("archive").upsert(upload).execute()

    @staticmethod
    def restore():
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data

        for row in cloud_data:
            exists = any(r["id"] == row["id"] for r in ArchiveRepository.fetch_all())
            if not exists:
                ArchiveRepository.insert(row)

    @staticmethod
    def update_cloud(item_id, data):
        supabase.table("archive").update(data).eq("id", item_id).execute()

    @staticmethod
    def delete_cloud(item_id):
        supabase.table("archive").delete().eq("id", item_id).execute()


# =========================================================
# API LAYER
# =========================================================

def search_books(query):
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}
    res = requests.get(
        "https://dapi.kakao.com/v3/search/book",
        headers=headers,
        params={"query": query}
    )
    return res.json().get("documents", []) if res.status_code == 200 else []


def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
    res = requests.get(url).json().get("results", [])
    return res


def search_tmdb(query, category):
    path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{path}"
    params = {"api_key": TMDB_API_KEY, "query": query, "language": "ko-KR"}
    return requests.get(url, params=params).json().get("results", [])


def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=100&cpage=1"
    res = requests.get(url)
    root = ET.fromstring(res.content)
    return root.findall("db")


# =========================================================
# AUTH
# =========================================================

if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False

with st.sidebar:
    st.markdown("### 🔐 Admin")
    if not st.session_state.is_logged_in:
        pw = st.text_input("Password", type="password")
        if pw == ADMIN_PASSWORD:
            st.session_state.is_logged_in = True
            st.rerun()

    if st.session_state.is_logged_in:
        st.success("Admin Mode")
        if st.button("Logout"):
            st.session_state.is_logged_in = False
            st.rerun()

        st.divider()
        st.button("📤 Backup", on_click=SyncService.backup)
        st.button("📥 Restore", on_click=SyncService.restore)

is_admin = st.session_state.is_logged_in


# =========================================================
# MAIN UI
# =========================================================

st.title("🌈 PRISM ARCHIVE")

tabs = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"] if is_admin else ["📂 ARCHIVE"])

# =========================================================
# WRITE TAB
# =========================================================

if is_admin:
    with tabs[0]:

        category = st.radio("CATEGORY", CATEGORIES, horizontal=True)

        title = st.text_input("Title")
        creator = st.text_input("Creator")
        rel_date = st.text_input("Rel Date")
        venue = st.text_input("Venue")
        summary = st.text_area("Summary")
        brief = st.text_input("Brief")
        highlights = st.text_area("Highlights")
        note = st.text_area("PRISM")
        img_url = st.text_input("Main Image URL")
        img_url2 = st.text_input("Sub Image URL")
        view_date = st.date_input("View Date", value=date.today())

        if st.button("Save"):

            record = {
                "category": category,
                "title": title.strip(),
                "creator": creator.strip(),
                "rel_date": rel_date,
                "venue": venue.strip(),
                "summary": summary.strip(),
                "brief": brief.strip(),
                "highlights": highlights.strip(),
                "note": note.strip(),
                "img_url": img_url.strip(),
                "img_url2": img_url2.strip(),
                "save_date": str(date.today()),
                "view_date": str(view_date)
            }

            ArchiveRepository.insert(record)
            SyncService.backup()

            st.success("Saved")
            time.sleep(0.5)
            st.rerun()


# =========================================================
# ARCHIVE TAB
# =========================================================

with tabs[-1]:

    rows = ArchiveRepository.fetch_all()
    df = pd.DataFrame(rows)

    if not df.empty:

        df["v_dt"] = pd.to_datetime(df["view_date"], errors="coerce")
        years = sorted(df["v_dt"].dt.year.dropna().unique(), reverse=True)

        sel_year = st.selectbox("Year", years)

        year_df = df[df["v_dt"].dt.year == sel_year]

        for month in range(12, 0, -1):

            m_df = year_df[year_df["v_dt"].dt.month == month]

            if not m_df.empty:
                st.subheader(f"{month}월")

                for _, row in m_df.iterrows():
                    with st.expander(f"{row['title']} ({row['category']})"):

                        if row["img_url"]:
                            st.image(row["img_url"], use_container_width=True)

                        if row["img_url2"]:
                            st.image(row["img_url2"], use_container_width=True)

                        st.write(f"**Creator:** {row['creator']}")
                        st.write(f"**Rel Date:** {row['rel_date']}")
                        st.write(f"**Venue:** {row['venue']}")
                        st.write(f"**View Date:** {row['view_date']}")

                        st.divider()
                        st.write(row["summary"])
                        st.write(row["brief"])
                        st.write(row["highlights"])
                        st.write(row["note"])

                        if is_admin:
                            if st.button("Delete", key=f"del_{row['id']}"):
                                ArchiveRepository.delete(row["id"])
                                SyncService.delete_cloud(row["id"])
                                st.rerun()

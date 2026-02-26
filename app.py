import streamlit as st
import sqlite3
import requests
from datetime import datetime
from supabase import create_client, Client

# ==================================================
# 🔑 설정
# ==================================================

TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

DB_NAME = "archive_prism_total_v5.db"

SUPABASE_URL = st.secrets.get("SUPABASE_URL", None)
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", None)

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CATEGORIES = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]

# ==================================================
# 🗄 DB
# ==================================================

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        conn.execute('''
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
        ''')

init_db()

# ==================================================
# ☁️ Sync
# ==================================================

def cloud_upsert(data):
    if not supabase:
        return
    supabase.table("archive").upsert(data).execute()

def cloud_delete(item_id):
    if not supabase:
        return
    supabase.table("archive").delete().eq("id", item_id).execute()

# ==================================================
# 🔎 TMDB 검색
# ==================================================

def search_tmdb(query, category):
    path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{path}"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "ko-KR"
    }
    res = requests.get(url, params=params)
    return res.json().get("results", [])

# ==================================================
# ✍ 저장
# ==================================================

def save_item(data):
    with get_conn() as conn:
        cursor = conn.execute("""
        INSERT INTO archive
        (category,title,creator,rel_date,venue,summary,brief,highlights,note,img_url,img_url2,save_date,view_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data["category"], data["title"], data["creator"],
            data["rel_date"], data["venue"], data["summary"],
            data["brief"], data["highlights"], data["note"],
            data["img_url"], data["img_url2"],
            data["save_date"], data["view_date"]
        ))
        item_id = cursor.lastrowid

    data["id"] = item_id
    cloud_upsert(data)

# ==================================================
# 🎨 UI
# ==================================================

st.set_page_config(page_title="PRISM", layout="wide")

st.title("🌈 PRISM ARCHIVE")

tab1, tab2 = st.tabs(["🖋 WRITE", "📂 ARCHIVE"])

# ==================================================
# 🖋 WRITE TAB
# ==================================================

with tab1:
    category = st.selectbox("Category", CATEGORIES)
    title = st.text_input("Title")

    creator = st.text_input("Creator")
    rel_date = st.text_input("Release Date")
    venue = st.text_input("Venue")

    summary = st.text_area("Summary")
    brief = st.text_area("Brief")
    highlights = st.text_area("Highlights")
    note = st.text_area("Note")

    img_url = st.text_input("Image URL 1")
    img_url2 = st.text_input("Image URL 2")

    view_date = st.date_input("View Date")

    if st.button("Save"):
        save_item({
            "category": category,
            "title": title,
            "creator": creator,
            "rel_date": rel_date,
            "venue": venue,
            "summary": summary,
            "brief": brief,
            "highlights": highlights,
            "note": note,
            "img_url": img_url,
            "img_url2": img_url2,
            "save_date": datetime.now().strftime("%Y-%m-%d"),
            "view_date": view_date.strftime("%Y-%m-%d")
        })
        st.success("Saved")

# ==================================================
# 📂 ARCHIVE TAB
# ==================================================

with tab2:

    with get_conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM archive ORDER BY view_date DESC"
        ).fetchall()

    for item in rows:
        with st.expander(f"{item['title']} ({item['category']})"):
            col1, col2 = st.columns([1, 3])

            with col1:
                if item["img_url"]:
                    st.image(item["img_url"])
                if item["img_url2"]:
                    st.image(item["img_url2"])

            with col2:
                st.markdown(f"**Creator:** {item['creator']}")
                st.markdown(f"**Release:** {item['rel_date']}")
                st.markdown(f"**Venue:** {item['venue']}")
                st.markdown(f"**View Date:** {item['view_date']}")
                st.markdown("---")
                st.markdown(item["summary"])
                st.markdown(item["brief"])
                st.markdown(item["highlights"])
                st.markdown(item["note"])

                if st.button("Delete", key=f"del_{item['id']}"):
                    with get_conn() as conn:
                        conn.execute(
                            "DELETE FROM archive WHERE id=?",
                            (item["id"],)
                        )
                    cloud_delete(item["id"])
                    st.rerun()

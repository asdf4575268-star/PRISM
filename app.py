import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re
import time
import os
import shutil

# ------------------ 기본 설정 ------------------

st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "archive_prism_total_v4.db")

TMDB_API_KEY = "YOUR_TMDB_KEY"
KOPIS_KEY = "YOUR_KOPIS_KEY"
GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pubhtml?gid=1160662254&single=true"

# ------------------ DB 초기화 ------------------

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             category TEXT, title TEXT, creator TEXT,
             rel_date TEXT, summary TEXT, brief TEXT,
             highlights TEXT, note TEXT,
             img_url TEXT, save_date TEXT, view_date TEXT)''')

init_db()

# ------------------ Google 복원 ------------------

def restore_from_google():
    try:
        df = pd.read_csv(GOOGLE_SHEET_CSV)

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM archive")

            for _, row in df.iterrows():
                conn.execute("""
                    INSERT INTO archive
                    (category, title, creator, rel_date,
                     summary, brief, highlights, note,
                     img_url, save_date, view_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get("category"),
                    row.get("title"),
                    row.get("creator"),
                    row.get("rel_date"),
                    row.get("summary"),
                    row.get("brief"),
                    row.get("highlights"),
                    row.get("note"),
                    row.get("img_url"),
                    row.get("save_date"),
                    row.get("view_date"),
                ))

        st.success("✅ Google 백업 복원 완료")
        time.sleep(1)
        st.rerun()

    except Exception as e:
        st.error(f"❌ 복원 실패: {e}")

# ------------------ 자동 복원 ------------------

with sqlite3.connect(DB_NAME) as conn:
    check_df = pd.read_sql_query("SELECT COUNT(*) as cnt FROM archive", conn)

if check_df["cnt"][0] == 0 and GOOGLE_SHEET_CSV != "":
    restore_from_google()

# ------------------ 백업 ------------------

def backup_local_db():
    backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
    shutil.copy(DB_NAME, os.path.join(BASE_DIR, backup_name))

# ------------------ API ------------------

def search_books(query):
    headers = {"Authorization": "KakaoAK YOUR_KAKAO_KEY"}
    try:
        res = requests.get(
            "https://dapi.kakao.com/v3/search/book",
            headers=headers,
            params={"query": query},
        )
        return res.json().get("documents", [])
    except:
        return []

def search_apple_music(query):
    try:
        res = requests.get(
            f"https://itunes.apple.com/search?term={query}&limit=20&country=kr"
        ).json()
        return res.get("results", [])
    except:
        return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    try:
        res = requests.get(
            f"https://api.themoviedb.org/3/search/{type_path}",
            params={
                "api_key": TMDB_API_KEY,
                "query": query,
                "language": "ko-KR",
            },
        )
        return res.json().get("results", [])
    except:
        return []

def search_kopis(query):
    try:
        url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=20200101&eddate=20261231&rows=10&cpage=1"
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [
            {
                "title": d.findtext("prfnm"),
                "date": d.findtext("prfpdfrom"),
                "img": d.findtext("poster"),
                "venue": d.findtext("fcltynm"),
            }
            for d in root.findall("db")
        ]
    except:
        return []

# ------------------ TAB 구성 ------------------

tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

# ================= WRITE =================

with tab1:

    category = st.radio(
        "📂 CATEGORY",
        ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"],
        horizontal=True,
    )

    search_query = st.text_input("🔍 검색")

    if search_query:

        if category == "BOOKS":
            res = search_books(search_query)

        elif category == "MUSIC":
            res = search_apple_music(search_query)

        elif category in ["MOVIES", "SERIES"]:
            res = search_tmdb(search_query, category)

        elif category == "STAGE":
            res = search_kopis(search_query)

        st.write(res)

    st.divider()

    img_url = st.text_input("🖼️ 이미지 URL")
    title = st.text_input("제목")
    creator = st.text_input("창작자")
    rel_date = st.text_input("📅 작품 날짜")
    view_date = st.date_input("🍿 감상일", value=date.today())
    summary = st.text_area("📖 줄거리")
    brief = st.text_input("📝 요약")
    highlights = st.text_area("✨ 인상 깊은 부분")
    note = st.text_area("💬 감상")

    if st.button("✅ 저장", use_container_width=True):

        processed_note = note.replace("KM", "km").replace("BPM", "bpm")
        safe_img_url = (
            img_url
            if img_url
            else "https://via.placeholder.com/500x750?text=No+Image"
        )

        with sqlite3.connect(DB_NAME) as conn:
            existing = conn.execute(
                "SELECT id FROM archive WHERE title=? AND creator=?",
                (title, creator),
            ).fetchone()

        if existing:
            st.warning("⚠️ 이미 저장된 기록입니다.")
        else:
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute(
                    """
                    INSERT INTO archive
                    (category, title, creator, rel_date,
                     summary, brief, highlights, note,
                     img_url, save_date, view_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        category,
                        title,
                        creator,
                        rel_date,
                        summary,
                        brief,
                        highlights,
                        processed_note,
                        safe_img_url,
                        str(date.today()),
                        str(view_date),
                    ),
                )

            backup_local_db()
            st.success("✅ 저장 완료 (로컬 + 자동 백업)")
            time.sleep(1)
            st.rerun()

# ================= ARCHIVE =================

with tab2:

    col1, col2 = st.columns([0.8, 0.2])
    with col2:
        if st.button("🔄 Google 복원"):
            restore_from_google()

    with sqlite3.connect(DB_NAME) as conn:
        df = pd.read_sql_query("SELECT * FROM archive", conn)

    if df.empty:
        st.info("기록이 없습니다.")
    else:
        df["sort_dt"] = pd.to_datetime(
            df["view_date"].fillna(df["save_date"])
        )
        df = df.sort_values(by="sort_dt", ascending=False)

        for _, row in df.iterrows():
            with st.container():
                cols = st.columns([1, 4])
                with cols[0]:
                    st.image(row["img_url"])
                with cols[1]:
                    st.markdown(f"### {row['title']}")
                    st.write(row["creator"])
                    st.write(row["view_date"])
                st.divider()

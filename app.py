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

# ✅ 반드시 CSV 형식이어야 함 (pubhtml ❌)
GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pub?gid=1160662254&single=true&output=csv"

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

# ------------------ Google 복원 (안전 버전) ------------------

def restore_from_google():
    try:
        df = pd.read_csv(
            GOOGLE_SHEET_CSV,
            engine="python",
            sep=",",
            quotechar='"',
            on_bad_lines="skip"
        )

        df.columns = df.columns.str.strip()

        col_map = {}

        for col in df.columns:
            lower = col.lower()
            if "category" in lower:
                col_map["category"] = col
            elif "title" in lower:
                col_map["title"] = col
            elif "creator" in lower:
                col_map["creator"] = col
            elif "rel" in lower:
                col_map["rel_date"] = col
            elif "summary" in lower:
                col_map["summary"] = col
            elif "brief" in lower:
                col_map["brief"] = col
            elif "highlight" in lower:
                col_map["highlights"] = col
            elif "note" in lower:
                col_map["note"] = col
            elif "img" in lower:
                col_map["img_url"] = col
            elif "save" in lower:
                col_map["save_date"] = col
            elif "view" in lower:
                col_map["view_date"] = col

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
                    row.get(col_map.get("category"), ""),
                    row.get(col_map.get("title"), ""),
                    row.get(col_map.get("creator"), ""),
                    row.get(col_map.get("rel_date"), ""),
                    row.get(col_map.get("summary"), ""),
                    row.get(col_map.get("brief"), ""),
                    row.get(col_map.get("highlights"), ""),
                    row.get(col_map.get("note"), ""),
                    row.get(col_map.get("img_url"), ""),
                    row.get(col_map.get("save_date"), ""),
                    row.get(col_map.get("view_date"), ""),
                ))

        st.success("✅ Google 백업 복원 완료")
        time.sleep(1)
        st.rerun()

    except Exception as e:
        st.error(f"❌ 복원 실패: {e}")

# ------------------ 자동 복원 ------------------

with sqlite3.connect(DB_NAME) as conn:
    check_df = pd.read_sql_query("SELECT COUNT(*) as cnt FROM archive", conn)

if check_df["cnt"][0] == 0:
    restore_from_google()

# ------------------ 로컬 백업 ------------------

def backup_local_db():
    backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
    shutil.copy(DB_NAME, os.path.join(BASE_DIR, backup_name))

# ------------------ TAB 구성 ------------------

tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

# ================= WRITE =================

with tab1:

    category = st.radio(
        "📂 CATEGORY",
        ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"],
        horizontal=True,
    )

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

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("""
                INSERT INTO archive
                (category, title, creator, rel_date,
                 summary, brief, highlights, note,
                 img_url, save_date, view_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                category,
                title,
                creator,
                rel_date,
                summary,
                brief,
                highlights,
                processed_note,
                img_url,
                str(date.today()),
                str(view_date),
            ))

        backup_local_db()
        st.success("✅ 저장 완료")
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
            df["view_date"].fillna(df["save_date"]),
            errors="coerce"
        )
        df = df.sort_values(by="sort_dt", ascending=False)

        for _, row in df.iterrows():
            with st.container():
                cols = st.columns([1, 4])
                with cols[0]:
                    if row["img_url"]:
                        st.image(row["img_url"])
                with cols[1]:
                    st.markdown(f"### {row['title']}")
                    st.write(row["creator"])
                    st.write(row["view_date"])
                st.divider()

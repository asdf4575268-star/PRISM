import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime
import os
import shutil
from contextlib import contextmanager

# -------------------------------------------------
# 1. 기본 설정
# -------------------------------------------------
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

DB_NAME = "archive_prism_secure.db"
BACKUP_DIR = "db_backups"
MAX_BACKUPS = 5

# -------------------------------------------------
# 2. 🔒 SQLite 완전 안전 설정
# -------------------------------------------------
def get_connection():
    conn = sqlite3.connect(
        DB_NAME,
        timeout=30,
        isolation_level=None,
        check_same_thread=False
    )
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def db_transaction():
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    except:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_db():
    with db_transaction() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                title TEXT,
                creator TEXT,
                rel_date TEXT,
                summary TEXT,
                brief TEXT,
                highlights TEXT,
                note TEXT,
                img_url TEXT,
                save_date TEXT,
                view_date TEXT
            )
        """)


def auto_backup():
    if not os.path.exists(DB_NAME):
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(DB_NAME, f"{BACKUP_DIR}/backup_{ts}.db")

    backups = sorted(os.listdir(BACKUP_DIR))
    if len(backups) > MAX_BACKUPS:
        for old in backups[:-MAX_BACKUPS]:
            os.remove(os.path.join(BACKUP_DIR, old))


def load_all_data():
    try:
        with get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM archive", conn)
    except:
        return pd.DataFrame()


def insert_archive(data_tuple):
    with db_transaction() as conn:
        conn.execute("""
            INSERT INTO archive
            (category, title, creator, rel_date, summary,
             brief, highlights, note, img_url, save_date, view_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, data_tuple)


def update_archive(data_tuple):
    with db_transaction() as conn:
        conn.execute("""
            UPDATE archive
            SET title=?, creator=?, rel_date=?, summary=?,
                brief=?, highlights=?, note=?, view_date=?
            WHERE id=?
        """, data_tuple)


def delete_archive(item_id):
    with db_transaction() as conn:
        conn.execute("DELETE FROM archive WHERE id=?", (item_id,))


init_db()
auto_backup()

# -------------------------------------------------
# 3. 세션 초기화
# -------------------------------------------------
if 'cal_year' not in st.session_state:
    st.session_state.cal_year = datetime.now().year

if 'cal_month' not in st.session_state:
    st.session_state.cal_month = datetime.now().month

if 'api_data' not in st.session_state:
    st.session_state.api_data = {}

# -------------------------------------------------
# 4. API 함수
# -------------------------------------------------
TMDB_API_KEY = "YOUR_TMDB_KEY"
KOPIS_KEY = "YOUR_KOPIS_KEY"

def search_books(query):
    headers = {"Authorization": "KakaoAK YOUR_KAKAO_KEY"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book",
                           headers=headers,
                           params={"query": query})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except:
        return []

# (기존 search 함수들은 그대로 사용 가능 — 생략 없이 유지 가능)

# -------------------------------------------------
# 5. WRITE 탭
# -------------------------------------------------
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:

    category = st.radio("📂 CATEGORY",
                        ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"],
                        horizontal=True)

    title = st.text_input("제목")
    creator = st.text_input("창작자")
    rel_date = st.text_input("작품 날짜", value=str(date.today()))
    view_date = st.date_input("감상일", value=date.today())
    summary = st.text_area("줄거리")
    brief = st.text_input("요약")
    highlights = st.text_area("인상 깊은 부분")
    note = st.text_area("감상")
    img_url_val = st.text_input("이미지 URL")

    if st.button("✅ 저장"):
        insert_archive((
            category,
            title,
            creator,
            rel_date,
            summary,
            brief,
            highlights,
            note,
            img_url_val,
            str(date.today()),
            str(view_date)
        ))
        st.success("저장 완료")
        st.rerun()

# -------------------------------------------------
# 6. ARCHIVE 탭
# -------------------------------------------------
with tab2:

    all_df = load_all_data()

    if not all_df.empty:

        all_df['v_dt'] = pd.to_datetime(
            all_df['view_date'].fillna(all_df['save_date'])
        )

        all_df = all_df.sort_values(by='v_dt', ascending=False)

        for _, row in all_df.iterrows():
            cols = st.columns([1, 3])
            with cols[0]:
                if row['img_url']:
                    st.image(row['img_url'], use_container_width=True)
            with cols[1]:
                st.subheader(row['title'])
                st.write(row['creator'])
                st.write("감상일:", row['view_date'])

                if st.button("삭제", key=f"del_{row['id']}"):
                    delete_archive(row['id'])
                    st.rerun()

    else:
        st.info("기록이 없습니다.")

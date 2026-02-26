# ==============================
# PRISM v2 - Clean Structured
# ==============================

import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date

# =====================================================
# 1️⃣ CONFIG
# =====================================================

class Config:
    DB_NAME = "archive_prism_v2.db"
    TMDB_API_KEY = st.secrets.get("TMDB_API_KEY", "")

# =====================================================
# 2️⃣ DATABASE LAYER
# =====================================================

class ArchiveDB:

    def __init__(self):
        self.conn = sqlite3.connect(
            Config.DB_NAME,
            check_same_thread=False
        )
        self._init_table()

    def _init_table(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            title TEXT,
            creator TEXT,
            rel_date TEXT,
            venue TEXT,
            summary TEXT,
            img_url TEXT,
            view_date TEXT
        )
        """)

    def insert(self, data: dict):
        self.conn.execute("""
        INSERT INTO archive
        (category,title,creator,rel_date,venue,
         summary,img_url,view_date)
        VALUES (?,?,?,?,?,?,?,?)
        """, (
            data["category"],
            data["title"],
            data["creator"],
            data["rel_date"],
            data["venue"],
            data["summary"],
            data["img_url"],
            data["view_date"]
        ))
        self.conn.commit()

    def fetch_all(self):
        cursor = self.conn.execute(
            "SELECT * FROM archive ORDER BY view_date DESC"
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def delete(self, record_id):
        self.conn.execute(
            "DELETE FROM archive WHERE id=?",
            (record_id,)
        )
        self.conn.commit()


db = ArchiveDB()

# =====================================================
# 3️⃣ SERVICE LAYER
# =====================================================

class MovieService:

    BASE_URL = "https://api.themoviedb.org/3"

    @staticmethod
    def search(query):
        if not Config.TMDB_API_KEY:
            return []

        url = f"{MovieService.BASE_URL}/search/movie"
        params = {
            "api_key": Config.TMDB_API_KEY,
            "query": query,
            "language": "ko-KR"
        }
        res = requests.get(url, params=params)
        if res.status_code != 200:
            return []
        return res.json().get("results", [])

# =====================================================
# 4️⃣ UTIL
# =====================================================

def safe_image(url):
    if url and url.startswith("http"):
        st.image(url, use_container_width=True)

# =====================================================
# 5️⃣ UI COMPONENTS
# =====================================================

def render_write_tab():

    st.subheader("🖋️ WRITE")

    category = st.radio(
        "CATEGORY",
        ["MOVIES", "BOOKS", "MUSIC", "STAGE"],
        horizontal=True
    )

    query = st.text_input("검색")

    if category == "MOVIES" and query:
        results = MovieService.search(query)

        if results:
            options = {
                f"{r['title']} ({r.get('release_date','')[:4]})": r
                for r in results
            }

            selected = st.selectbox("결과 선택", options.keys())

            if st.button("가져오기"):
                data = options[selected]
                st.session_state.api_data = {
                    "title": data["title"],
                    "creator": "",
                    "rel_date": data.get("release_date", ""),
                    "venue": "",
                    "summary": data.get("overview", ""),
                    "img_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}"
                }
                st.rerun()

    st.divider()

    api_data = st.session_state.get("api_data", {})

    img_url = st.text_input("이미지 URL", api_data.get("img_url", ""))
    title = st.text_input("제목", api_data.get("title", ""))
    creator = st.text_input("창작자", api_data.get("creator", ""))
    rel_date = st.text_input("작품 날짜", api_data.get("rel_date", ""))
    venue = st.text_input("장소/플랫폼", api_data.get("venue", ""))
    summary = st.text_area("줄거리", api_data.get("summary", ""))
    view_date = st.date_input("감상일", value=date.today())

    if st.button("저장"):
        db.insert({
            "category": category,
            "title": title,
            "creator": creator,
            "rel_date": rel_date,
            "venue": venue,
            "summary": summary,
            "img_url": img_url,
            "view_date": str(view_date)
        })
        st.success("저장 완료")
        st.session_state.api_data = {}
        st.rerun()


def render_archive_tab():

    st.subheader("📂 ARCHIVE")

    records = db.fetch_all()

    if not records:
        st.info("기록이 없습니다.")
        return

    df = pd.DataFrame(records)
    df["v_dt"] = pd.to_datetime(df["view_date"])

    years = sorted(df["v_dt"].dt.year.unique(), reverse=True)

    selected_year = st.selectbox("연도 선택", years)

    year_df = df[df["v_dt"].dt.year == selected_year]

    for month in range(12, 0, -1):
        month_df = year_df[year_df["v_dt"].dt.month == month]

        if not month_df.empty:
            st.markdown(f"### {month}월")

            cols = st.columns(4)

            for idx, row in enumerate(month_df.to_dict("records")):
                with cols[idx % 4]:
                    safe_image(row["img_url"])
                    if st.button(
                        row["title"][:10],
                        key=f"detail_{row['id']}"
                    ):
                        show_detail_dialog(row)


@st.dialog("상세보기")
def show_detail_dialog(item):

    safe_image(item["img_url"])

    st.markdown(f"## {item['title']}")
    st.write(item["creator"])
    st.write(f"{item['rel_date']} | {item['venue']}")
    st.write(f"감상일: {item['view_date']}")
    st.divider()
    st.write(item["summary"])

    if st.button("삭제"):
        db.delete(item["id"])
        st.success("삭제 완료")
        st.rerun()

# =====================================================
# 6️⃣ MAIN APP
# =====================================================

st.set_page_config(
    layout="wide",
    page_title="PRISM v2",
    page_icon="🌈"
)

st.title("🌈 PRISM v2")

tabs = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tabs[0]:
    render_write_tab()

with tabs[1]:
    render_archive_tab()

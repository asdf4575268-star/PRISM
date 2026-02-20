import streamlit as st
import sqlite3
import requests
import pandas as pd
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime

# =========================
# ✅ 1. 기본 설정
# =========================

st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "archive_prism_total_v4.db")

TMDB_API_KEY = "여기에_본인_TMDB키"
KOPIS_KEY = "여기에_본인_KOPIS키"

if 'cal_year' not in st.session_state:
    st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state:
    st.session_state.cal_month = datetime.now().month
if 'api_data' not in st.session_state:
    st.session_state.api_data = {}

# =========================
# ✅ 2. DB 완전 안전 초기화
# =========================

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
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
        conn.commit()

        # 컬럼 누락 방지 (안전 보강)
        existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(archive)").fetchall()]
        required_cols = ["brief","highlights","note","img_url","view_date"]

        for col in required_cols:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE archive ADD COLUMN {col} TEXT")
        conn.commit()

init_db()

# =========================
# ✅ 3. API 함수 (기존 그대로)
# =========================

def search_books(query):
    headers = {"Authorization": "KakaoAK 여기에_카카오키"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book",
                           headers=headers,
                           params={"query": query})
        return res.json().get("documents", [])
    except:
        return []

def search_apple_music(query):
    try:
        url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
        res = requests.get(url).json().get("results", [])
        result = []
        for m in res:
            is_album = m.get('wrapperType') == 'collection'
            title = m.get('collectionName') if is_album else m.get('trackName')
            result.append({
                "display_name": f"{title} - {m.get('artistName')}",
                "title": title,
                "creator": m.get("artistName"),
                "date": m.get("releaseDate","")[:10],
                "img": m.get("artworkUrl100","").replace("100x100bb","800x800bb"),
                "url": m.get("trackViewUrl","")
            })
        return result
    except:
        return []

def search_tmdb(query, category):
    try:
        type_path = "movie" if category=="MOVIES" else "tv"
        url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
        return requests.get(url).json().get("results", [])
    except:
        return []

def search_kopis(query):
    try:
        url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&rows=10"
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{
            "title": d.findtext("prfnm"),
            "venue": d.findtext("fcltynm"),
            "date": d.findtext("prfpdfrom"),
            "img": d.findtext("poster")
        } for d in root.findall("db")]
    except:
        return []

# =========================
# ✅ 4. DB 저장/로드 안전 함수
# =========================

def insert_record(data):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("""
            INSERT INTO archive
            (category,title,creator,rel_date,summary,brief,highlights,note,img_url,save_date,view_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, data)
            conn.commit()
    except Exception as e:
        st.error(f"DB 저장 오류: {e}")

def load_all():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            return pd.read_sql_query("SELECT * FROM archive", conn)
    except:
        return pd.DataFrame()

# =========================
# ✅ 5. UI (기존 기능 그대로)
# =========================

tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

# -------------------------
# WRITE TAB
# -------------------------
with tab1:

    category = st.radio("📂 CATEGORY",
                        ["BOOKS","MUSIC","MOVIES","SERIES","STAGE"],
                        horizontal=True)

    search_query = st.text_input("검색")

    if search_query:

        if category=="BOOKS":
            res = search_books(search_query)
            if res:
                opts = {r["title"]:r for r in res}
                sel = st.selectbox("선택", list(opts.keys()))
                if st.button("가져오기"):
                    r = opts[sel]
                    st.session_state.api_data = {
                        "title": r["title"],
                        "creator": ", ".join(r.get("authors",[])),
                        "date": r["datetime"][:10],
                        "img": r.get("thumbnail",""),
                        "summary": r.get("contents","")
                    }

        elif category=="MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {r["display_name"]:r for r in res}
                sel = st.selectbox("선택", list(opts.keys()))
                if st.button("가져오기"):
                    r = opts[sel]
                    st.session_state.api_data = r

        elif category=="STAGE":
            res = search_kopis(search_query)
            if res:
                opts = {r["title"]:r for r in res}
                sel = st.selectbox("선택", list(opts.keys()))
                if st.button("가져오기"):
                    r = opts[sel]
                    st.session_state.api_data = r

        else:
            res = search_tmdb(search_query, category)
            if res:
                t_key = "title" if category=="MOVIES" else "name"
                opts = {r.get(t_key):r for r in res}
                sel = st.selectbox("선택", list(opts.keys()))
                if st.button("가져오기"):
                    r = opts[sel]
                    st.session_state.api_data = {
                        "title": r.get(t_key),
                        "creator": "",
                        "date": r.get("release_date",""),
                        "img": f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}",
                        "summary": r.get("overview","")
                    }

    st.divider()

    data = st.session_state.get("api_data",{})

    title = st.text_input("제목", value=data.get("title",""))
    creator = st.text_input("창작자", value=data.get("creator",""))
    rel_date = st.text_input("작품 날짜", value=data.get("date",""))
    view_date = st.date_input("감상일", value=date.today())
    img_url = st.text_input("이미지", value=data.get("img",""))
    summary = st.text_area("줄거리", value=data.get("summary",""))
    brief = st.text_input("요약")
    highlights = st.text_area("인상 깊은 부분")
    note = st.text_area("감상")

    if st.button("✅ 저장"):
        insert_record((
            category,
            title,
            creator,
            rel_date,
            summary,
            brief,
            highlights,
            note,
            img_url,
            str(date.today()),
            str(view_date)
        ))
        st.success("저장 완료")
        st.session_state.api_data = {}

# -------------------------
# ARCHIVE TAB
# -------------------------
with tab2:

    df = load_all()

    if df.empty:
        st.info("기록이 없습니다.")
    else:
        df["dt"] = pd.to_datetime(df["view_date"].fillna(df["save_date"]))
        df = df.sort_values("dt", ascending=False)

        for _, row in df.iterrows():
            with st.expander(f"{row['title']} ({row['view_date']})"):
                if row["img_url"]:
                    st.image(row["img_url"], width=200)
                st.write("Creator:", row["creator"])
                st.write("공개일:", row["rel_date"])
                st.write("요약:", row["brief"])
                st.write("줄거리:", row["summary"])
                st.write("인상 깊은 부분:", row["highlights"])
                st.write("감상:", row["note"])

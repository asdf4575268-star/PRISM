import streamlit as st
from supabase import create_client
import requests
import pandas as pd
from datetime import date, datetime
import re
import xml.etree.ElementTree as ET

# -------------------------------------------------
# 기본 설정
# -------------------------------------------------
st.set_page_config(layout="centered", page_title="PRISM")
st.title("🌈 PRISM")

SUPABASE_URL = st.secrets["https://zfdmzpzcbpwtphvmmybi.supabase.co"]
SUPABASE_KEY = st.secrets["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpmZG16cHpjYnB3dHBodm1teWJpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE4MTc2MDQsImV4cCI6MjA4NzM5MzYwNH0.LYF5Ly15Y5NiWuitcdgv-A34y3_fCH4shM2otDiFOhY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TMDB_API_KEY = "YOUR_TMDB_KEY"
KOPIS_KEY = "YOUR_KOPIS_KEY"

if "user" not in st.session_state:
    st.session_state.user = None

# -------------------------------------------------
# 로그인 영역 (너만 로그인)
# -------------------------------------------------
with st.sidebar:
    st.header("🔐 Admin Login")

    if not st.session_state.user:
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            try:
                res = supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
                st.session_state.user = res.user
                st.success("로그인 성공")
                st.rerun()
            except:
                st.error("로그인 실패")

    else:
        st.success("Admin Mode")
        if st.button("Logout"):
            supabase.auth.sign_out()
            st.session_state.user = None
            st.rerun()

# -------------------------------------------------
# API 함수들 (기존 유지)
# -------------------------------------------------
def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    return requests.get(url).json().get("results", [])

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&rows=20"
    res = requests.get(url)
    root = ET.fromstring(res.content)
    items = root.findall('db')
    return [{
        "title": d.findtext("prfnm"),
        "id": d.findtext("mt20id"),
        "img": d.findtext("poster"),
        "date": d.findtext("prfpdfrom"),
        "venue": d.findtext("fcltynm")
    } for d in items]

# -------------------------------------------------
# DB 함수
# -------------------------------------------------
def fetch_all():
    return supabase.table("contents")\
        .select("*")\
        .order("view_date", desc=True)\
        .execute().data

def insert_content(data):
    supabase.table("contents").insert(data).execute()

def update_content(cid, data):
    supabase.table("contents").update(data).eq("id", cid).execute()

def delete_content(cid):
    supabase.table("contents").delete().eq("id", cid).execute()

# -------------------------------------------------
# 탭
# -------------------------------------------------
tab1, tab2 = st.tabs(["🖋 WRITE", "📂 ARCHIVE"])

# =================================================
# WRITE
# =================================================
with tab1:

    if not st.session_state.user:
        st.info("읽기 전용 모드입니다.")
    else:
        category = st.radio(
            "CATEGORY",
            ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"],
            horizontal=True
        )

        search_query = st.text_input("검색")

        img_url = ""
        creator = ""
        rel_date = ""
        venue = ""
        summary = ""

        if search_query and category in ["MOVIES", "SERIES"]:
            results = search_tmdb(search_query, category)
            if results:
                sel = st.selectbox(
                    "결과 선택",
                    [r.get("title") or r.get("name") for r in results]
                )
                chosen = next(
                    r for r in results
                    if (r.get("title") or r.get("name")) == sel
                )
                img_url = f"https://image.tmdb.org/t/p/w500{chosen.get('poster_path')}"
                summary = chosen.get("overview", "")
                rel_date = chosen.get("release_date") or chosen.get("first_air_date")

        title = st.text_input("제목")
        creator = st.text_input("창작자")
        rel_date = st.text_input("📅 작품 날짜", value=rel_date)
        venue = st.text_input("📍 장소")
        img_url = st.text_input("🖼 이미지 URL", value=img_url)
        summary = st.text_area("📖 줄거리", value=summary)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분")
        note = st.text_area("💬 감상")
        view_date = st.date_input("🍿 감상일", value=date.today())

        if st.button("저장", use_container_width=True):

            insert_content({
                "owner_id": st.session_state.user.id,
                "category": category,
                "title": title,
                "creator": creator,
                "release_date": rel_date,
                "venue": venue,
                "summary": summary,
                "brief": brief,
                "highlights": highlights,
                "note": note,
                "image_url": img_url,
                "view_date": str(view_date)
            })

            st.success("저장 완료")
            st.rerun()

# =================================================
# ARCHIVE
# =================================================
with tab2:

    data = fetch_all()

    if not data:
        st.info("기록이 없습니다.")
    else:
        df = pd.DataFrame(data)
        df["view_date"] = pd.to_datetime(df["view_date"], errors="coerce")
        df = df.sort_values("view_date", ascending=False)

        items = df.to_dict("records")

        COLS = 2  # 모바일 기본

        for i in range(0, len(items), COLS):
            cols = st.columns(COLS)
            for j in range(COLS):
                if i + j < len(items):
                    row = items[i+j]
                    with cols[j]:
                        if row.get("image_url"):
                            st.image(row["image_url"], use_container_width=True)

                        if st.button(
                            row["title"][:10],
                            key=row["id"],
                            use_container_width=True
                        ):
                            show = row

                            st.markdown(f"# {show['title']}")
                            st.write(f"[{show['category']}] {show['creator']}")
                            st.write(show["summary"])
                            st.write("🍿", show["view_date"])

                            if st.session_state.user and \
                               st.session_state.user.id == show["owner_id"]:

                                if st.button("삭제"):
                                    delete_content(show["id"])
                                    st.rerun()



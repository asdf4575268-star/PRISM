import streamlit as st
import requests
import re
import pandas as pd
from datetime import date
from supabase import create_client

# -------------------------------
# 기본 설정
# -------------------------------
st.set_page_config(layout="wide")

# -------------------------------
# Supabase 연결 (기존 값 사용)
# -------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------------
# 데이터 로드
# -------------------------------
def get_all_data():
    res = supabase.table("archive").select("*").execute()
    return pd.DataFrame(res.data)

# -------------------------------
# SCRAP 전용 URL 메타 파싱 (bs4 제거)
# -------------------------------
def crawl_url_metadata(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        html = res.text

        def extract(prop):
            match = re.search(
                rf'<meta[^>]+property=["\']{prop}["\'][^>]+content=["\'](.*?)["\']',
                html,
                re.IGNORECASE
            )
            return match.group(1) if match else ""

        return {
            "title": extract("og:title"),
            "img": extract("og:image"),
            "summary": extract("og:description"),
            "creator": extract("og:site_name")
        }
    except:
        return None

# -------------------------------
# 관리자 여부
# -------------------------------
is_admin = st.session_state.get("is_admin", False)

# -------------------------------
# 탭 구성
# -------------------------------
tab1, tab2 = st.tabs(["WRITE", "ARCHIVE"])

# =========================================================
# WRITE TAB
# =========================================================
with tab1:

    category = st.radio(
        "📂 CATEGORY",
        ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"],
        horizontal=True
    )

    # ---------------------------
    # SCRAP 입력 모드
    # ---------------------------
    if category == "SCRAP":

        if not is_admin:
            st.warning("SCRAP은 관리자 전용입니다.")
            st.stop()

        url_input = st.text_input("🔗 기사 URL 입력")

        if st.button("🔍 자동 입력"):
            data = crawl_url_metadata(url_input)
            if data:
                st.session_state.api_data = {
                    "title": data["title"],
                    "creator": data["creator"],
                    "date": str(date.today()),
                    "img": data["img"],
                    "summary": data["summary"]
                }
                st.success("자동 입력 완료")
                st.rerun()
            else:
                st.error("메타데이터 추출 실패")

    # ---------------------------
    # 기존 API 검색 모드 (SCRAP 제외)
    # ---------------------------
    else:
        search_query = st.text_input("검색어 입력")

        if search_query:
            st.write("여기에 기존 API 검색 로직 그대로 유지")

    # ---------------------------
    # 공통 저장 폼
    # ---------------------------
    if "api_data" in st.session_state:

        data = st.session_state.api_data

        title = st.text_input("제목", value=data.get("title", ""))
        creator = st.text_input("저자/출연", value=data.get("creator", ""))
        view_date = st.date_input("감상일", date.today())
        rating = st.slider("평점", 1, 5, 3)
        note = st.text_area("메모")

        if st.button("저장"):
            supabase.table("archive").insert({
                "category": category,
                "title": title,
                "creator": creator,
                "view_date": str(view_date),
                "rating": rating,
                "note": note,
                "img_url": data.get("img"),
                "summary": data.get("summary")
            }).execute()

            st.success("저장 완료")
            del st.session_state["api_data"]
            st.rerun()

# =========================================================
# ARCHIVE TAB
# =========================================================
with tab2:

    all_df = get_all_data()

    # ALL 탭에서 SCRAP 숨김 (비관리자)
    if not is_admin:
        display_df = all_df[all_df["category"] != "SCRAP"]
    else:
        display_df = all_df

    categories = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
    if is_admin:
        categories.append("SCRAP")

    for c_name in categories:

        st.subheader(c_name)
        df = display_df[display_df["category"] == c_name]

        if df.empty:
            st.write("데이터 없음")
            continue

        for _, row in df.iterrows():
            with st.expander(row["title"]):

                if row["img_url"]:
                    st.image(row["img_url"], width=150)

                st.write("작성자:", row["creator"])
                st.write("감상일:", row["view_date"])
                st.write("평점:", row["rating"])
                st.write("요약:", row["summary"])
                st.write("메모:", row["note"])

        # ---------------------------
        # SCRAP 주간 대시보드 (관리자)
        # ---------------------------
        if is_admin and c_name == "SCRAP":

            scrap_df = df.copy()

            if not scrap_df.empty:
                st.divider()
                st.subheader("📰 SCRAP Weekly")

                scrap_df["v_dt"] = pd.to_datetime(scrap_df["view_date"])
                weekly = scrap_df.groupby(pd.Grouper(key="v_dt", freq="W-MON"))

                # 해시태그 추출
                tags = []
                for t in scrap_df["note"]:
                    if t:
                        tags.extend(re.findall(r"#\w+", t))

                if tags:
                    st.markdown("### 🏷️ Hashtags")
                    st.write(" ".join(sorted(set(tags))))

                for week, group in weekly:
                    if not group.empty:
                        st.markdown(f"### 📅 {week.date()} 주간")

                        for _, row in group.iterrows():
                            with st.expander(row["title"]):
                                if row["img_url"]:
                                    st.image(row["img_url"], width=150)
                                st.write(row["summary"])
                                st.write(row["note"])

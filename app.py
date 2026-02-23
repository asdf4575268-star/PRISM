import streamlit as st
import pandas as pd
import requests
from datetime import date
from supabase import create_client, Client

# -------------------------
# 기본 설정
# -------------------------
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈 PRISM")

# -------------------------
# 🔑 Supabase 연결
# -------------------------
SUPABASE_URL = "여기에_프로젝트_URL"
SUPABASE_KEY = "여기에_service_role_key"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# 📌 데이터 함수
# -------------------------

def insert_data(data):
    return supabase.table("archive").insert(data).execute()

def get_all_data():
    res = supabase.table("archive").select("*").order("id", desc=True).execute()
    return pd.DataFrame(res.data)

def delete_item(item_id):
    return supabase.table("archive").delete().eq("id", item_id).execute()

def update_item(item_id, new_data):
    return supabase.table("archive").update(new_data).eq("id", item_id).execute()


# -------------------------
# 🖋 WRITE 탭
# -------------------------
tab1, tab2 = st.tabs(["🖋 WRITE", "📂 ARCHIVE"])

with tab1:

    category = st.selectbox("카테고리", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"])
    title = st.text_input("제목")
    creator = st.text_input("창작자")
    rel_date = st.text_input("작품 날짜")
    venue = st.text_input("장소 / 출판사 / 플랫폼")
    summary = st.text_area("줄거리")
    brief = st.text_input("요약")
    highlights = st.text_area("인상 깊은 부분")
    note = st.text_area("감상")
    img_url = st.text_input("이미지 URL")
    view_date = st.date_input("감상일", value=date.today())

    if st.button("저장", use_container_width=True):
        try:
            data = {
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
                "save_date": str(date.today()),
                "view_date": str(view_date),
            }

            insert_data(data)
            st.success("✅ 저장 완료")
            st.rerun()

        except Exception as e:
            st.error(f"❌ 저장 실패: {e}")


# -------------------------
# 📂 ARCHIVE 탭
# -------------------------
with tab2:

    try:
        df = get_all_data()
    except Exception as e:
        st.error(f"❌ 데이터 로드 실패: {e}")
        st.stop()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        categories = ["ALL"] + sorted(df["category"].unique().tolist())
        selected_cat = st.selectbox("카테고리 선택", categories)

        if selected_cat != "ALL":
            df = df[df["category"] == selected_cat]

        for _, row in df.iterrows():
            with st.container():
                col1, col2 = st.columns([1, 4])

                with col1:
                    if row["img_url"]:
                        st.image(row["img_url"], use_container_width=True)

                with col2:
                    st.subheader(row["title"])
                    st.write(f"**{row['category']}** | {row['creator']}")
                    st.write(f"📅 {row['rel_date']} | 🍿 {row['view_date']}")
                    st.write(row["brief"])

                    c1, c2 = st.columns(2)

                    if c1.button("삭제", key=f"del_{row['id']}"):
                        delete_item(row["id"])
                        st.rerun()

                    if c2.button("수정", key=f"edit_{row['id']}"):
                        st.session_state["edit_id"] = row["id"]

        # -------------------------
        # 수정 모드
        # -------------------------
        if "edit_id" in st.session_state:
            edit_row = df[df["id"] == st.session_state["edit_id"]].iloc[0]

            st.divider()
            st.subheader("✏️ 수정")

            n_title = st.text_input("제목", edit_row["title"])
            n_creator = st.text_input("창작자", edit_row["creator"])
            n_note = st.text_area("감상", edit_row["note"])

            if st.button("수정 저장"):
                update_item(
                    edit_row["id"],
                    {
                        "title": n_title,
                        "creator": n_creator,
                        "note": n_note,
                    },
                )
                del st.session_state["edit_id"]
                st.success("수정 완료")
                st.rerun()

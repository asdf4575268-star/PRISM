import streamlit as st
from supabase import create_client, Client
from datetime import date

# -------------------------
# Supabase 연결
# -------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
ADMIN_EMAIL = st.secrets["ADMIN_EMAIL"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="PRISM", layout="wide")

# -------------------------
# 로그인
# -------------------------
if "user" not in st.session_state:
    st.session_state.user = None

def login():
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
        except Exception as e:
            st.error("로그인 실패")

def logout():
    supabase.auth.sign_out()
    st.session_state.user = None
    st.rerun()

# -------------------------
# 권한 체크
# -------------------------
def is_admin():
    if st.session_state.user:
        return st.session_state.user.email == ADMIN_EMAIL
    return False

# -------------------------
# DB 함수
# -------------------------
def fetch_all():
    try:
        response = supabase.table("contents").select("*").order("created_at", desc=True).execute()
        return response.data
    except Exception as e:
        st.error("데이터 로드 실패")
        return []

def insert_content(data):
    try:
        supabase.table("contents").insert(data).execute()
        st.success("저장 완료")
    except Exception as e:
        st.error("저장 실패")

def update_content(content_id, data):
    try:
        supabase.table("contents").update(data).eq("id", content_id).execute()
        st.success("수정 완료")
    except Exception as e:
        st.error("수정 실패")

def delete_content(content_id):
    try:
        supabase.table("contents").delete().eq("id", content_id).execute()
        st.success("삭제 완료")
    except Exception as e:
        st.error("삭제 실패")

# -------------------------
# UI
# -------------------------
st.title("PRISM")

if st.session_state.user:
    st.sidebar.write(f"로그인: {st.session_state.user.email}")
    if st.sidebar.button("Logout"):
        logout()
else:
    st.sidebar.subheader("Admin Login")
    login()

tab1, tab2 = st.tabs(["ARCHIVE", "WRITE"])

# -------------------------
# ARCHIVE (모두 읽기 가능)
# -------------------------
with tab1:
    data = fetch_all()

    if not data:
        st.info("데이터 없음")

    for item in data:
        with st.container():
            st.subheader(item["title"])
            st.caption(item.get("creator", ""))
            st.write(item.get("summary", ""))

            if item.get("image_url"):
                st.image(item["image_url"], use_column_width=True)

            if is_admin():
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("삭제", key=f"del_{item['id']}"):
                        delete_content(item["id"])
                        st.rerun()
                with col2:
                    if st.button("수정", key=f"edit_{item['id']}"):
                        st.session_state.edit_id = item["id"]

# -------------------------
# WRITE (관리자만)
# -------------------------
with tab2:
    if not is_admin():
        st.warning("작성 권한 없음")
    else:
        st.subheader("콘텐츠 작성")

        title = st.text_input("제목")
        category = st.text_input("카테고리")
        creator = st.text_input("제작자")
        summary = st.text_area("요약")
        image_url = st.text_input("이미지 URL")
        view_date = st.date_input("관람일", value=date.today())

        if st.button("저장"):
            new_data = {
                "title": title,
                "category": category,
                "creator": creator,
                "summary": summary,
                "image_url": image_url,
                "view_date": str(view_date),
                "owner_id": st.session_state.user.id
            }
            insert_content(new_data)
            st.rerun()

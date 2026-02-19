import streamlit as st
import sqlite3
import requests
from datetime import date

# --- [1. 카카오 도서 검색 함수] ---
def search_books_kakao(query):
    if not query: return []
    # 사용자 REST API 키 적용
    KAKAO_API_KEY = "a356895a3aae4f0acf9f4ee884d90a6a" 
    url = "https://dapi.kakao.com/v3/search/book"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query, "size": 10}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            return response.json().get("documents", [])
        return []
    except:
        return []

# --- [2. UI 구성: 기본 입력창 중심] ---
st.set_page_config(layout="wide")

# 검색 섹션
search_query = st.text_input("🔍 도서 검색", placeholder="제목이나 저자 입력 후 엔터")

if search_query:
    books = search_books_kakao(search_query)
    if books:
        book_options = {f"📚 {b['title']} ({', '.join(b['authors'])})": b for b in books}
        selected_label = st.selectbox("결과 선택", book_options.keys())
        
        if st.button("✨ 데이터 불러오기"):
            st.session_state.api_data = book_options[selected_label]
    else:
        st.info("검색 결과가 없습니다.")

st.divider()

# 데이터 연동 및 입력 섹션
data = st.session_state.get('api_data', {})

col1, col2 = st.columns([0.7, 0.3])

with col1:
    # 연동되는 입력창들
    title = st.text_input("활동명 (제목)", value=data.get('title', ''))
    creator = st.text_input("창작자 (작가)", value=", ".join(data.get('authors', [])) if 'authors' in data else "")
    release_date = st.text_input("날짜 (출판일)", value=data.get('datetime', '')[:10])
    
    impression = st.text_area("인상 깊은 부분 (수동 입력)")
    note = st.text_area("감상 노트 (자동 연동)", value=data.get('contents', ''), height=200)

with col2:
    # 이미지 확인용
    img_url = data.get('thumbnail', '')
    if img_url:
        st.image(img_url, caption="표지 이미지")
    
    # 저장 버튼
    if st.button("✅ 저장하기", use_container_width=True):
        # DB 저장 로직 (필요 시 유지)
        st.success("입력된 정보가 저장되었습니다.")

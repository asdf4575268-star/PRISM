import streamlit as st
import sqlite3
import requests
from datetime import date

# --- [1. 카카오 도서 검색 함수] ---
def search_books_kakao(query):
    if not query: return []
    KAKAO_API_KEY = "a356895a3aae4f0acf9f4ee884d90a6a" 
    url = "https://dapi.kakao.com/v3/search/book"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query, "size": 8}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            return response.json().get("documents", [])
        return []
    except:
        return []

# --- [2. 디자인 설정] ---
st.set_page_config(layout="wide")
st.markdown("""
    <style>
    .title-text { font-size: 70px !important; font-weight: 900; line-height: 1.1; margin-bottom: 10px; }
    .date-text { font-size: 30px !important; color: #888; }
    .number-text { font-size: 60px !important; font-weight: bold; color: #ff4b4b; }
    </style>
    """, unsafe_allow_html=True)

# --- [3. 메인 입력 루틴] ---
col1, col2 = st.columns([0.6, 0.4])

with col1:
    # 검색창
    search_query = st.text_input("🔍 도서 검색", placeholder="제목이나 저자를 입력하고 엔터를 누르세요")
    
    if search_query:
        books = search_books_kakao(search_query)
        if books:
            # 검색 결과 선택
            book_options = {f"📚 {b['title']} ({', '.join(b['authors'])})": b for b in books}
            selected_label = st.selectbox("결과 선택", book_options.keys())
            
            if st.button("✨ 데이터 불러오기"):
                st.session_state.api_data = book_options[selected_label]
        else:
            st.info("검색 결과가 없습니다.")

    # 자동 입력되는 필드들
    data = st.session_state.get('api_data', {})
    st.divider()
    
    # 활동명 (70px 반영)
    title_val = st.text_input("활동명", value=data.get('title', ''))
    st.markdown(f'<p class="title-text">{title_val if title_val else "PRISM"}</p>', unsafe_allow_html=True)
    
    creator = st.text_input("창작자", value=", ".join(data.get('authors', [])) if 'authors' in data else "")
    release_date = st.text_input("날짜", value=data.get('datetime', '')[:10])
    
    impression = st.text_area("인상 깊은 부분")
    note = st.text_area("감상 노트", value=data.get('contents', ''), height=150)

with col2:
    # 상단 날짜 (30px)
    st.markdown(f'<p class="date-text">{date.today()}</p>', unsafe_allow_html=True)
    
    # 만족도 (60 bpm)
    score = st.slider("만족도", 0, 100, 80)
    st.markdown(f'<span class="number-text">{score}</span> <span style="font-size:24px;">bpm</span>', unsafe_allow_html=True)
    
    st.divider()
    # 이미지 자동 표시
    img_url = data.get('thumbnail', '')
    if img_url:
        st.image(img_url, use_container_width=True)
        st.caption("커버 이미지")
    
    if st.button("✅ 아카이브 저장", use_container_width=True):
        # 여기에 기존 sqlite3 저장 로직을 연결하면 됩니다.
        st.success("데이터가 성공적으로 입력되었습니다.")

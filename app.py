import streamlit as st
import sqlite3
import requests
from datetime import date

# --- [1. 스타일 설정] ---
st.set_page_config(layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; margin-bottom:-20px; }
    .date-text { font-size: 30px; color: gray; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; }
    </style>
    """, unsafe_allow_html=True)

# --- [2. 검색 및 연동 함수] ---
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

# --- [3. 메인 레이아웃] ---
st.title("📚 데이터 기반 아카이빙")

# 검색바 (상단 고정)
search_query = st.text_input("🔍 도서 검색 (제목이나 저자를 입력하세요)")
if search_query:
    books = search_books(search_query)
    if books:
        # 검색 결과 선택
        options = {f"{b['title']} - {b['authors'][0] if b['authors'] else ''}": b for b in books}
        selected_book = st.selectbox("검색 결과 중 선택하세요", list(options.keys()))
        if st.button("✨ 데이터 연동하기"):
            st.session_state.api_data = options[selected_book]
            st.rerun()

st.divider()

# 연동된 데이터 불러오기
data = st.session_state.get('api_data', {})

# 레이아웃 분리
col_left, col_right = st.columns([0.4, 0.6])

with col_left:
    st.subheader("📍 연동 정보")
    # 1. 연동 시 자동으로 데이터가 채워짐
        # 이미지: 원본 크기 유지
    img_url = data.get('thumbnail', '')
    if img_url:
        st.image(img_url, caption="연동 이미지", use_container_width=False)
    title = st.text_input("활동명 (제목)", value=data.get('title', ''))
    creator = st.text_input("창작자 (작가)", value=", ".join(data.get('authors', [])) if 'authors' in data else "")
    release_date = st.text_input("날짜", value=data.get('datetime', '')[:10] if data.get('datetime') else "")
    

with col_right:
    st.subheader("🖋️ 아카이빙 기록")
    # 2. 요약 및 인상 깊은 부분 중심
    summary = st.text_area("📖 핵심 요약", height=100, placeholder="전체 내용을 한 줄로 요약해 보세요.")
    highlights = st.text_area("✨ 인상 깊은 부분 (쪽수 포함)", height=150, placeholder="p.45 - 이 문장이 특히 와닿았다.")
    thought = st.text_area("💬 감상 및 노트", value=data.get('contents', ''), height=200)
    
    # 하단 시각화 데이터 (폰트 설정 적용)
    st.divider()
    st.markdown(f'<p class="act-name">{title if title else "활동명"}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="date-text">{release_date if release_date else "2026-00-00"}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)

    if st.button("✅ 최종 아카이브 저장", use_container_width=True):
        # 여기에 DB 저장 로직을 추가하면 끝!
        st.success(f"'{title}' 기록이 성공적으로 보관되었습니다.")


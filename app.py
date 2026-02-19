import streamlit as st
import sqlite3
from datetime import date

# --- [1. 기본 설정 및 CSS] ---
st.set_page_config(layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; }
    .date-text { font-size: 30px; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; }
    </style>
    """, unsafe_allow_html=True)

# --- [2. 메인 화면 구성] ---
st.title("📚 기록 아카이브")

# 검색 및 데이터 연동 (검색 부분 생략, data는 api 결과물이라 가정)
search_query = st.text_input("🔍 도서 검색")
# ... (기존 검색 로직 동일) ...

data = st.session_state.get('api_data', {})

st.divider()

# 레이아웃 분리
col_left, col_right = st.columns([0.4, 0.6])

with col_left:
    st.subheader("📍 기본 정보")
    title = st.text_input("활동명 (제목)", value=data.get('title', ''))
    creator = st.text_input("창작자 (작가)", value=", ".join(data.get('authors', [])) if 'authors' in data else "")
    release_date = st.text_input("날짜", value=data.get('datetime', '')[:10] if data.get('datetime') else "")
    
    # 이미지: 원래 크기대로 (use_container_width=False)
    img_url = data.get('thumbnail', '')
    if img_url:
        st.image(img_url, caption="연동된 이미지 (원본)", use_container_width=False)

with col_right:
    st.subheader("🖋️ 기록 및 요약")
    # 아카이빙 핵심 항목들
    summary = st.text_area("📖 핵심 요약", height=100)
    highlights = st.text_area("✨ 인상 깊은 부분 (쪽수 포함)", placeholder="예: p.123 - 이 문장이 좋았다", height=150)
    thought = st.text_area("💬 감상 및 노트", value=data.get('contents', ''), height=200)
    
    # 하단 수치 표시 (km, bpm)
    st.markdown(f'<p class="act-name">{title}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="date-text">{release_date}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)

    if st.button("✅ 아카이브 최종 저장", use_container_width=True):
        # 저장 로직 (DB insert)
        st.success(f"'{title}' 아카이빙 완료!")

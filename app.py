import streamlit as st
import sqlite3
import pandas as pd
import requests
from datetime import date

# --- [1. 스타일 설정] ---
st.set_page_config(layout="wide")
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; margin-bottom: -20px; }
    .date-text { font-size: 30px; color: #666; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; }
    </style>
    """, unsafe_allow_html=True)

def init_db():
    conn = sqlite3.connect('prism_archive.db')
    conn.execute('CREATE TABLE IF NOT EXISTS archive (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, creator TEXT, release_date TEXT, impression TEXT, note TEXT, image_url TEXT, save_date TEXT)')
    conn.commit()
    return conn

def search_books_kakao(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

# --- [2. 메인 로직] ---
init_db()
tab1, tab2 = st.tabs(["🖋️ 데이터 입력", "📂 보관함 확인"])

with tab1:
    search_query = st.text_input("🔍 도서 검색")
    if search_query:
        books = search_books_kakao(search_query)
        if books:
            book_options = {f"📚 {b['title']}": b for b in books}
            sel = st.selectbox("결과 선택", list(book_options.keys()))
            if st.button("✨ 데이터 불러오기"): st.session_state.api_data = book_options[sel]

    st.divider()
    data = st.session_state.get('api_data', {})
    
    # 레이아웃: 이전 버전의 편의성 + 사이드 메뉴 구성
    col1, col2 = st.columns([0.6, 0.4])

    with col1:
        title = st.text_input("활동명 (제목)", value=data.get('title', ''))
        creator = st.text_input("창작자 (작가)", value=", ".join(data.get('authors', [])))
        release_date = st.text_input("날짜", value=data.get('datetime', '')[:10])
        impression = st.text_area("인상 깊은 부분", height=100)
        note = st.text_area("감상 노트", value=data.get('contents', ''), height=200)

    with col2:
        st.subheader("🖼️ 미리보기 & 설정")
        img_url = data.get('thumbnail', '')
        if img_url:
            # [중요] 흐릿함 방지: 썸네일을 카카오 고화질 원본 규격으로 치환
            high_res_img = img_url.replace("fname=t1.daumcdn.net", "fname=t1.daumcdn.net").replace("width=120", "width=1000").replace("height=174", "height=0")
            st.image(high_res_img, use_container_width=True)
        
        # 선명한 고화질 텍스트 출력
        st.markdown(f'<p class="act-name">{title if title else "활동명"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{release_date if release_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 아카이브에 최종 저장", use_container_width=True):
            conn = sqlite3.connect('prism_archive.db')
            conn.execute("INSERT INTO archive (title, creator, release_date, impression, note, image_url, save_date) VALUES (?,?,?,?,?,?,?)",
                         (title, creator, release_date, impression, note, img_url, str(date.today())))
            conn.commit()
            st.success("저장 완료!")

# 보관함 확인 생략 (기존 로직 유지)

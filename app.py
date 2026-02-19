import streamlit as st
import sqlite3
import pandas as pd
import requests
from datetime import date

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide")
# 요청하신 폰트 및 글자 크기(90, 60, 30) 반영
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; }
    .date-text { font-size: 30px; color: gray; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; }
    .side-menu { background-color: #f0f2f6; padding: 20px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

def init_db():
    conn = sqlite3.connect('prism_archive.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS archive (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, creator TEXT, release_date TEXT, impression TEXT, note TEXT, image_url TEXT, save_date TEXT)''')
    conn.commit()
    return conn

def search_books_kakao(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query, "size": 10})
    return res.json().get("documents", []) if res.status_code == 200 else []

# --- [2. 메인 로직] ---
init_db()
tab1, tab2 = st.tabs(["🖋️ 데이터 입력", "📂 보관함 확인"])

with tab1:
    search_query = st.text_input("🔍 도서 검색", placeholder="제목 입력 후 엔터")
    if search_query:
        books = search_books_kakao(search_query)
        if books:
            book_options = {f"{b['title']}": b for b in books}
            sel = st.selectbox("결과 선택", list(book_options.keys()))
            if st.button("✨ 데이터 불러오기"): st.session_state.api_data = book_options[sel]

    st.divider()
    data = st.session_state.get('api_data', {})
    
    # 레이아웃: 왼쪽(이미지 및 고화질 텍스트), 오른쪽(사이드 메뉴 및 설정)
    col_main, col_side = st.columns([0.7, 0.3])

    with col_main:
        img_url = data.get('thumbnail', '').replace("width=120", "width=1000") # 고화질 치환
        if img_url:
            st.image(img_url, use_container_width=True)
            # 고화질 텍스트 오버레이 효과
            st.markdown(f'<p class="act-name">{data.get("title", "활동명")}</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="date-text">{data.get("datetime", str(date.today()))[:10]}</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)

    with col_side:
        st.markdown('<div class="side-menu">', unsafe_allow_html=True)
        st.subheader("⚙️ 커스텀 & OCR")
        title = st.text_input("제목 수정", value=data.get('title', ''))
        note = st.text_area("감상 노트", value=data.get('contents', ''), height=150)
        
        if st.button("✅ 최종 저장", use_container_width=True):
            conn = sqlite3.connect('prism_archive.db')
            conn.execute("INSERT INTO archive (title, creator, release_date, note, image_url, save_date) VALUES (?,?,?,?,?,?)",
                         (title, data.get('authors',[''])[0], data.get('datetime','')[:10], note, img_url, str(date.today())))
            conn.commit()
            st.success("저장 완료!")
        st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    # 보관함 확인 생략 (기존과 동일하되 위 스타일 적용됨)
    conn = sqlite3.connect('prism_archive.db')
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    st.dataframe(df, use_container_width=True)

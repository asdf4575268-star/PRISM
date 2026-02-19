import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date

# --- [1. 스타일 및 DB 설정] ---
st.set_page_config(layout="wide", page_title="My Prism Archive")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; }
    
    /* 갤러리 이미지 마우스 오버 효과 */
    div[data-testid="stImage"] > img {
        border-radius: 10px;
        transition: transform 0.3s ease;
        cursor: pointer;
    }
    div[data-testid="stImage"] > img:hover {
        transform: scale(1.03);
        box-shadow: 0px 4px 15px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_v6.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                     rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')
    conn.commit()
    conn.close()

# --- [상세 보기 팝업 함수] ---
@st.dialog("📖 아카이브 상세 기록", width="large")
def show_details(item):
    col_img, col_txt = st.columns([0.4, 0.6])
    with col_img:
        if item['img_url']:
            st.image(item['img_url'], use_container_width=True)
        st.write(f"**카테고리:** {item['category']}")
        st.write(f"**창작자:** {item['creator']}")
        st.write(f"**활동일:** {item['rel_date']}")
        st.write(f"**저장일:** {item['save_date']}")
    
    with col_txt:
        st.subheader(item['title'])
        st.info(f"**📖 요약/평**\n\n{item['summary']}")
        st.warning(f"**✨ 하이라이트**\n\n{item['highlights']}")
        st.write(f"**💬 감상**\n\n{item['note']}")
        
        st.divider()
        if st.button("🗑️ 이 기록 삭제", f"del_{item['id']}"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

# --- [API 및 초기화] ---
init_db()

tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 보관함 (폴더별)"])

# --- [Tab 1: 입력] (기존 로직 유지) ---
with tab1:
    category = st.radio("📂 카테고리 선택", ["도서", "음악"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색", placeholder=f"제목/아티스트 입력")
    # ... (중략: 검색/연동 로직은 이전과 동일) ...
    # (코드 간결화를 위해 핵심 저장 부분만 표시)
    data = st.session_state.get('api_data', {})
    col_l, col_r = st.columns([0.4, 0.6])
    with col_l:
        if data.get('img'): st.image(data['img'], width=200)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("아티스트/작가", value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', ''))
    with col_r:
        summary = st.text_area("📖 요약/평")
        highlights = st.text_area("✨ 하이라이트")
        note = st.text_area("💬 감상", value=data.get('note', ''))
        if st.button("✅ 최종 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, highlights, note, data.get('img', ''), str(date.today())))
            st.success("저장 완료!")
            st.rerun()

# --- [Tab 2: 보관함 폴더] ---
with tab2:
    sub_book, sub_music = st.tabs(["📚 도서", "🎸 음악"])
    
    def display_folder(cat):
        with sqlite3.connect(DB_NAME) as conn:
            df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{cat}' ORDER BY id DESC", conn)
        
        if df.empty:
            st.info("기록이 없습니다.")
            return

        # 4열 그리드
        cols = st.columns(4)
        for idx, row in df.iterrows():
            with cols[idx % 4]:
                # 이미지 출력
                if row['img_url']:
                    st.image(row['img_url'], use_container_width=True)
                # 제목 버튼을 누르면 팝업 열림
                if st.button(row['title'], key=f"item_{row['id']}", use_container_width=True):
                    show_details(row)

    with sub_book: display_folder("도서")
    with sub_music: display_folder("음악")

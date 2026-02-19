import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date

# --- [1. 스타일 및 DB 설정] ---
st.set_page_config(layout="wide", page_title="My Archive")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; }
    .sidebar-content { background-color: #f8f9fa; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

def init_db():
    conn = sqlite3.connect('archive_final.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, creator TEXT, 
                     rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')
    conn.commit()
    return conn

def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

init_db()

# --- [2. 메인 화면: 탭 구성] ---
tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 전체 목록 및 상세"])

with tab1:
    # 검색 및 연동
    search_query = st.text_input("🔍 도서 검색", placeholder="연동할 책 제목을 입력하세요")
    if search_query:
        books = search_books(search_query)
        if books:
            options = {f"{b['title']} ({b['authors'][0] if b['authors'] else '미상'})": b for b in books}
            sel = st.selectbox("검색 결과 선택", list(options.keys()))
            if st.button("✨ 데이터 연동"):
                st.session_state.api_data = options[sel]
                st.rerun()

    data = st.session_state.get('api_data', {})
    st.divider()

    # 입력 레이아웃 (왼쪽: 정보/사진, 오른쪽: 요약/감상)
    col_l, col_r = st.columns([0.4, 0.6])
    
    with col_l:
        img_url = data.get('thumbnail', '')
        if img_url:
            st.image(img_url, use_container_width=False, caption="원본 크기 유지")
        title = st.text_input("활동명 (제목)", value=data.get('title', ''))
        creator = st.text_input("창작자 (작가)", value=", ".join(data.get('authors', [])) if 'authors' in data else "")
        rel_date = st.text_input("날짜", value=data.get('datetime', '')[:10] if data.get('datetime') else "")
        
    with col_r:
        summary = st.text_area("📖 요약", height=80, placeholder="내용을 요약해 주세요.")
        highlights = st.text_area("✨ 인상 깊은 부분 (쪽수 포함)", height=150, placeholder="p.123 - 문장 내용")
        note = st.text_area("💬 감상", value=data.get('contents', ''), height=150)
        
        if st.button("✅ 아카이브 최종 저장", use_container_width=True):
            conn = sqlite3.connect('archive_final.db')
            conn.execute("""INSERT INTO archive (title, creator, rel_date, summary, highlights, note, img_url, save_date) 
                            VALUES (?,?,?,?,?,?,?,?)""",
                         (title, creator, rel_date, summary, highlights, note, img_url, str(date.today())))
            conn.commit()
            st.success("저장되었습니다!")
            st.rerun()

with tab2:
    st.subheader("🗂️ 전체 아카이빙 상세 보기")
    conn = sqlite3.connect('archive_final.db')
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    conn.close()

    if not df.empty:
        # 제목 목록에서 선택 시 상세 정보 표시
        selected_id = st.selectbox("보고 싶은 기록을 선택하세요", df['title'].tolist())
        item = df[df['title'] == selected_id].iloc[0]
        
        st.divider()
        det_l, det_r = st.columns([0.3, 0.7])
        
        with det_l:
            if item['img_url']:
                st.image(item['img_url'], use_container_width=False)
            st.write(f"**작가:** {item['creator']}")
            st.write(f"**출판/활동일:** {item['rel_date']}")
            st.write(f"**저장일:** {item['save_date']}")
        
        with det_r:
            st.info(f"**📖 핵심 요약**\n\n{item['summary']}")
            st.warning(f"**✨ 인상 깊은 부분**\n\n{item['highlights']}")
            st.write(f"**💬 감상 노트**\n\n{item['note']}")
            
            if st.button("🗑️ 이 기록 삭제"):
                conn = sqlite3.connect('archive_final.db')
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
                conn.commit()
                st.rerun()
    else:
        st.info("아직 저장된 아카이브가 없습니다.")










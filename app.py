import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="My Prism Archive")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; }
    
    div[data-testid="stImage"] > img {
        border-radius: 12px;
        transition: transform 0.3s ease;
        cursor: pointer;
        border: 1px solid #eee;
    }
    div[data-testid="stImage"] > img:hover { transform: scale(1.05); }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_stable.db'

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')

# --- [2. API 연동 함수들] ---

def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=15&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url)
        return res.json().get("results", [])
    except: return []

# --- [3. 상세 보기 팝업] ---
@st.dialog("📋 아카이브 상세 기록", width="large")
def show_details(item):
    col_img, col_txt = st.columns([0.4, 0.6])
    with col_img:
        if item['img_url']: st.image(item['img_url'], use_container_width=True)
        st.caption(f"Category: {item['category']} | 저장일: {item['save_date']}")
    with col_txt:
        st.subheader(item['title'])
        st.write(f"**창작자:** {item['creator']}")
        st.write(f"**날짜:** {item['rel_date']}")
        st.divider()
        st.info(f"**📖 요약/정보**\n\n{item['summary']}")
        st.warning(f"**✨ 하이라이트/명대사**\n\n{item['highlights']}")
        st.write(f"**💬 개인적 감상**\n\n{item['note']}")
        if st.button("🗑️ 삭제하기", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

init_db()

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 보관함 폴더"])

with tab1:
    category = st.radio("📂 카테고리 선택", ["도서", "음악"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 제목을 입력하세요", placeholder="검색 후 데이터 연동을 눌러주세요")
    
    if search_query:
        if category == "도서":
            res = search_books(search_query)
            if res:
                opts = {f"📚 {b['title']} ({b['authors'][0] if b['authors'] else '미상'})": b for b in res}
                sel = st.selectbox("검색 결과 선택", list(opts.keys()))
                if st.button("✨ 데이터 연동"):
                    b = opts[sel]
                    st.session_state.api_data = {
                        'title': b['title'], 'creator': b['authors'][0] if b['authors'] else "미상", 
                        'date': b['datetime'][:10], 'img': b['thumbnail'], 'note': b['contents']
                    }
                    st.rerun()
        elif category == "음악":
            res = search_apple_music(search_query)
            if res:
                opts = {f"🎵 {m.get('trackName', m.get('collectionName'))} - {m['artistName']}": m for m in res}
                sel = st.selectbox("검색 결과 선택", list(opts.keys()))
                if st.button("✨ 데이터 연동"):
                    m = opts[sel]
                    artwork = m.get('artworkUrl100', '').replace('100x100bb', '600x600bb')
                    st.session_state.api_data = {
                        'title': m.get('trackName', m.get('collectionName')), 'creator': m['artistName'], 
                        'date': m['releaseDate'][:10], 'img': artwork, 'note': ''
                    }
                    st.rerun()

    data = st.session_state.get('api_data', {})
    st.divider()
    col_l, col_r = st.columns([0.4, 0.6])
    with col_l:
        if data.get('img'): st.image(data['img'], use_container_width=False)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자 (작가/아티스트)", value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', ''))
        
    with col_r:
        summary = st.text_area("📖 요약/정보", value=data.get('note', ''), height=80)
        highlights = st.text_area("✨ 하이라이트", height=120)
        note = st.text_area("💬 개인적 감상", height=120)
        
        # 가이드 디자인 (90, 30, 60 규칙)
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 최종 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, highlights, note, data.get('img', ''), str(date.today())))
            st.success("보관함에 저장되었습니다!")
            st.session_state.api_data = {} # 저장 후 데이터 초기화
            st.rerun()

with tab2:
    sub_tabs = st.tabs(["📚 도서 폴더", "🎸 음악 폴더"])
    sub_cats = ["도서", "음악"]
    
    for i, tab in enumerate(sub_tabs):
        with tab:
            with sqlite3.connect(DB_NAME) as conn:
                df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{sub_cats[i]}' ORDER BY id DESC", conn)
            if df.empty:
                st.info(f"저장된 {sub_cats[i]} 기록이 없습니다.")
            else:
                cols = st.columns(4)
                for idx, row in df.iterrows():
                    with cols[idx % 4]:
                        if row['img_url']: st.image(row['img_url'], use_container_width=True)
                        if st.button(row['title'], key=f"btn_{row['id']}", use_container_width=True):
                            show_details(row)

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
    
    /* 카드형 스타일 */
    .img-card {
        border-radius: 10px;
        transition: transform 0.2s;
        cursor: pointer;
    }
    .img-card:hover {
        transform: scale(1.05);
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_v6.db' # 새로운 구조를 위해 버전 업

def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                     rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')
    conn.commit()
    conn.close()

def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=15&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url)
        return res.json().get("results", [])
    except: return []

init_db()

# --- [2. 메인 화면 탭] ---
tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 보관함 (폴더별 보기)"])

# --- [Tab 1: 입력부] ---
with tab1:
    category = st.radio("📂 카테고리 선택", ["도서", "음악"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색", placeholder=f"연동할 {category} 제목/아티스트를 입력하세요")
    
    if search_query:
        if category == "도서":
            results = search_books(search_query)
            if results:
                options = {f"📚 {b['title']} ({b['authors'][0]})": b for b in results if b['authors']}
                sel = st.selectbox("검색 결과 선택", list(options.keys()))
                if st.button("✨ 데이터 연동"):
                    b = options[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': b['authors'][0], 'date': b['datetime'][:10], 'img': b['thumbnail'], 'note': b['contents']}
                    st.rerun()
        else: 
            results = search_apple_music(search_query)
            if results:
                options = {f"{('🎵' if m.get('wrapperType')=='track' else '💿')} {m.get('trackName', m.get('collectionName'))} - {m['artistName']}": m for m in results}
                sel = st.selectbox("검색 결과 선택", list(options.keys()))
                if st.button("✨ 애플뮤직 데이터 연동"):
                    m = options[sel]
                    name = m.get('trackName', m.get('collectionName'))
                    artwork_url = m.get('artworkUrl100', '').replace('100x100bb', '600x600bb')
                    st.session_state.api_data = {'title': name, 'creator': m['artistName'], 'date': m['releaseDate'][:10], 'img': artwork_url, 'note': ''}
                    st.rerun()

    data = st.session_state.get('api_data', {})
    st.divider()
    col_l, col_r = st.columns([0.4, 0.6])
    
    with col_l:
        if data.get('img'): st.image(data['img'], use_container_width=False)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("아티스트/작가", value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', ''))
        
    with col_r:
        summary = st.text_area("📖 요약/평", height=80)
        highlights = st.text_area("✨ 하이라이트/추천트랙", height=120)
        note = st.text_area("💬 감상", value=data.get('note', ''), height=120)
        
        # 가이드 폰트 시각화
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 최종 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, highlights, note, data.get('img', ''), str(date.today())))
                conn.commit()
            st.success("보관함에 저장되었습니다!")
            st.rerun()

# --- [Tab 2: 보관함 폴더] ---
with tab2:
    sub_tab_book, sub_tab_music = st.tabs(["📚 도서 폴더", "🎸 음악 폴더"])
    
    def display_gallery(cat):
        with sqlite3.connect(DB_NAME) as conn:
            df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{cat}' ORDER BY id DESC", conn)
        
        if df.empty:
            st.info(f"저장된 {cat} 기록이 없습니다.")
            return

        # 갤러리 그리드 구성 (한 줄에 4개)
        cols = st.columns(4)
        for idx, row in df.iterrows():
            with cols[idx % 4]:
                if row['img_url']:
                    st.image(row['img_url'], use_container_width=True)
                if st.button(f"{row['title']}", key=f"btn_{row['id']}"):
                    st.session_state.selected_item = row['id']

        # 상세 보기 섹션
        if 'selected_item' in st.session_state:
            item = df[df['id'] == st.session_state.selected_item]
            if not item.empty:
                item = item.iloc[0]
                st.divider()
                det_l, det_r = st.columns([0.3, 0.7])
                with det_l:
                    if item['img_url']: st.image(item['img_url'], use_container_width=True)
                    st.write(f"**창작자:** {item['creator']}")
                    st.write(f"**활동일:** {item['rel_date']}")
                with det_r:
                    st.info(f"**📖 요약**\n\n{item['summary']}")
                    st.warning(f"**✨ 하이라이트**\n\n{item['highlights']}")
                    st.write(f"**💬 감상**\n\n{item['note']}")
                    if st.button("🗑️ 삭제", key=f"del_{item['id']}"):
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
                        del st.session_state.selected_item
                        st.rerun()

    with sub_tab_book:
        display_gallery("도서")
    with sub_tab_music:
        display_gallery("음악")

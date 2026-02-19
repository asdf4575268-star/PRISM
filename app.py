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
    
    /* 갤러리 이미지 효과 */
    div[data-testid="stImage"] > img {
        border-radius: 12px;
        transition: transform 0.3s ease;
        cursor: pointer;
        border: 1px solid #eee;
    }
    div[data-testid="stImage"] > img:hover {
        transform: scale(1.05);
        box-shadow: 0px 10px 20px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

# DB 파일명 (카테고리 구조 최적화)
DB_NAME = 'archive_prism_v1.db'

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')

# --- [2. API 연동 함수들] ---

# 도서 (카카오)
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

# 음악 (애플/iTunes)
def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=15&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url)
        return res.json().get("results", [])
    except: return []

# 영화 (TMDB)
def search_movies(query):
    api_key = "a80084c6883582489f688062829141f2" 
    url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={query}&language=ko-KR"
    try:
        res = requests.get(url)
        return res.json().get("results", []) if res.status_code == 200 else []
    except: return []

# --- [3. 상세 보기 팝업 다이얼로그] ---
@st.dialog("📋 아카이브 상세 기록", width="large")
def show_details(item):
    col_img, col_txt = st.columns([0.4, 0.6])
    with col_img:
        if item['img_url']:
            st.image(item['img_url'], use_container_width=True)
        st.caption(f"Category: {item['category']} | 저장일: {item['save_date']}")
    
    with col_txt:
        st.subheader(item['title'])
        st.write(f"**창작자:** {item['creator']}")
        st.write(f"**날짜:** {item['rel_date']}")
        st.divider()
        st.info(f"**📖 요약/줄거리**\n\n{item['summary']}")
        st.warning(f"**✨ 하이라이트/명대사**\n\n{item['highlights']}")
        st.write(f"**💬 개인적 감상**\n\n{item['note']}")
        
        st.divider()
        if st.button("🗑️ 이 기록 삭제", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

# --- [4. 메인 로직] ---
init_db()

tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 보관함 폴더"])

with tab1:
    category = st.radio("📂 카테고리 선택", ["도서", "음악", "영화"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 제목을 입력하세요", placeholder="검색 후 데이터 연동을 눌러주세요")
    
    if search_query:
        if category == "도서":
            res = search_books(search_query)
            if res:
                opts = {f"📚 {b['title']} ({b['authors'][0]})": b for b in res if b['authors']}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 데이터 연동"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': b['authors'][0], 'date': b['datetime'][:10], 'img': b['thumbnail'], 'note': b['contents']}
                    st.rerun()
        elif category == "음악":
            res = search_apple_music(search_query)
            if res:
                opts = {f"{('🎵' if m.get('wrapperType')=='track' else '💿')} {m.get('trackName', m.get('collectionName'))} - {m['artistName']}": m for m in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 데이터 연동"):
                    m = opts[sel]
                    artwork = m.get('artworkUrl100', '').replace('100x100bb', '600x600bb')
                    st.session_state.api_data = {'title': m.get('trackName', m.get('collectionName')), 'creator': m['artistName'], 'date': m['releaseDate'][:10], 'img': artwork, 'note': ''}
                    st.rerun()
        else: # 영화
            res = search_movies(search_query)
            if res:
                opts = {f"🎬 {mv['title']} ({mv['release_date'][:4] if mv.get('release_date') else '미정'})": mv for mv in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 데이터 연동"):
                    mv = opts[sel]
                    poster = f"https://image.tmdb.org/t/p/w500{mv['poster_path']}" if mv.get('poster_path') else ""
                    st.session_state.api_data = {'title': mv['title'], 'creator': '감독 및 출연진', 'date': mv.get('release_date', ''), 'img': poster, 'note': mv.get('overview', '')}
                    st.rerun()

    data = st.session_state.get('api_data', {})
    st.divider()
    
    # 입력 폼 레이아웃
    col_l, col_r = st.columns([0.4, 0.6])
    with col_l:
        if data.get('img'): st.image(data['img'], use_container_width=False)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자 (작가/아티스트/감독)", value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', ''))
        
    with col_r:
        summary = st.text_area("📖 요약/평", value=data.get('note', '')[:200] if category=="영화" else "", height=80)
        highlights = st.text_area("✨ 하이라이트 (명대사/추천트랙)", height=120)
        note = st.text_area("💬 개인적 감상", height=120)
        
        # 가이드 폰트 프리뷰
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 아카이브 최종 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, highlights, note, data.get('img', ''), str(date.today())))
            st.success(f"{category} 보관함에 저장되었습니다!")
            st.rerun()

# --- [보관함 탭] ---
with tab2:
    f_book, f_music, f_movie = st.tabs(["📚 도서 폴더", "🎸 음악 폴더", "🎬 영화 폴더"])
    
    def display_gallery(cat):
        try:
            with sqlite3.connect(DB_NAME) as conn:
                df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{cat}' ORDER BY id DESC", conn)
            
            if df.empty:
                st.info(f"아직 저장된 {cat} 기록이 없습니다.")
                return

            cols = st.columns(4)
            for idx, row in df.iterrows():
                with cols[idx % 4]:
                    if row['img_url']:
                        st.image(row['img_url'], use_container_width=True)
                    if st.button(row['title'], key=f"btn_{row['id']}", use_container_width=True):
                        show_details(row)
        except:
            st.warning("데이터를 불러오는 중입니다. 잠시만 기다려주세요.")

    with f_book: display_gallery("도서")
    with f_music: display_gallery("음악")
    with f_movie: display_gallery("영화")

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

DB_NAME = 'archive_prism_tmdb_v1.db'
TMDB_API_KEY = "a80084c6883582489f688062829141f2" # TMDB 키

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')

# --- [2. TMDB 연동 함수] ---
def search_tmdb(query, category):
    # 영화(movie) 또는 TV(tv) 검색
    search_type = "movie" if category == "영화" else "tv"
    url = f"https://api.themoviedb.org/3/search/{search_type}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try:
        res = requests.get(url)
        return res.json().get("results", [])
    except: return []

# --- [3. 상세 보기 팝업] ---
@st.dialog("📋 아카이브 상세 정보", width="large")
def show_details(item):
    col_img, col_txt = st.columns([0.4, 0.6])
    with col_img:
        if item['img_url']: st.image(item['img_url'], use_container_width=True)
    with col_txt:
        st.subheader(item['title'])
        st.write(f"**정보:** {item['creator']} | **개봉/방영:** {item['rel_date']}")
        st.divider()
        st.info(f"**📖 줄거리 요약**\n\n{item['summary']}")
        st.warning(f"**✨ 하이라이트**\n\n{item['highlights']}")
        st.write(f"**💬 나의 기록**\n\n{item['note']}")
        if st.button("🗑️ 삭제하기"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

init_db()

# --- [4. 메인 화면] ---
tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 보관함"])

with tab1:
    category = st.radio("📂 카테고리", ["영화", "시리즈(드라마)"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 제목을 입력하세요", placeholder="제목 입력 후 엔터를 눌러주세요")
    
    if search_query:
        results = search_tmdb(search_query, category)
        if results:
            # 영화는 title, TV는 name 속성을 사용함
            opts = {}
            for r in results[:10]:
                name = r.get('title') if category == "영화" else r.get('name')
                year = (r.get('release_date', '')[:4] if category == "영화" else r.get('first_air_date', '')[:4])
                opts[f"🎬 {name} ({year if year else '날짜미상'})"] = r
            
            sel_name = st.selectbox("검색 결과 선택", list(opts.keys()))
            if st.button("✨ 데이터 가져오기"):
                selected = opts[sel_name]
                poster_path = selected.get('poster_path')
                st.session_state.api_data = {
                    'title': selected.get('title') if category == "영화" else selected.get('name'),
                    'date': selected.get('release_date') if category == "영화" else selected.get('first_air_date'),
                    'img': f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "",
                    'summary': selected.get('overview', '')
                }
                st.rerun()

    st.divider()
    data = st.session_state.get('api_data', {})
    
    col_l, col_r = st.columns([0.4, 0.6])
    with col_l:
        img_url = st.text_input("포스터 URL", value=data.get('img', ''))
        if img_url: st.image(img_url, width=300)
        title = st.text_input("제목", value=data.get('title', ''))
        rel_date = st.text_input("날짜", value=data.get('date', ''))
        creator = st.text_input("추가 정보 (감독/제작사)", value="TMDB 연동 데이터")

    with col_r:
        summary = st.text_area("📖 줄거리/요약", value=data.get('summary', ''), height=100)
        highlights = st.text_area("✨ 하이라이트 (명대사)", height=100)
        note = st.text_area("💬 감상평", height=100)
        
        # 가이드 디자인 프리뷰
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 최종 저장", use_container_width=True):
            if title:
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (category, title, creator, rel_date, summary, highlights, note, img_url, str(date.today())))
                st.success("보관함에 저장되었습니다!")
                st.session_state.api_data = {}
                st.rerun()

with tab2:
    f_movie, f_tv = st.tabs(["🎬 영화 보관함", "📺 시리즈 보관함"])
    def display_gallery(cat):
        with sqlite3.connect(DB_NAME) as conn:
            df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{cat}' ORDER BY id DESC", conn)
        if df.empty: return st.info("기록이 없습니다.")
        cols = st.columns(4)
        for idx, row in df.iterrows():
            with cols[idx % 4]:
                if row['img_url']: st.image(row['img_url'], use_container_width=True)
                if st.button(row['title'], key=f"btn_{cat}_{row['id']}", use_container_width=True):
                    show_details(row)
    with f_movie: display_gallery("영화")
    with f_tv: display_gallery("시리즈(드라마)")

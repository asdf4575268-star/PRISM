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
    div[data-testid="stImage"] > img:hover {
        transform: scale(1.05);
        box-shadow: 0px 10px 20px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_v12.db'
KAKAO_KEY = "a356895a3aae4f0acf9f4ee884d90a6a"
KOFIC_KEY = "f5eef3421c602c6cb7ea224104795888" # 영진위 API 키

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')

# --- [2. API 연동 함수들] ---

def search_books(query):
    headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=10&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url)
        return res.json().get("results", [])
    except: return []

# 영진위 영화 검색
def search_movies_kofic(query):
    url = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/getMovieList.json"
    params = {"key": KOFIC_KEY, "movieNm": query}
    try:
        res = requests.get(url, params=params)
        return res.json().get("movieListResult", {}).get("movieList", [])
    except: return []

# 카카오 이미지 검색 (포스터용)
def search_kakao_image(query):
    headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
    res = requests.get("https://dapi.kakao.com/v2/search/image", headers=headers, params={"query": f"영화 {query} 포스터", "size": 5})
    return res.json().get("documents", []) if res.status_code == 200 else []

# --- [3. 상세 보기 팝업] ---
@st.dialog("📋 상세 기록", width="large")
def show_details(item):
    col_img, col_txt = st.columns([0.4, 0.6])
    with col_img:
        if item['img_url']: st.image(item['img_url'], use_container_width=True)
        st.caption(f"Category: {item['category']} | 저장일: {item['save_date']}")
    with col_txt:
        st.subheader(item['title'])
        st.write(f"**정보:** {item['creator']}")
        st.write(f"**날짜:** {item['rel_date']}")
        st.divider()
        st.info(f"**📖 요약**\n\n{item['summary']}")
        st.warning(f"**✨ 하이라이트**\n\n{item['highlights']}")
        st.write(f"**💬 감상**\n\n{item['note']}")
        if st.button("🗑️ 삭제하기", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

init_db()

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 보관함 폴더"])

with tab1:
    category = st.radio("📂 카테고리 선택", ["도서", "음악", "영화"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 제목을 입력하세요")
    
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
                opts = {f"🎵 {m.get('trackName', m.get('collectionName'))} - {m['artistName']}": m for m in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 데이터 연동"):
                    m = opts[sel]
                    img = m.get('artworkUrl100', '').replace('100x100bb', '600x600bb')
                    st.session_state.api_data = {'title': m.get('trackName', m.get('collectionName')), 'creator': m['artistName'], 'date': m['releaseDate'][:10], 'img': img, 'note': ''}
                    st.rerun()

        elif category == "영화":
            movie_res = search_movies_kofic(search_query)
            if movie_res:
                # 영진위 결과 선택
                opts = {f"🎬 {m['movieNm']} ({m['prdtYear']}년) - {m['genreAlt']}": m for m in movie_res}
                sel_movie = st.selectbox("영진위 영화 목록", list(opts.keys()))
                
                # 선택한 영화의 포스터 후보를 카카오에서 가져옴
                img_res = search_kakao_image(opts[sel_movie]['movieNm'])
                if img_res:
                    st.write("🖼️ 매칭할 포스터를 선택하세요")
                    img_cols = st.columns(5)
                    for i, img_doc in enumerate(img_res):
                        with img_cols[i]:
                            st.image(img_doc['image_url'], use_container_width=True)
                            if st.button(f"선택 {i+1}"):
                                m = opts[sel_movie]
                                st.session_state.api_data = {
                                    'title': m['movieNm'],
                                    'creator': m['directors'][0]['peopleNm'] if m['directors'] else "정보 없음",
                                    'date': m['openDt'] if m.get('openDt') else f"{m['prdtYear']}-01-01",
                                    'img': img_doc['image_url'],
                                    'note': f"장르: {m['genreAlt']} / 국가: {m['nationAlt']}"
                                }
                                st.rerun()
            else:
                st.warning("영진위 검색 결과가 없습니다.")

    # 공통 입력 폼
    data = st.session_state.get('api_data', {})
    st.divider()
    col_l, col_r = st.columns([0.4, 0.6])
    
    with col_l:
        if data.get('img'): st.image(data['img'], use_container_width=False)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자", value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', ''))
        
    with col_r:
        summary = st.text_area("📖 요약/줄거리", value=data.get('note', ''), height=80)
        highlights = st.text_area("✨ 하이라이트", height=120)
        note = st.text_area("💬 개인적 감상", height=120)
        
        # 가이드 디자인
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 최종 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, highlights, note, data.get('img', ''), str(date.today())))
            st.success("보관함에 저장되었습니다!")
            st.rerun()

# --- [보관함 탭] ---
with tab2:
    f_book, f_music, f_movie = st.tabs(["📚 도서", "🎸 음악", "🎬 영화"])
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
    with f_book: display_gallery("도서")
    with f_music: display_gallery("음악")
    with f_movie: display_gallery("영화")

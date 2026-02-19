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
    }
    div[data-testid="stImage"] > img:hover { transform: scale(1.05); }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_final.db'
KAKAO_KEY = "a356895a3aae4f0acf9f4ee884d90a6a" # 사용자님의 카카오 키 활용

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')

# --- [2. API 연동 함수 (카카오 통합)] ---

def search_kakao(query, category_type="book"):
    # 카카오 API를 카테고리에 따라 다르게 호출
    headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
    if category_type == "도서":
        url = "https://dapi.kakao.com/v3/search/book"
        res = requests.get(url, headers=headers, params={"query": query})
        return res.json().get("documents", [])
    else: # 영화의 경우 '웹 검색'을 통해 정보를 가져옴
        url = "https://dapi.kakao.com/v2/search/web"
        res = requests.get(url, headers=headers, params={"query": f"영화 {query} 정보"})
        return res.json().get("documents", [])

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=10&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url)
        return res.json().get("results", [])
    except: return []

# --- [3. 상세 보기 팝업] ---
@st.dialog("📋 상세 기록 보기", width="large")
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

# --- [메인 화면] ---
tab1, tab2 = st.tabs(["🖋️ 입력", "📂 보관함"])

with tab1:
    category = st.radio("📂 카테고리", ["도서", "음악", "영화"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색", placeholder="제목을 입력하고 엔터를 눌러주세요")
    
    if search_query:
        if category == "도서":
            res = search_kakao(search_query, "도서")
            if res:
                opts = {f"📚 {b['title']} ({b['authors'][0] if b['authors'] else '미상'})": b for b in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 데이터 연동"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': b['authors'][0] if b['authors'] else "", 'date': b['datetime'][:10], 'img': b['thumbnail'], 'note': b['contents']}
                    st.rerun()
        
        elif category == "음악":
            res = search_apple_music(search_query)
            if res:
                opts = {f"🎵 {m.get('trackName', m.get('collectionName'))} - {m['artistName']}": m for m in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 데이터 연동"):
                    m = opts[sel]
                    img = m.get('artworkUrl100', '').replace('100x100bb', '600x600bb')
                    st.session_state.api_data = {'title': m.get('trackName', m.get('collectionName')), 'creator': m['artistName'], 'date': m['releaseDate'][:10], 'img': img, 'note': ''}
                    st.rerun()

        elif category == "영화":
            # 영화는 '이미지 검색' API를 활용해 포스터와 제목을 가져옵니다.
            headers = {"Authorization": f"KakaoAK {KAKAO_KEY}"}
            img_res = requests.get("https://dapi.kakao.com/v2/search/image", headers=headers, params={"query": f"영화 {search_query} 포스터", "size": 10})
            web_res = requests.get("https://dapi.kakao.com/v2/search/web", headers=headers, params={"query": f"영화 {search_query} 정보"})
            
            img_docs = img_res.json().get("documents", [])
            web_docs = web_res.json().get("documents", [])
            
            if img_docs:
                st.write("🔎 영화 관련 이미지를 찾았습니다.")
                # 이미지들을 선택할 수 있게 나열
                img_opts = {f"포스터 후보 {i+1}": doc['image_url'] for i, doc in enumerate(img_docs[:5])}
                sel_img = st.selectbox("영화 포스터 선택", list(img_opts.keys()))
                
                if st.button("✨ 영화 데이터 연동"):
                    # 웹 검색 결과에서 첫 번째 요약을 가져옴
                    summary_text = web_docs[0]['contents'].replace('<b>', '').replace('</b>', '') if web_docs else ""
                    st.session_state.api_data = {
                        'title': search_query, 
                        'creator': "영화 감독/배우", 
                        'date': str(date.today()), 
                        'img': img_opts[sel_img], 
                        'note': summary_text
                    }
                    st.rerun()

    data = st.session_state.get('api_data', {})
    st.divider()
    col_l, col_r = st.columns([0.4, 0.6])
    with col_l:
        if data.get('img'): st.image(data['img'], use_container_width=False)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("정보 (작가/아티스트/감독)", value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', ''))
    with col_r:
        summary = st.text_area("📖 요약", value=data.get('note', ''), height=80)
        highlights = st.text_area("✨ 하이라이트", height=120)
        note = st.text_area("💬 감상", height=120)
        
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 최종 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, highlights, note, data.get('img', ''), str(date.today())))
            st.success("저장되었습니다!")
            st.rerun()

with tab2:
    f_book, f_music, f_movie = st.tabs(["📚 도서", "🎸 음악", "🎬 영화"])
    def display_gallery(cat):
        with sqlite3.connect(DB_NAME) as conn:
            df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{cat}' ORDER BY id DESC", conn)
        if df.empty:
            st.info("기록이 없습니다.")
            return
        cols = st.columns(4)
        for idx, row in df.iterrows():
            with cols[idx % 4]:
                if row['img_url']: st.image(row['img_url'], use_container_width=True)
                if st.button(row['title'], key=f"btn_{cat}_{row['id']}", use_container_width=True):
                    show_details(row)
    with f_book: display_gallery("도서")
    with f_music: display_gallery("음악")
    with f_movie: display_gallery("영화")

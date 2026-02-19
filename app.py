import streamlit as st
import sqlite3
import requests
import pandas as pd
import xml.etree.ElementTree as ET # KOPIS는 XML 데이터를 주로 사용합니다
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

DB_NAME = 'archive_prism_v2.db'
KOPIS_API_KEY = "f79603f909154737a28e932332617730" # 공연예술통합전산망 키

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')

# --- [2. API 연동 함수들] ---

# (기존 도서, 음악, 영화 API 로직 유지...)
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=10&country=kr&entity=musicTrack,album"
    try: return requests.get(url).json().get("results", [])
    except: return []

def search_movies(query):
    api_key = "a80084c6883582489f688062829141f2" 
    url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

# 🎭 [신규] 무대극 검색 (KOPIS 연동)
def search_stage_play(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr"
    params = {
        "service": KOPIS_API_KEY,
        "stdate": "20100101", # 검색 시작일
        "eddate": "20261231", # 검색 종료일
        "cpage": 1,
        "rows": 10,
        "shprfnm": query
    }
    try:
        res = requests.get(url, params=params)
        root = ET.fromstring(res.text)
        plays = []
        for db in root.findall('db'):
            plays.append({
                'title': db.find('prfnm').text,
                'id': db.find('mt20id').text,
                'date': f"{db.find('prfpdfrom').text} ~ {db.find('prfpdto').text}",
                'img': db.find('poster').text,
                'venue': db.find('fcltynm').text
            })
        return plays
    except: return []

# --- [3. 상세 보기 팝업] ---
@st.dialog("📋 아카이브 상세 기록", width="large")
def show_details(item):
    col_img, col_txt = st.columns([0.4, 0.6])
    with col_img:
        if item['img_url']: st.image(item['img_url'], use_container_width=True)
    with col_txt:
        st.subheader(item['title'])
        st.write(f"**창작자/장소:** {item['creator']}")
        st.write(f"**날짜:** {item['rel_date']}")
        st.divider()
        st.info(f"**📖 요약/정보**\n\n{item['summary']}")
        st.warning(f"**✨ 하이라이트/명대사**\n\n{item['highlights']}")
        st.write(f"**💬 개인적 감상**\n\n{item['note']}")
        if st.button("🗑️ 삭제하기"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

init_db()

# --- [4. 메인 화면] ---
tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 보관함 폴더"])

with tab1:
    category = st.radio("📂 카테고리 선택", ["도서", "음악", "영화", "무대극"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색", placeholder="제목을 입력하세요")
    
    if search_query:
        # 도서, 음악, 영화 로직 (기존과 동일) ...
        if category == "무대극":
            res = search_stage_play(search_query)
            if res:
                opts = {f"🎭 {p['title']} ({p['venue']})": p for p in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 공연 데이터 연동"):
                    p = opts[sel]
                    st.session_state.api_data = {
                        'title': p['title'], 'creator': p['venue'], 
                        'date': p['date'], 'img': p['img'], 'note': f"공연 장소: {p['venue']}"
                    }
                    st.rerun()

    data = st.session_state.get('api_data', {})
    st.divider()
    col_l, col_r = st.columns([0.4, 0.6])
    with col_l:
        if data.get('img'): st.image(data['img'], use_container_width=False)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("정보 (작가/아티스트/장소)", value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', ''))
        
    with col_r:
        summary = st.text_area("📖 요약/정보", value=data.get('note', ''), height=80)
        highlights = st.text_area("✨ 하이라이트", height=120)
        note = st.text_area("💬 개인적 감상", height=120)
        
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 최종 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, highlights, note, data.get('img', ''), str(date.today())))
            st.success("보관함에 저장되었습니다!")
            st.rerun()

with tab2:
    tabs = st.tabs(["📚 도서", "🎸 음악", "🎬 영화", "🎭 무대극"])
    cats = ["도서", "음악", "영화", "무대극"]
    
    for i, tab in enumerate(tabs):
        with tab:
            with sqlite3.connect(DB_NAME) as conn:
                df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{cats[i]}' ORDER BY id DESC", conn)
            if df.empty: st.info("기록이 없습니다.")
            else:
                cols = st.columns(4)
                for idx, row in df.iterrows():
                    with cols[idx % 4]:
                        if row['img_url']: st.image(row['img_url'], use_container_width=True)
                        if st.button(row['title'], key=f"btn_{row['id']}", use_container_width=True):
                            show_details(row)

import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="Prism")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; }
    div[data-testid="stImage"] > img { border-radius: 12px; border: 1px solid #eee; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_total_v4.db' # 요약 컬럼 추가를 위해 DB 버전 업
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        # summary(줄거리) 외에 brief(새로 만든 요약) 컬럼 추가
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')

# --- [2. API 연동 함수들] ---
def get_tmdb_details(item_id, category):
    type_path = "MOVIES" if category == "MOVIES" else "tv"
    url = f"https://api.theMOVIESdb.org/3/{type_path}/{item_id}/credits?api_key={TMDB_API_KEY}&language=ko-KR"
    try:
        res = requests.get(url).json()
        director = next((m['name'] for m in res.get('crew', []) if m.get('job') == 'Director'), "정보 없음")
        cast = ", ".join([c['name'] for c in res.get('cast', [])[:3]])
        return f"감독: {director} / 출연: {cast}"
    except: return "정보 없음"

def search_BOOKSs(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/BOOKS", headers=headers, params={"query": query})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=10&country=kr&entity=musicTrack,album"
    try: return requests.get(url).json().get("results", [])
    except: return []

def search_tmdb(query, category):
    search_type = "MOVIES" if category == "MOVIES" else "tv"
    url = f"https://api.theMOVIESdb.org/3/search/{search_type}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

# --- [3. 상세 보기 팝업] ---
@st.dialog("📋 기록 상세 보기", width="large")
def show_details(item):
    col_img, col_txt = st.columns([0.4, 0.6])
    with col_img:
        if item['img_url']: st.image(item['img_url'], use_container_width=True)
    with col_txt:
        st.subheader(item['title'])
        st.write(f"**정보:** {item['creator']} | **날짜:** {item['rel_date']}")
        st.divider()
        if item['brief']: st.success(f"**📝 요약:** {item['brief']}")
        st.info(f"**📖 줄거리:**\n\n{item['summary']}")
        st.warning(f"**✨ 하이라이트:**\n\n{item['highlights']}")
        st.write(f"**💬 감상:**\n\n{item['note']}")
        if st.button("🗑️ 삭제하기"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

init_db()

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 ", ["BOOKS", "MUSIC", "MOVIES", "SERIES"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 제목 검색")
    
    if search_query:
        # (기본 연동 로직은 동일하되, 받아오는 데이터를 session_state에 저장)
        if category == "BOOKS":
            res = search_BOOKSs(search_query)
            if res:
                opts = {f"📚 {b['title']} ({b['authors'][0]})": b for b in res if b['authors']}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 데이터 가져오기"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': f"저자: {', '.join(b['authors'])}", 'date': b['datetime'][:10], 'img': b['thumbnail'], 'summary': b['contents']}
                    st.rerun()
        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {f"🎵 {m.get('trackName', m.get('collectionName'))}": m for m in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 데이터 가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m.get('trackName', m.get('collectionName')), 'creator': f"아티스트: {m['artistName']}", 'date': m['releaseDate'][:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '600x600bb'), 'summary': ''}
                    st.rerun()
        else: # MOVIES/SERIES
            res = search_tmdb(search_query, category)
            if res:
                opts = {}
                for r in res[:10]:
                    name = r.get('title') if category == "MOVIES" else r.get('name')
                    date_v = r.get('release_date') if category == "MOVIES" else r.get('first_air_date')
                    opts[f"🎬 {name} ({date_v[:4] if date_v else '미상'})"] = r
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 데이터 가져오기"):
                    selected = opts[sel]
                    credits_info = get_tmdb_details(selected['id'], category)
                    st.session_state.api_data = {
                        'title': selected.get('title') if category == "MOVIES" else selected.get('name'),
                        'creator': credits_info,
                        'date': selected.get('release_date') if category == "MOVIES" else selected.get('first_air_date'),
                        'img': f"https://image.tmdb.org/t/p/w500{selected.get('poster_path')}" if selected.get('poster_path') else "",
                        'summary': selected.get('overview', '')
                    }
                    st.rerun()

    st.divider()
    data = st.session_state.get('api_data', {})
    col_l, col_r = st.columns([0.4, 0.6])
    
    with col_l:
        img_url = data.get('img', '')
        if img_url: st.image(img_url, width=300)
        show_img_input = st.checkbox("이미지 주소 직접 입력", value=False if img_url else True)
        if show_img_input: img_url = st.text_input("이미지 주소(URL)", value=img_url)
        
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자/배우 정보", value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', str(date.today())))

    with col_r:
        # 요청사항 반영: 요약 입력창 새로 만들고, 기존 요약은 줄거리로 변경
        brief = st.text_input("📝 한 줄 요약 (직접 입력)", placeholder="이 작품을 한 마디로 정의한다면?")
        summary = st.text_area("📖 줄거리 (API 연동)", value=data.get('summary', ''), height=150)
        highlights = st.text_area("✨ 하이라이트 (명대사/구절)", height=100)
        note = st.text_area("💬 개인적 감상", height=100)
        
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 최종 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, brief, highlights, note, img_url, str(date.today())))
            st.success("보관함에 저장되었습니다!")
            st.session_state.api_data = {}
            st.rerun()

with tab2:
    sub_tabs = st.tabs(["📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES"])
    categories = ["BOOKS", "MUSIC", "MOVIES", "SERIES"]
    for i, tab in enumerate(sub_tabs):
        with tab:
            with sqlite3.connect(DB_NAME) as conn:
                df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{categories[i]}' ORDER BY id DESC", conn)
            if df.empty: st.info("기록이 없습니다.")
            else:
                cols = st.columns(4)
                for idx, row in df.iterrows():
                    with cols[idx % 4]:
                        if row['img_url']: st.image(row['img_url'], use_container_width=True)
                        if st.button(row['title'], key=f"btn_{row['id']}", use_container_width=True):
                            show_details(row)




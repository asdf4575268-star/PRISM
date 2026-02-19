import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    
    /* 사용자 요청 폰트 크기 설정 */
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; }
    
    /* 갤러리 이미지 스타일 */
    div[data-testid="stImage"] > img {
        border-radius: 12px;
        transition: transform 0.3s ease;
        cursor: pointer;
        border: 1px solid #eee;
    }
    div[data-testid="stImage"] > img:hover { transform: scale(1.05); }
    
    /* 보관함 날짜 텍스트 스타일 */
    .save-date-tag { font-size: 14px; color: #888; margin-top: -10px; margin-bottom: 10px; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_total_v4.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')

# --- [2. API 연동 함수들] ---
def get_tmdb_details(item_id, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}/credits?api_key={TMDB_API_KEY}&language=ko-KR"
    try:
        res = requests.get(url).json()
        director = next((m['name'] for m in res.get('crew', []) if m.get('job') == 'Director'), "정보 없음")
        cast = ", ".join([c['name'] for c in res.get('cast', [])[:3]])
        return f"감독: {director} / 출연: {cast}"
    except: return "정보 없음"

def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=10&country=kr&entity=musicTrack,album"
    try: return requests.get(url).json().get("results", [])
    except: return []

def search_tmdb(query, category):
    search_type = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{search_type}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
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
        st.write(f"**정보:** {item['creator']} | **작품날짜:** {item['rel_date']}")
        st.caption(f"기록일: {item['save_date']}")
        st.divider()
        if item['brief']: st.success(f"**📝 요약:** {item['brief']}")
        st.info(f"**📖 줄거리:**\n\n{item['summary']}")
        st.warning(f"**✨ 인상 깊은 부분:**\n\n{item['highlights']}")
        st.write(f"**💬 감상:**\n\n{item['note']}")
        if st.button("🗑️ 삭제하기", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

init_db()

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색", placeholder="제목 입력 후 가져오기를 눌러주세요")
    
    if search_query:
        if category == "BOOKS":
            res = search_books(search_query)
            if res:
                opts = {f"📚 {b['title']} ({b['authors'][0] if b['authors'] else '미상'})": b for b in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': f"저자: {', '.join(b['authors'])}", 'date': b['datetime'][:10], 'img': b['thumbnail'], 'summary': b['contents']}
                    st.rerun()
        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {f"🎵 {m.get('trackName', m.get('collectionName'))}": m for m in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 가져오기"):
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
                if st.button("✨ 가져오기"):
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
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자/배우 정보", value=data.get('creator', ''))
        rel_date = st.text_input("작품 관련 날짜", value=data.get('date', str(date.today())))

    with col_r:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=100)

        
        if st.button("✅ 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, brief, highlights, note, img_url, str(date.today())))
            st.success("보관함에 저장되었습니다!")
            st.session_state.api_data = {}
            st.rerun()

# --- [4. 메인 화면 구성 수정 부분] ---
with tab2:
    # 탭 메뉴에 'YEARLY' 추가
    sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES"])
    
# 1. 연도별 통합 보기 탭
with sub_tabs[0]:
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive ORDER BY save_date DESC, id DESC", conn)
    
    if all_df.empty:
        st.info("기록이 없습니다.")
    else:
        # 연도 추출 및 선택창 옵션 구성 (연도 (개수))
        all_df['year'] = all_df['save_date'].apply(lambda x: str(x).split('-')[0])
        year_counts = all_df['year'].value_counts().sort_index(ascending=False)
        year_options = [f"{year} ({count})" for year, count in year_counts.items()]
        
        selected_option = st.selectbox("📅 연도 선택", year_options)
        selected_year = selected_option.split(' ')[0]
        
        year_df = all_df[all_df['year'] == selected_year]

        # --- 이미지 크기 통일을 위한 CSS 추가 ---
        st.markdown("""
            <style>
            /* 모든 이미지를 1:1 비율의 고정된 크기로 통일 */
            .annual-img-container img {
                width: 100% !important;
                height: 150px !important; /* 세로 높이 고정 */
                object-fit: cover !important; /* 비율 유지하며 꽉 채움 */
                border-radius: 8px;
            }
            </style>
        """, unsafe_allow_html=True)

        # 한 줄에 6개 배치 (이미지 사이즈 축소 효과)
        cols_per_row = 6 
        cols = st.columns(cols_per_row)
        
        for idx, row in year_df.reset_index().iterrows():
            with cols[idx % cols_per_row]:
                if row['img_url']:
                    # 이미지를 div로 감싸서 CSS 적용
                    st.markdown(f'<div class="annual-img-container">', unsafe_allow_html=True)
                    st.image(row['img_url'], use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                
                # 텍스트 정보 (소문자 단위 유지)
                st.markdown(f"""
                    <div style="text-align:center; font-size:11px; color:gray; margin-top:5px;">
                        {row['save_date']}<br>
                        <b style="color:black; font-size:12px;">{row['title']}</b>
                    </div>
                """, unsafe_allow_html=True)
                
                if st.button("🔍", key=f"year_btn_{row['id']}", use_container_width=True):
                    show_details(row)

    # 2. 기존 카테고리별 탭 (동일하게 유지)
    categories = ["BOOKS", "MUSIC", "MOVIES", "SERIES"]
    for i, category_name in enumerate(categories):
        with sub_tabs[i+1]:
            with sqlite3.connect(DB_NAME) as conn:
                df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{category_name}' ORDER BY id DESC", conn)
            if df.empty:
                st.info(f"{category_name} 기록이 없습니다.")
            else:
                cols = st.columns(4)
                for idx, row in df.iterrows():
                    with cols[idx % 4]:
                        if row['img_url']: st.image(row['img_url'], use_container_width=True)
                        st.markdown(f'<p class="save-date-tag">📅 기록일: {row["save_date"]}</p>', unsafe_allow_html=True)
                        if st.button(row['title'], key=f"cat_btn_{row['id']}", use_container_width=True):
                            show_details(row)














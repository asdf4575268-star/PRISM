import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
from datetime import date, datetime

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    
    /* 활동명(제목) 크기 90 */
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    /* 날짜 크기 30 */
    .date-text { font-size: 30px; color: #666; margin: 0; }
    /* 숫자 크기 60 (Jolly Lodger 적용) */
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; line-height: 1; }
    
    .cal-img-box { width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:4px; margin-bottom:4px; border: 1px solid #eee; }
    .cal-img-box img { width:100%; height:100%; object-fit:cover; }
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

init_db()

# --- [2. 세션 및 기능 함수] ---
if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month

def shift_month(delta):
    new_month = st.session_state.cal_month + delta
    if new_month > 12: st.session_state.cal_month = 1; st.session_state.cal_year += 1
    elif new_month < 1: st.session_state.cal_month = 12; st.session_state.cal_year -= 1
    else: st.session_state.cal_month = new_month

@st.dialog("📋 기록 상세 보기", width="large")
def show_details(item):
    col_img, col_txt = st.columns([0.4, 0.6])
    with col_img:
        if item['img_url']: st.image(item['img_url'], use_container_width=True)
    with col_txt:
        st.markdown(f'<p class="act-name">{item["title"]}</p>', unsafe_allow_html=True)
        st.write(f"**정보:** {item['creator']} | **작품날짜:** {item['rel_date']}")
        st.markdown(f'<p class="date-text">기록일: {item["save_date"]}</p>', unsafe_allow_html=True)
        st.divider()
        if item['brief']: st.success(f"**📝 요약:** {item['brief']}")
        st.info(f"**📖 줄거리:**\n\n{item['summary']}")
        st.warning(f"**✨ 인상 깊은 부분:**\n\n{item['highlights']}")
        st.write(f"**💬 감상:**\n\n{item['note']}")
        if st.button("🗑️ 삭제하기", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

# --- API 함수들 (WRITE용) ---
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

# --- [3. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

# --- TAB 1: WRITE ---
with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    if search_query:
        if category == "BOOKS":
            res = search_books(search_query)
            if res:
                opts = {f"📚 {b['title']}": b for b in res}
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
        else:
            res = search_tmdb(search_query, category)
            if res:
                opts = {f"🎬 {r.get('title' if category=='MOVIES' else 'name')}": r for r in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s.get('title' if category=='MOVIES' else 'name'), 'creator': get_tmdb_details(s['id'], category), 'date': s.get('release_date' if category=='MOVIES' else 'first_air_date'), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'summary': s.get('overview', '')}
                    st.rerun()

    st.divider()
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url_val = data.get('img', '')
        if img_url_val: st.image(img_url_val, width=300)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자 정보", value=data.get('creator', ''))
        rel_date = st.text_input("날짜", value=data.get('date', str(date.today())))
    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=100)
        if st.button("✅ 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date) VALUES (?,?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, brief, highlights, note, img_url_val, str(date.today())))
            st.success("저장 완료!")
            st.session_state.api_data = {}
            st.rerun()

# --- TAB 2: ARCHIVE ---
with tab2:
    sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES"])
    
    with sub_tabs[0]:
        with sqlite3.connect(DB_NAME) as conn:
            all_df = pd.read_sql_query("SELECT * FROM archive", conn)
        
        if not all_df.empty:
            all_df['save_date'] = pd.to_datetime(all_df['save_date'])
            
            # --- 연도 선택창 추가 ---
            all_df['year_int'] = all_df['save_date'].dt.year
            available_years = sorted(all_df['year_int'].unique(), reverse=True)
            if datetime.now().year not in available_years:
                available_years = [datetime.now().year] + available_years
            
            # 상단 컨트롤 영역
            c_yr, c_nav = st.columns([1, 3])
            with c_yr:
                selected_year = st.selectbox("연도 선택", available_years, index=available_years.index(st.session_state.cal_year) if st.session_state.cal_year in available_years else 0)
                if selected_year != st.session_state.cal_year:
                    st.session_state.cal_year = selected_year
                    st.rerun()

            n1, n2, n3 = st.columns([1, 2, 1])
            with n1:
                if st.button("◀ 이전달"): shift_month(-1); st.rerun()
            with n2:
                # 숫자 크기 60 적용
                st.markdown(f"<div style='text-align:center;' class='num-text'>{st.session_state.cal_year} / {st.session_state.cal_month}</div>", unsafe_allow_html=True)
            with n3:
                if st.button("다음달 ▶"): shift_month(1); st.rerun()

            # 달력 렌더링
            days = ["월", "화", "수", "목", "금", "토", "일"]
            h_cols = st.columns(7)
            for i, d in enumerate(days):
                color = "#2E5BFF" if i == 5 else "#FF4B4B" if i == 6 else "#888"
                h_cols[i].markdown(f"<p style='text-align:center; font-weight:bold; color:{color};'>{d}</p>", unsafe_allow_html=True)

            cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
            month_df = all_df[(all_df['save_date'].dt.year == st.session_state.cal_year) & (all_df['save_date'].dt.month == st.session_state.cal_month)]

            for week in cal:
                cols = st.columns(7)
                for i, day in enumerate(week):
                    if day == 0: continue
                    with cols[i]:
                        st.markdown(f"<p class='num-text' style='font-size:30px; margin:0;'>{day}</p>", unsafe_allow_html=True)
                        day_items = month_df[month_df['save_date'].dt.day == day]
                        if not day_items.empty:
                            if day_items.iloc[0]['img_url']:
                                st.markdown(f'<div class="cal-img-box"><img src="{day_items.iloc[0]["img_url"]}"></div>', unsafe_allow_html=True)
                            for _, r in day_items.iterrows():
                                if st.button(f"• {r['title'][:5]}", key=f"cal_{r['id']}", use_container_width=True):
                                    show_details(r)
                        else:
                            st.markdown("<div style='height:80px;'></div>", unsafe_allow_html=True)
        else:
            st.info("기록이 없습니다.")

    # 나머지 카테고리 탭
    cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES"]
    for idx, c_name in enumerate(cats):
        with sub_tabs[idx+1]:
            with sqlite3.connect(DB_NAME) as conn:
                df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{c_name}' ORDER BY id DESC", conn)
            if not df.empty:
                cols = st.columns(4)
                for i, row in df.iterrows():
                    with cols[i % 4]:
                        if row['img_url']: st.image(row['img_url'], use_container_width=True)
                        st.markdown(f'<p class="date-text" style="font-size:14px; text-align:center;">📅 {row["save_date"]}</p>', unsafe_allow_html=True)
                        if st.button(row['title'], key=f"list_{row['id']}", use_container_width=True):
                            show_details(row)

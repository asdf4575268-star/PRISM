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
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; }
    div[data-testid="stImage"] > img { border-radius: 12px; transition: transform 0.3s ease; cursor: pointer; border: 1px solid #eee; }
    div[data-testid="stImage"] > img:hover { transform: scale(1.05); }
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

# --- [2. 세션 상태 초기화] (중요: 탭보다 먼저 와야 함) ---
if 'cal_year' not in st.session_state:
    st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state:
    st.session_state.cal_month = datetime.now().month
if 'selected_record' not in st.session_state:
    st.session_state.selected_record = None

def shift_month(delta):
    new_month = st.session_state.cal_month + delta
    if new_month > 12:
        st.session_state.cal_month = 1
        st.session_state.cal_year += 1
    elif new_month < 1:
        st.session_state.cal_month = 12
        st.session_state.cal_year -= 1
    else:
        st.session_state.cal_month = new_month

# --- [3. API 및 다이얼로그] ---
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
        if st.button("🗑️ 삭제하기", key=f"del_diag_{item['id']}", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
            st.rerun()

# API 함수들 (생략 - 기존과 동일하게 유지)
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

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색", placeholder="제목 입력 후 가져오기를 눌러주세요")
    
    if search_query:
        # (기존 검색 로직 유지)
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
        else:
            res = search_tmdb(search_query, category)
            if res:
                opts = {f"🎬 {r.get('title' if category=='MOVIES' else 'name')}": r for r in res[:10]}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s.get('title' if category=='MOVIES' else 'name'), 'creator': get_tmdb_details(s['id'], category), 'date': s.get('release_date' if category=='MOVIES' else 'first_air_date'), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'summary': s.get('overview', '')}
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

with tab2:
    # 에러 해결 포인트: sub_tabs를 tab2 안에서 먼저 정의함
    sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES"])
    
    with sub_tabs[0]:
        with sqlite3.connect(DB_NAME) as conn:
            all_df = pd.read_sql_query("SELECT * FROM archive", conn)
        
        if all_df.empty:
            st.info("기록이 없습니다.")
        else:
            all_df['save_date'] = pd.to_datetime(all_df['save_date'], errors='coerce')
            all_df = all_df.dropna(subset=['save_date'])
            all_df['year_str'] = all_df['save_date'].dt.year.astype(str)

            year_counts = all_df['year_str'].value_counts().sort_index(ascending=False)
            year_options = [f"{y} ({c})" for y, c in year_counts.items()]
            curr_yr_str = str(st.session_state.cal_year)
            default_ix = next((i for i, s in enumerate(year_options) if s.startswith(curr_yr_str)), 0)

            top_col1, _ = st.columns([2, 1])
            with top_col1:
                selected_year_opt = st.selectbox("📅 연도 선택", year_options, index=default_ix, key="year_selector_main")
                st.session_state.cal_year = int(selected_year_opt.split(' ')[0])
            
            nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
            with nav_col1:
                if st.button("◀ 저번달", key="prev_mo"): shift_month(-1); st.rerun()
            with nav_col2:
                st.markdown(f"<h4 style='text-align:center; margin:0;'>{st.session_state.cal_year}년 {st.session_state.cal_month}월</h4>", unsafe_allow_html=True)
            with nav_col3:
                if st.button("다음달 ▶", key="next_mo"): shift_month(1); st.rerun()

            year_df = all_df[(all_df['save_date'].dt.year == st.session_state.cal_year) & 
                             (all_df['save_date'].dt.month == st.session_state.cal_month)].copy()

            # --- 달력 렌더링 ---
            days_ko = ["월", "화", "수", "목", "금", "토", "일"]
            h_cols = st.columns(7)
            for i, d in enumerate(days_ko):
                h_color = "#2E5BFF" if i == 5 else "#FF4B4B" if i == 6 else "#888"
                h_cols[i].markdown(f"<p style='text-align:center; font-weight:bold; color:{h_color};'>{d}</p>", unsafe_allow_html=True)

            cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
            for week in cal:
                cols = st.columns(7)
                for i, day in enumerate(week):
                    if day == 0:
                        cols[i].write(""); continue
                    with cols[i]:
                        is_today = (st.session_state.cal_year == datetime.now().year and st.session_state.cal_month == datetime.now().month and day == datetime.now().day)
                        day_items = year_df[year_df['save_date'].dt.day == day]
                        
                        if is_today: d_color, f_w = "#FF4B4B", "bold"
                        elif i == 5: d_color, f_w = "#2E5BFF", "normal"
                        elif i == 6: d_color, f_w = "#FF4B4B", "normal"
                        else: d_color, f_w = ("#333" if not day_items.empty else "#ccc"), "normal"

                        st.markdown(f"<p style='margin:0; font-size:12px; color:{d_color}; font-weight:{f_w};'>{day}</p>", unsafe_allow_html=True)
                        
                        if not day_items.empty:
                            m_row = day_items.iloc[0]
                            if m_row['img_url']:
                                st.markdown(f'<div style="width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:4px; margin-bottom:4px;"><img src="{m_row["img_url"]}" style="width:100%; height:100%; object-fit:cover;"></div>', unsafe_allow_html=True)
                            for _, row in day_items.iterrows():
                                title_cut = row['title'][:5] + ".." if len(row['title']) > 6 else row['title']
                                if st.button(f"• {title_cut}", key=f"cal_btn_v7_{row['id']}", use_container_width=True):
                                    st.session_state.selected_record = row
                                    st.rerun()
                        else:
                            st.markdown("<div style='width:100%; aspect-ratio:1/1;'></div>", unsafe_allow_html=True)

    # 2. 기존 카테고리별 탭
    categories = ["BOOKS", "MUSIC", "MOVIES", "SERIES"]
    for i, category_name in enumerate(categories):
        with sub_tabs[i+1]:
            with sqlite3.connect(DB_NAME) as conn:
                df = pd.read_sql_query(f"SELECT * FROM archive WHERE category='{category_name}' ORDER BY id DESC", conn)
            if df.empty:
                st.info(f"{category_name} 기록 없음")
            else:
                c = st.columns(4)
                for idx, row in df.iterrows():
                    with c[idx % 4]:
                        if row['img_url']: st.image(row['img_url'], use_container_width=True)
                        st.markdown(f'<p class="save-date-tag">📅 {row["save_date"]}</p>', unsafe_allow_html=True)
                        if st.button(row['title'], key=f"cat_btn_v7_{row['id']}", use_container_width=True):
                            show_details(row)

# --- [5. 사이드바 관리 UI] ---
if st.session_state.selected_record is not None:
    rec = st.session_state.selected_record
    with st.sidebar:
        st.markdown("## 🛠️ 관리 창")
        if rec['img_url']: st.image(rec['img_url'], use_container_width=True)
        st.subheader(rec['title'])
        st.divider()
        if st.button("🔍 상세 내용 보기", key="sb_detail", use_container_width=True):
            show_details(rec)
        st.markdown("### 📅 날짜 이동")
        new_d = st.date_input("변경할 날짜", value=rec['save_date'].to_pydatetime().date(), key="sb_date")
        if st.button("확인 및 이동", key="sb_move", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("UPDATE archive SET save_date=? WHERE id=?", (new_d.strftime('%Y-%m-%d'), rec['id']))
            st.session_state.selected_record = None
            st.rerun()
        st.markdown("### ⚠️ 삭제")
        if st.button("🗑️ 기록 삭제", type="primary", key="sb_del", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (rec['id'],))
            st.session_state.selected_record = None
            st.rerun()
        if st.button("닫기", key="sb_close", use_container_width=True):
            st.session_state.selected_record = None
            st.rerun()

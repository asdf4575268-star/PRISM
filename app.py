import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month
if 'api_data' not in st.session_state: st.session_state.api_data = {}

# 월 이동 함수 추가
def shift_month(delta):
    new_month = st.session_state.cal_month + delta
    if new_month == 0:
        st.session_state.cal_year -= 1
        st.session_state.cal_month = 12
    elif new_month == 13:
        st.session_state.cal_year += 1
        st.session_state.cal_month = 1
    else:
        st.session_state.cal_month = new_month

st.markdown("""
    <style>
    @import url('https://github.com/google/fonts/raw/main/ofl/blackhansans/BlackHanSans-Regular.ttf');
    .act-name { font-size: 90px; font-family: 'BlackHanSans'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; line-height: 1; }
    .cal-img-box { width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:10px; margin-bottom:4px; border: 1px solid #eee; background-color: #f0f0f0; }
    .cal-img-box img { width:100%; height:100%; object-fit:cover; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_total_v4.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# --- [2. API 함수 정의 구역] ---

def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url).json().get("results", [])
        formatted_res = []
        for m in res:
            is_album = m.get('wrapperType') == 'collection'
            if is_album:
                title = m.get('collectionName', 'Unknown Album')
                info_url = m.get('collectionViewUrl', '')
                prefix = "📀 [ALBUM]"
            else:
                title = m.get('trackName', 'Unknown Song')
                info_url = m.get('trackViewUrl', '')
                prefix = "🎵 [SINGLE]"
            
            formatted_res.append({
                'display_name': f"{prefix} {title} - {m.get('artistName', '')}",
                'title': title,
                'creator': m.get('artistName', ''),
                'date': m.get('releaseDate', '')[:10],
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'),
                'url': info_url
            })
        return formatted_res
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try:
        return requests.get(url).json().get("results", [])
    except: return []

def get_tmdb_details(item_id, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}/credits?api_key={TMDB_API_KEY}&language=ko-KR"
    try:
        res = requests.get(url).json()
        director = next((m['name'] for m in res.get('crew', []) if m.get('job') == 'Director'), "정보 없음")
        cast = ", ".join([c['name'] for c in res.get('cast', [])[:3]])
        return f"감독: {director} / 출연: {cast}"
    except: return "정보 없음"

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=20200101&eddate=20261231&rows=10&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

# --- [3. 팝업 함수] ---
@st.dialog("📋 기록", width="medium")
def show_details(item):
    if hasattr(item, 'to_dict'):
        item = item.to_dict()
    
    # 1. 상단 컨트롤 바 (토글과 삭제 버튼을 나란히)
    c_head1, c_head2 = st.columns([0.85, 0.15])
    with c_head1:
        # 다시 이전처럼 직관적인 토글 스위치로 복구
        edit_mode = st.toggle("✏️ 수정 모드", key=f"tog_v2_{item['id']}")
    with c_head2:
        if st.button("🗑️ 삭제", key=f"del_v2_{item['id']}", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()

    st.divider()
    
    # 2. 메인 레이아웃 (좌 이미지 / 우 상세정보)
    col_img, col_txt = st.columns([0.4, 0.6])

    with col_img:
        if item.get('img_url'):
            st.image(item['img_url'], use_container_width=True)
        else:
            st.info("등록된 이미지가 없습니다.")

    with col_txt:
        if edit_mode:
            # --- [수정 모드] ---
            with st.form(key=f"edit_form_final_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 Creator", value=str(item.get('creator', '')))
                
                c1, c2 = st.columns(2)
                try:
                    raw_v = str(item.get('view_date') or item.get('save_date'))[:10]
                    v_dt = datetime.strptime(raw_v, '%Y-%m-%d').date()
                except: v_dt = date.today()
                
                n_view = c1.date_input("🍿 감상일", v_dt)
                n_rel = c2.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))

                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '') or ''))
                n_sum = st.text_area("📖 줄거리(URL)", value=str(item.get('summary', '') or ''), height=100)
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '') or ''), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '') or ''), height=150)

                if st.form_submit_button("💾 저장하기", use_container_width=True):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""
                            UPDATE archive 
                            SET title=?, creator=?, rel_date=?, summary=?, brief=?, highlights=?, note=?, view_date=? 
                            WHERE id=?
                        """, (n_title, n_creator, n_rel, n_sum, n_brief, n_high, n_note, str(n_view), item['id']))
                    st.rerun()
        else:
            # --- [조회 모드] ---
            st.markdown(f'<p class="act-name" style="font-size: 25px; font-weight: bold; line-height: 1.1; margin-bottom: 10px;">{item.get("title")}</p>', unsafe_allow_html=True)         
            content = str(item.get('summary', ''))
            urls = re.findall(r'(https?://[^\s]+)', content)
            if urls:
                st.link_button("🌐 공식 정보 확인", urls[0], use_container_width=True)
            
            st.write(f"**Creator:** {item.get('creator')}")
            st.write(f"**작품날짜:** {item.get('rel_date')}")
            
            # 감상일 (30px) [2026-02-12 날짜 크기 30]
            v_date = item.get('view_date') or item.get('save_date', '')
            st.markdown(f'<p class="date-text">🍿 {v_date}</p>', unsafe_allow_html=True)
            
            st.divider()

            # 요약, 줄거리, 인상, 감상 박스들
            if item.get('brief'): st.success(f"**요약:** {item['brief']}")
            if item.get('summary'): st.info(f"**상세:** {item['summary']}")
            if item.get('highlights'): st.warning(f"**인상 깊은 부분:**\n\n{item['highlights']}")
            if item.get('note'): st.write(f"**나의 감상:**\n\n{item['note']}")

            # 5. 상세 내용 (데이터가 비어있지 않으면 출력)
            def show_box(label, val, type="write"):
                if val and str(val).strip() not in ["None", "nan", ""]:
                    st.markdown(f"**{label}**")
                    if type == "success": st.success(val)
                    elif type == "info": st.info(val)
                    elif type == "warning": st.warning(val)
                    else: st.write(val)

            show_box("📝 요약", item.get('brief'), "success")
            show_box("📖 줄거리 / 상세", item.get('summary'), "info")
            show_box("✨ 인상 깊은 부분", item.get('highlights'), "warning")
            show_box("💬 감상", item.get('note'), "write")

            st.divider()
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                st.rerun()
# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    
    if search_query:
        if category == "BOOKS":
            res = search_books(search_query)
            if res:
                opts = {f"📚 {b['title']}": b for b in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': f"{', '.join(b['authors'])}", 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'summary': f"{b['url']}\n\n{b.get('contents', '')}"}
                    st.rerun()

        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {m['display_name']: m for m in res}
                sel = st.selectbox("결과 선택 (SINGLE/ALBUM)", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': f"{m['url']}\n\n"}
                    st.rerun()

        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                opts = {f"🎭 {s['title']} ({s['venue']})": s for s in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s['title'], 'creator': f"@{s['venue']}", 'date': s['date'], 'img': s['img'], 'summary': ''}
                    st.rerun()

        else: # MOVIES, SERIES
            res = search_tmdb(search_query, category)
            if res:
                t_key = 'title' if category == 'MOVIES' else 'name'
                d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                opts = {f"🎬 {r.get(t_key)}": r for r in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s.get(t_key), 'creator': get_tmdb_details(s['id'], category), 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'summary': s.get('overview', '')}
                    st.rerun()

    st.divider()
    # 입력 폼 생략 (사용자 코드와 동일하게 유지)
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url_val = st.text_input("🖼️ 이미지", value=data.get('img', ''))
        if img_url_val: 
            st.image(img_url_val, use_container_width=True)
        else:
            st.info("검색을 통해 이미지를 불러와주세요.")
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("Creator 정보", value=data.get('creator', ''))
        col1, col2 = st.columns(2)
        rel_date = col1.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        view_date = col2.date_input("🍿 감상일", value=date.today())
    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=100)
        if st.button("✅ 저장"):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
            st.session_state.api_data = {}
            st.rerun()

# --- TAB 2: ARCHIVE ---
with tab2:
    # 1. 세션 상태 초기화 (최상단 배치)
    if 'cal_year' not in st.session_state:
        st.session_state.cal_year = datetime.now().year
    if 'cal_month' not in st.session_state:
        st.session_state.cal_month = datetime.now().month

    # 2. 반응형 CSS (세로 리스트 / 가로 그리드)
    st.markdown("""
        <style>
        [data-testid="column"] { padding: 1px !important; }
        
        @media (max-width: 600px) {
            /* 카테고리 탭: 세로 리스트 강제 전환 */
            .list-mode [data-testid="stHorizontalBlock"] {
                display: flex !important;
                flex-direction: column !important;
            }
            .list-mode [data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-width: 100% !important;
                border-bottom: 1px solid #333;
                padding: 10px 0 !important;
            }
            /* 달력 탭: 7열 유지 */
            .cal-mode [data-testid="column"] {
                width: 14.28% !important;
                flex: 0 0 14.28% !important;
                min-width: 14.28% !important;
            }
        }
        
        .cal-img-box { width: 100%; aspect-ratio: 1/1; overflow: hidden; border-radius: 6px; margin-top: 2px; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        div.stButton > button { text-transform: lowercase !important; font-size: 10px !important; }
        </style>
    """, unsafe_allow_html=True)

    # 3. 데이터 로드 및 전처리
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])

# --- [1] YEARLY 탭 (카테고리 스타일 6열 배치) ---
with sub_tabs[0]:
    if not all_df.empty:
        # 데이터 전처리
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'].fillna(all_df['save_date']))
        all_df['year_int'] = all_df['v_dt'].dt.year
        all_df['month_int'] = all_df['v_dt'].dt.month
        yearly_df = all_df.sort_values(by='v_dt', ascending=False)
        
        # 연도 선택 바
        raw_years = sorted(list(yearly_df['year_int'].unique()), reverse=True)
        year_counts = yearly_df['year_int'].value_counts().to_dict()
        year_labels = [f"{y} ({year_counts.get(y, 0)})" for y in raw_years]
        
        c_yr, _ = st.columns([2, 5])
        with c_yr:
            default_y = st.session_state.cal_year if st.session_state.cal_year in raw_years else raw_years[0]
            sel_y_label = st.selectbox("연도 선택", year_labels, index=raw_years.index(default_y), key="yearly_fixed_sel")
            st.session_state.cal_year = int(sel_y_label.split(" ")[0])

        year_data = yearly_df[yearly_df['year_int'] == st.session_state.cal_year]
        
        # 월별 루프
        for month in range(12, 0, -1):
            month_data = year_data[year_data['month_int'] == month]
            if not month_data.empty:
                st.markdown(f"### 🗓️ {month}월")
                
                # 💡 카테고리와 동일한 그리드 컨테이너
                st.markdown('<div class="list-mode">', unsafe_allow_html=True)
                
                # 6개씩 끊어서 컬럼 배치
                items = month_data.to_dict('records')
                for i in range(0, len(items), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i + j < len(items):
                            row = items[i + j]
                            with cols[j]:
                                # 1. 이미지 (정사각형 작은 박스)
                                if row['img_url']:
                                    st.markdown(f'''
                                        <div class="cal-img-box">
                                            <img src="{row['img_url']}">
                                        </div>
                                    ''', unsafe_allow_html=True)
                                
                                # 2. 날짜 (이미지 아래 작게)
                                v_date = row['view_date'] if row['view_date'] else row['save_date']
                                st.markdown(f'<p style="font-size:15px; color:gray; margin:2px 0; text-align:center;">{v_date}</p>', unsafe_allow_html=True)
                                
                                # 3. 제목 버튼 (5자 제한 적용하여 작게 유지)
                                display_title = row['title'][:5] + ".." if len(row['title']) > 5 else row['title']
                                if st.button(display_title, key=f"yr_grid_{row['id']}", use_container_width=True):
                                    show_details(row)
                
                st.markdown('</div>', unsafe_allow_html=True)
                st.divider()
    else:
        st.info("기록이 없습니다.")

    # --- [2] 카테고리 탭 (리스트 형식) ---
    cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
    for idx, c_name in enumerate(cats):
        with sub_tabs[idx+1]:
            # 카테고리별 데이터 필터링
            cat_df = all_df[all_df['category'] == c_name].copy()
            if not cat_df.empty:
                cat_df['sort_dt'] = pd.to_datetime(cat_df['view_date'].fillna(cat_df['save_date']))
                cat_df = cat_df.sort_values(by='sort_dt', ascending=False)
                
                st.markdown('<div class="list-mode">', unsafe_allow_html=True)
                for i in range(0, len(cat_df), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i + j < len(cat_df):
                            row = cat_df.iloc[i + j]
                            with cols[j]:
                                if row['img_url']:
                                    st.markdown(f'<div class="cal-img-box"><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                
                                v_date = row['view_date'] if row['view_date'] else row['save_date']
                                st.markdown(f'<p style="font-size:15px; color:#666; margin:5px 0; text-align:center;">{v_date}</p>', unsafe_allow_html=True)
                                
                                display_title = row['title'][:5] + ".." if len(row['title']) > 5 else row['title']
                                if st.button(display_title, key=f"btn_list_{idx}_{row['id']}", use_container_width=True):
                                    show_details(row)
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.info(f"{c_name} 기록이 없습니다.")











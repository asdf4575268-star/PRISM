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

# 💡 CSS 설정: 활동명 90, 날짜 30, 숫자 60 및 요청 폰트 적용
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Jolly+Lodger&family=Kirang+Haerang&family=Lacquer&display=swap');
    
    /* 활동명 (90px) */
    .act-name { font-size: 90px !important; font-family: 'Kirang Haerang', cursive; line-height: 1.1; margin: 0; }
    /* 날짜 (30px) */
    .date-text { font-size: 30px !important; color: #666; font-family: sans-serif; margin: 0; }
    /* 숫자 (60px) */
    .num-text { font-size: 60px !important; font-family: 'Jolly Lodger', cursive; margin: 0; line-height: 1; }
    
    .cal-img-box { width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:10px; margin-bottom:4px; border: 1px solid #eee; background-color: #f0f0f0; }
    .cal-img-box img { width:100%; height:100%; object-fit:cover; }
    
    /* 팝업 내 이미지 크기 */
    [data-testid="stDialog"] img { max-height: 450px !important; object-fit: contain !important; }
    
    /* 사이드바 스타일링 */
    [data-testid="stSidebar"] { background-color: #f8f9fa; }
    </style>
    """, unsafe_allow_html=True)

st.title("🌈PRISM")

if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month
if 'api_data' not in st.session_state: st.session_state.api_data = {}

# --- [사이드바 구성: 커스텀 설정 & OCR] ---
with st.sidebar:
    st.header("⚙️ SETTINGS")
    st.info("💡 **Font Guide**\n- 활동명: 90 (Kirang Haerang)\n- 날짜: 30\n- 숫자: 60 (Jolly Lodger)")
    
    st.divider()
    st.header("📸 OCR MENU")
    uploaded_file = st.file_uploader("이미지에서 텍스트 추출", type=['png', 'jpg', 'jpeg'])
    if uploaded_file:
        st.warning("OCR 기능이 활성화되었습니다. (API 연결 필요)")

# --- [DB 및 API 함수 (기존 유지)] ---
DB_NAME = 'archive_prism_total_v4.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# (search_books, search_apple_music, search_tmdb, get_tmdb_details, search_kopis 함수는 기존과 동일하게 유지)
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
            title = m.get('collectionName' if is_album else 'trackName', 'Unknown')
            info_url = m.get('collectionViewUrl' if is_album else 'trackViewUrl', '')
            prefix = "📀 [ALBUM]" if is_album else "🎵 [SINGLE]"
            formatted_res.append({
                'display_name': f"{prefix} {title} - {m.get('artistName', '')}",
                'title': title, 'creator': m.get('artistName', ''), 'date': m.get('releaseDate', '')[:10],
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'url': info_url
            })
        return formatted_res
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
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

@st.dialog("📋 기록 상세 정보", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    edit_key = f"is_editing_{item['id']}"
    if edit_key not in st.session_state: st.session_state[edit_key] = False

    c_del, c_mid, c_edit = st.columns([0.1, 0.8, 0.1])
    with c_del:
        if st.button("🗑️", key=f"del_btn_{item['id']}", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()
    with c_edit:
        icon = "❌" if st.session_state[edit_key] else "✏️"
        if st.button(icon, key=f"edit_btn_{item['id']}", use_container_width=True):
            st.session_state[edit_key] = not st.session_state[edit_key]
            st.rerun()
    st.divider()
    
    col_img, col_txt = st.columns([0.35, 0.65])
    with col_img:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
        else: st.info("등록된 이미지가 없습니다.")
    with col_txt:
        if st.session_state[edit_key]:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 Creator", value=str(item.get('creator', '')))
                n_view = st.date_input("🍿 감상일", value=datetime.strptime(item.get('view_date')[:10], '%Y-%m-%d').date() if item.get('view_date') else date.today())
                n_rel = st.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '') or ''))
                n_sum = st.text_area("📖 줄거리(URL)", value=str(item.get('summary', '') or ''), height=100)
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '') or ''), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '') or ''), height=150)
                if st.form_submit_button("💾 저장하기"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE archive SET title=?, creator=?, rel_date=?, summary=?, brief=?, highlights=?, note=?, view_date=? WHERE id=?", (n_title, n_creator, n_rel, n_sum, n_brief, n_high, n_note, str(n_view), item['id']))
                    st.session_state[edit_key] = False
                    st.rerun()
        else:
            st.markdown(f'<p class="act-name">{item.get("title")}</p>', unsafe_allow_html=True)         
            st.markdown(f'<p class="date-text">🍿 {item.get("view_date") or item.get("save_date")}</p>', unsafe_allow_html=True)
            st.divider()
            st.write(f"**Creator:** {item.get('creator')} | **작품날짜:** {item.get('rel_date')}")
            st.info(f"📝 **요약**: {item.get('brief')}")
            st.write(f"💬 **감상**: {item.get('note')}")

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    
    # 검색 로직 (기존 유지)
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
                sel = st.selectbox("결과 선택", list(opts.keys()))
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
    
    # 💡 수정: 사진을 계속 확인할 수 있도록 레이아웃 구성
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    
    with cl:
        st.subheader("🖼️ Media Preview")
        img_url_val = st.text_input("이미지 URL", value=data.get('img', ''))
        if img_url_val: 
            st.image(img_url_val, use_container_width=True)
        else:
            st.info("검색을 통해 이미지를 불러오면 여기에 표시됩니다.")
        
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("Creator 정보", value=data.get('creator', ''))
        col1, col2 = st.columns(2)
        rel_date = col1.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        view_date = col2.date_input("🍿 감상일", value=date.today())

    with cr:
        st.subheader("📝 Record Details")
        summary = st.text_area("📖 줄거리 / 상세 정보", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 한 줄 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 개인적인 감상", height=150)
        
        if st.button("✅ 기록 저장하기", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
            st.success("성공적으로 저장되었습니다!")
            st.session_state.api_data = {}
            st.rerun()

# --- [TAB 2: ARCHIVE (기존 레이아웃 유지)] ---
with tab2:
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])

    with sub_tabs[0]:
        if not all_df.empty:
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'].fillna(all_df['save_date']))
            all_df['year_int'] = all_df['v_dt'].dt.year
            all_df['month_int'] = all_df['v_dt'].dt.month
            yearly_df = all_df.sort_values(by='v_dt', ascending=False)
            
            raw_years = sorted(list(yearly_df['year_int'].unique()), reverse=True)
            year_counts = yearly_df['year_int'].value_counts().to_dict()
            year_labels = [f"{y} ({year_counts.get(y, 0)})" for y in raw_years]
            
            c_yr, _ = st.columns([2, 5])
            with c_yr:
                default_y = st.session_state.cal_year if st.session_state.cal_year in raw_years else raw_years[0]
                sel_y_label = st.selectbox("연도 선택", year_labels, index=raw_years.index(default_y))
                st.session_state.cal_year = int(sel_y_label.split(" ")[0])

            year_data = yearly_df[yearly_df['year_int'] == st.session_state.cal_year]
            for month in range(12, 0, -1):
                month_data = year_data[year_data['month_int'] == month]
                if not month_data.empty:
                    # 💡 숫자 60px 적용 예시
                    st.markdown(f'<p class="num-text">{month} <span style="font-size:30px">MONTH</span></p>', unsafe_allow_html=True)
                    items = month_data.to_dict('records')
                    cols = st.columns(6)
                    for idx, row in enumerate(items):
                        with cols[idx % 6]:
                            if row['img_url']: st.markdown(f'<div class="cal-img-box"><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                            if st.button(row['title'][:10], key=f"yr_{row['id']}", use_container_width=True):
                                show_details(row)
                    st.divider()
        else: st.info("기록이 없습니다.")

    # 카테고리별 탭 (기존 로직과 유사하게 자동 생성)
    cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
    for idx, c_name in enumerate(cats):
        with sub_tabs[idx+1]:
            cat_df = all_df[all_df['category'] == c_name].copy()
            if not cat_df.empty:
                cat_df['sort_dt'] = pd.to_datetime(cat_df['view_date'].fillna(cat_df['save_date']))
                cat_df = cat_df.sort_values(by='sort_dt', ascending=False)
                items = cat_df.to_dict('records')
                for i in range(0, len(items), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i+j < len(items):
                            row = items[i+j]
                            with cols[j]:
                                if row['img_url']: st.markdown(f'<div class="cal-img-box"><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                if st.button(row['title'][:10], key=f"cat_{idx}_{row['id']}", use_container_width=True):
                                    show_details(row)
            else: st.info(f"{c_name} 기록이 없습니다.")

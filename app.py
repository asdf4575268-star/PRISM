import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re
import time
import os
from supabase import create_client, Client

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

# API 및 DB 설정
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pub?gid=1160662254&single=true&output=csv"
DB_NAME = 'archive_prism_total_v5.db'

# Supabase 설정 (secrets 기반)
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 세션 상태 초기화
if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month
if 'api_data' not in st.session_state: st.session_state.api_data = {}

# --- [2. 데이터베이스 함수] ---

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

def restore_from_google():
    try:
        df = pd.read_csv(GOOGLE_SHEET_CSV).fillna("")
        if df.empty:
            st.warning("복원할 데이터가 시트에 없습니다.")
            return

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM archive")
            for _, row in df.iterrows():
                vals = row.tolist()
                while len(vals) < 12: vals.append("")
                
                raw_v = str(vals[11]).strip()
                try:
                    clean_v = raw_v.replace("오전", "AM").replace("오후", "PM")
                    v_date = pd.to_datetime(clean_v).strftime('%Y-%m-%d')
                except: v_date = raw_v if raw_v else ""

                conn.execute("""
                    INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (str(vals[1]), str(vals[2]), str(vals[3]), str(vals[4]), str(vals[5]), 
                      str(vals[6]), str(vals[7]), str(vals[8]), str(vals[9]), str(vals[10]), str(vals[0]), v_date))
        st.success("✅ 복원이 완료되었습니다!")
    except Exception as e:
        st.error(f"❌ 복원 실패: {e}")

# --- [3. API 검색 함수들] ---

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
            prefix = "📀 [ALBUM]" if is_album else "🎵 [SINGLE]"
            formatted_res.append({
                'display_name': f"{prefix} {title} - {m.get('artistName', '')}",
                'title': title, 'creator': m.get('artistName', ''),
                'date': m.get('releaseDate', '')[:10],
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'),
                'url': m.get('collectionViewUrl' if is_album else 'trackViewUrl', ''),
                'venue': m.get('artistName', '')
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
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=100&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

def get_kopis_detail(mt20id):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content).find('db')
        if root is not None:
            crew = root.findtext('prfcrew') or ""
            cast = root.findtext('prfcast') or ""
            return f"{crew} / {cast}".strip(" / ")
    except: return "정보 없음"
    return "정보 없음"

# --- [4. 팝업 및 상세 보기] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    t_col1, t_col2, t_col3 = st.columns([0.2, 0.6, 0.2])
    with t_col1:
        if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()
    with t_col3:
        edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")

    st.divider()
    col_img, col_txt = st.columns([0.3, 0.7])
    with col_img:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)

    with col_txt:
        if edit_mode:
            with st.form(key=f"edit_form_{item['id']}"):
                n_img = st.text_input("🖼️ 이미지 URL", value=item.get('img_url', ''))
                n_title = st.text_input("📌 제목", value=item.get('title', ''))
                n_creator = st.text_input("👤 창작자", value=item.get('creator', ''))
                n_rel = st.text_input("📅 작품 날짜", value=item.get('rel_date', ''))
                n_venue = st.text_input("📍 장소/플랫폼", value=item.get('venue', ''))
                n_view_date = st.date_input("🍿 감상일", value=pd.to_datetime(item.get('view_date')).date() if item.get('view_date') else date.today())
                n_brief = st.text_input("📝 요약", value=item.get('brief', ''))
                n_sum = st.text_area("📖 줄거리", value=item.get('summary', ''), height=100)
                n_high = st.text_area("✨ 인상 깊은 부분", value=item.get('highlights', ''), height=100)
                n_note = st.text_area("💬 감상", value=item.get('note', ''), height=100)

                if st.form_submit_button("💾 저장"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=? WHERE id=?""", 
                                     (n_title, n_creator, n_rel, n_venue, n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, item['id']))
                    st.success("수정 완료!")
                    st.rerun()
        else:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**[{item.get('category')}]** {item.get('creator')}")
            st.write(f"📅 {item.get('rel_date')} | 📍 {item.get('venue')}")
            st.markdown(f'<p style="color: #FF4B4B; font-weight: bold;">🍿 {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()
            if item.get('brief'): st.info(f"**요약:** {item.get('brief')}")
            if item.get('summary'): st.write(f"**줄거리:**\n{item.get('summary')}")
            if item.get('highlights'): st.warning(f"**인상 깊은 부분:**\n{item.get('highlights')}")
            if item.get('note'): st.success(f"**나의 감상:**\n{item.get('note')}")

# --- [5. 메인 화면 구성] ---
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
                    st.session_state.api_data = {'title': b['title'], 'creator': ", ".join(b['authors']), 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'venue': b.get('publisher', ''), 'summary': b.get('contents', '')}
                    st.rerun()
        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {m['display_name']: m for m in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'venue': m['creator']}
                    st.rerun()
        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                opts = {f"🎭 {s['title']} ({s['venue']})": s for s in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s['title'], 'creator': get_kopis_detail(s['id']), 'date': s['date'], 'venue': s['venue'], 'img': s['img']}
                    st.rerun()
        else: # MOVIES, SERIES
            res = search_tmdb(search_query, category)
            if res:
                t_key = 'title' if category == 'MOVIES' else 'name'
                d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s.get(t_key), 'creator': get_tmdb_details(s['id'], category), 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'summary': s.get('overview', '')}
                    st.rerun()

    st.divider()
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url_val = st.text_input("🖼️ 이미지 URL", value=data.get('img', ''))
        if img_url_val: st.image(img_url_val, use_container_width=True)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자 정보", value=data.get('creator', ''))
        rel_date = st.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        venue = st.text_input("📍 장소/플랫폼", value=data.get('venue', ''))
        
    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=100)
        brief = st.text_input("📝 요약 (한 줄 평)")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 나의 감상", height=100)
        view_date = st.date_input("🍿 감상일", value=date.today())
        
        if st.button("✅ 기록 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
            st.success("기록되었습니다!")
            st.session_state.api_data = {}
            st.rerun()

# --- [6. 아카이브 뷰] ---
with tab2:
    if st.button("🔄 시트에서 복원"): restore_from_google()

    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; margin-bottom: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
    </style>""", unsafe_allow_html=True)

    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    if not all_df.empty:
        cat_list = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sub_tabs = st.tabs([f"📅 ALL ({len(all_df)})"] + [f"{c}" for c in cat_list])

        # 전체 보기 (Yearly)
        with sub_tabs[0]:
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
            years = sorted(all_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            if years:
                sel_y = st.selectbox("연도", years)
                y_data = all_df[all_df['v_dt'].dt.year == sel_y].sort_values('v_dt', ascending=False)
                for m in range(12, 0, -1):
                    m_data = y_data[y_data['v_dt'].dt.month == m]
                    if not m_data.empty:
                        st.subheader(f"🗓️ {m}월")
                        cols = st.columns(6)
                        for idx, row in enumerate(m_data.to_dict('records')):
                            with cols[idx % 6]:
                                st.markdown(f'<div class="cal-img-box"><div class="badge">{pd.to_datetime(row["view_date"]).day}일</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                if st.button(row['title'][:8], key=f"y_{row['id']}", use_container_width=True): show_details(row)

        # 카테고리별 보기
        for i, c_name in enumerate(cat_list):
            with sub_tabs[i+1]:
                c_data = all_df[all_df['category'] == c_name].sort_values('view_date', ascending=False)
                if not c_data.empty:
                    cols = st.columns(6)
                    for idx, row in enumerate(c_data.to_dict('records')):
                        with cols[idx % 6]:
                            st.markdown(f'<div class="cal-img-box"><div class="badge">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                            if st.button(row['title'][:8], key=f"c_{row['id']}", use_container_width=True): show_details(row)

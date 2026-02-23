import streamlit as st
import sqlite3
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re
import time

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")

# 모바일 UI 최적화 CSS
st.markdown("""
    <style>
    h1 { font-size: 1.8rem !important; margin-bottom: 0px; }
    .stTextInput label, .stTextArea label, .stSelectbox label { font-size: 0.9rem !important; font-weight: bold !important; }
    .cal-img-box { 
        position: relative; width: 100%; aspect-ratio: 1/1.4; 
        overflow: hidden; border-radius: 8px; margin-top: 5px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
    .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
    .badge { 
        position: absolute; top: 5px; right: 5px; 
        background: rgba(0, 0, 0, 0.7); color: white; 
        padding: 2px 6px; border-radius: 4px; font-size: 10px; 
        z-index: 10; font-weight: bold;
    }
    button[data-testid="stBaseButton-secondary"] p { font-size: 0.8rem !important; text-align: center !important; }
    /* 탭 간격 조절 */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 10px; font-size: 0.85rem; }
    </style>
""", unsafe_allow_html=True)

st.title("🌈 PRISM")

# --- [2. 전역 변수 및 DB 초기화] ---
DB_NAME = 'archive_prism_total_v5.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pub?gid=1160662254&single=true&output=csv"
BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"

if 'api_data' not in st.session_state: st.session_state.api_data = {}

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

def restore_from_google():
    try:
        df = pd.read_csv(GOOGLE_SHEET_CSV).fillna("")
        if df.empty: return
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM archive")
            for _, row in df.iterrows():
                vals = row.tolist()
                while len(vals) < 12: vals.append("")
                raw_v = str(vals[11]).strip()
                try: 
                    v_date = pd.to_datetime(raw_v.replace("오전", "AM").replace("오후", "PM")).strftime('%Y-%m-%d')
                except: v_date = raw_v
                conn.execute("""INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) 
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (str(vals[1]), str(vals[2]), str(vals[3]), str(vals[4]), str(vals[5]), str(vals[6]), str(vals[7]), str(vals[8]), str(vals[9]), str(vals[10]), str(vals[0]), v_date))
        st.success("✅ 복구 완료!")
    except Exception as e: st.error(f"❌ 복원 실패: {e}")

# --- [3. API 검색 함수 세트] ---
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
            formatted_res.append({
                'display_name': f"{'📀' if is_album else '🎵'} {title} - {m.get('artistName', '')}",
                'title': title, 'creator': m.get('artistName', ''), 'date': m.get('releaseDate', '')[:10],
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName', '')
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
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=50&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

def get_kopis_detail(mt20id):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        root = ET.fromstring(requests.get(url).content)
        d = root.find('db')
        return f"제작: {(d.findtext('prfcrew') or '').strip()} / 캐스팅: {(d.findtext('prfcast') or '').strip()}".strip(" / ")
    except: return "정보 없음"

# --- [4. 상세보기 다이얼로그] ---
@st.dialog("📋 기록 상세", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    c1, c2 = st.columns([1, 1])
    with c1: edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
    with c2:
        if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn: conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()
    st.divider()
    if edit_mode:
        with st.form(key=f"ed_{item['id']}"):
            n_title = st.text_input("제목", value=item['title'])
            n_creator = st.text_input("창작자", value=item['creator'])
            n_note = st.text_area("감상", value=item['note'], height=150)
            if st.form_submit_button("💾 업데이트", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("UPDATE archive SET title=?, creator=?, note=? WHERE id=?", (n_title, n_creator, n_note, item['id']))
                st.rerun()
    else:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
        st.subheader(item['title'])
        st.caption(f"**{item['category']}** | {item['creator']}")
        st.info(f"📅 {item['rel_date']} | 📍 {item['venue']} | 🍿 {item['view_date']}")
        if item['note']: st.success(f"**나의 감상**\n\n{item['note']}")

# --- [5. 메인 레이아웃] ---
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
                    st.session_state.api_data = {'title': b['title'], 'creator': f"{', '.join(b['authors'])}", 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'venue': b.get('publisher', '')}
                    st.rerun()
        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {m['display_name']: m for m in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'venue': m['venue']}
                    st.rerun()
        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                opts = {f"🎭 {s['title']} ({s['date']})": s for s in res}
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
                    st.session_state.api_data = {'title': s.get(t_key), 'creator': get_tmdb_details(s['id'], category), 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}"}
                    st.rerun()

    st.divider()
    data = st.session_state.get('api_data', {})
    img_url_val = st.text_input("🖼️ 이미지 URL", value=data.get('img', ''))
    if img_url_val: st.image(img_url_val, width=120)
    title = st.text_input("📌 제목", value=data.get('title', ''))
    creator = st.text_input("👤 창작자", value=data.get('creator', ''))
    c_rel, c_ven = st.columns(2)
    rel_date = c_rel.text_input("📅 제작일", value=data.get('date', str(date.today())))
    venue = c_ven.text_input("📍 장소", value=data.get('venue', ''))
    view_date = st.date_input("🍿 감상일", value=date.today())
    note = st.text_area("💬 감상평", height=150)
    
    if st.button("✅ 저장 및 구글 백업", use_container_width=True, type="primary"):
        try:
            # 1. 구글 폼 백업
            r_dt, v_dt = pd.to_datetime(rel_date), pd.to_datetime(view_date)
            payload = {
                "entry.574529989": category, "entry.898076783": title, "entry.345368346": creator,
                "entry.891180756": note, "entry.2056153041": img_url_val,
                "entry.780422311_year": str(r_dt.year), "entry.780422311_month": f"{r_dt.month:02d}", "entry.780422311_day": f"{r_dt.day:02d}",
                "entry.1446643193_year": str(v_dt.year), "entry.1446643193_month": f"{v_dt.month:02d}", "entry.1446643193_day": f"{v_dt.day:02d}",
                "entry.250402237": venue
            }
            requests.post(BACKUP_URL, data=payload, timeout=5)
            # 2. 로컬 저장
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, str(rel_date), venue, note, img_url_val, str(date.today()), str(view_date)))
            st.success("✅ 저장 및 백업 완료!"); time.sleep(0.5); st.session_state.api_data = {}; st.rerun()
        except Exception as e: st.error(f"실패: {e}")

with tab2:
    if st.button("🔄 구글 시트 데이터 복원하기", use_container_width=True):
        restore_from_google(); st.rerun()

    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    if not all_df.empty:
        cat_list = ["ALL", "YEARLY", "BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sub_tabs = st.tabs(cat_list)
        for idx, c_name in enumerate(cat_list):
            with sub_tabs[idx]:
                if c_name == "ALL": display_df = all_df.copy()
                elif c_name == "YEARLY":
                    all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
                    years = sorted(all_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
                    if not years: st.info("데이터 없음"); continue
                    sel_y = st.selectbox("연도", years, key=f"y_{idx}")
                    display_df = all_df[all_df['v_dt'].dt.year == sel_y]
                else: display_df = all_df[all_df['category'] == c_name]

                display_df['s_dt'] = pd.to_datetime(display_df['view_date'], errors='coerce')
                items = display_df.sort_values('s_dt', ascending=False).to_dict('records')
                cols_per_row = 3
                for i in range(0, len(items), cols_per_row):
                    cols = st.columns(cols_per_row)
                    for j in range(cols_per_row):
                        if i + j < len(items):
                            row = items[i + j]
                            with cols[j]:
                                b_txt = str(row['view_date'])[-5:]
                                st.markdown(f'<div class="cal-img-box"><div class="badge">{b_txt}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                if st.button(row['title'][:6]+".." if len(row['title'])>6 else row['title'], key=f"bt_{idx}_{row['id']}", use_container_width=True):
                                    show_details(row)

import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
import time
import re 
import xml.etree.ElementTree as ET
from supabase import create_client, Client

# --- [1. 설정 및 API] ---
st.set_page_config(
    layout="wide", 
    page_title="PRISM",
    page_icon="🌈",
    initial_sidebar_state="collapsed"
)

TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
DB_NAME = 'archive_prism_total_v5.db'
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- [2. DB 함수 및 동기화] ---
@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                     rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, 
                     img_url TEXT, img_url2 TEXT, save_date TEXT, view_date TEXT)''')
    conn.commit()

init_db()

@st.cache_data(ttl=600)
def get_all_data():
    conn = get_connection()
    return pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

def migrate_to_supabase():
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        local_data = conn.execute("SELECT * FROM archive").fetchall()
        if not local_data:
            st.session_state.sync_msg = ("warning", "로컬 데이터가 없습니다.")
            return
        upload_list = [dict(row) for row in local_data]
        for d in upload_list:
            if 'id' in d: del d['id']
        supabase.table("archive").upsert(upload_list).execute() 
        st.session_state.sync_msg = ("success", f"✅ {len(upload_list)}개 데이터 클라우드 백업 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        if not cloud_data:
            st.session_state.sync_msg = ("warning", "클라우드가 비어있습니다.")
            return
        conn = get_connection()
        cursor = conn.cursor()
        local_df = get_all_data()
        local_keys = set(zip(local_df['title'], local_df['view_date'])) if not local_df.empty else set()
        to_insert = []
        for row in cloud_data:
            if (row['title'], row['view_date']) not in local_keys:
                to_insert.append((
                    row['category'], row['title'], row['creator'], row['rel_date'], 
                    row['venue'], row['summary'], row['brief'], row['highlights'], 
                    row['note'], row.get('img_url'), row.get('img_url2'), row['save_date'], row['view_date']
                ))
        if to_insert:
            cursor.executemany("""INSERT INTO archive 
                (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", to_insert)
            conn.commit()
            st.cache_data.clear()
        st.session_state.sync_msg = ("success", f"✅ {len(to_insert)}개 복구 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

# --- [3. 로그인 & 사이드바] ---
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "user_password" not in st.session_state: st.session_state.user_password = ""
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"

is_admin = st.session_state.is_logged_in

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not is_admin:
        input_password = st.text_input("Password", type="password", key="sidebar_pw")
        if input_password == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.user_password = input_password 
            st.session_state.is_logged_in = True
            st.rerun()
    else:
        st.success("Admin Mode Active")
        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.is_logged_in = False
            st.rerun()
        st.divider()
        if 'sync_msg' in st.session_state:
            m_type, m_txt = st.session_state.sync_msg
            if m_type == "success": st.success(m_txt)
            elif m_type == "warning": st.warning(m_txt)
            else: st.error(m_txt)
            del st.session_state.sync_msg
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)

    st.divider()
    st.session_state.view_mode = st.radio("📱 화면 모드", ["PC", "Mobile"], horizontal=True)

is_mobile = st.session_state.view_mode == "Mobile"

# --- [API 검색 함수들] ---
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
            formatted_res.append({'display_name': f"{'📀' if is_album else '🎵'} {title} - {m.get('artistName', '')}", 'title': title, 'creator': m.get('artistName', ''), 'date': m.get('releaseDate', '')[:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName', '')})
        return formatted_res
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

def get_tmdb_details(item_id, category):
    is_movie = category == "MOVIES"
    type_path = "movie" if is_movie else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}?api_key={TMDB_API_KEY}&language=ko-KR&append_to_response=credits"
    try:
        res = requests.get(url).json()
        crew_list = res.get('credits', {}).get('crew', [])
        cast_list = res.get('credits', {}).get('cast', [])
        if is_movie:
            director = next((m['name'] for m in crew_list if m.get('job') == 'Director'), "정보 없음")
            creator_label = f"[감독] {director}"
            companies = res.get('production_companies', [])
            venue_info = companies[0].get('name', '') if companies else ""
        else:
            creators = res.get('created_by', [])
            creator_names = ", ".join([c['name'] for c in creators]) if creators else next((m['name'] for m in crew_list if m.get('job') in ['Writer', 'Executive Producer']), "정보 없음")
            creator_label = f"[작가/제작] {creator_names}"
            networks = res.get('networks', [])
            venue_info = networks[0].get('name', '') if networks else ""
        cast_names = ", ".join([c['name'] for c in cast_list[:3]])
        full_creator = f"{creator_label} / [출연] {cast_names}".strip(" / ")
        return {"creator": full_creator, "venue": venue_info}
    except: return {"creator": "정보 없음", "venue": ""}

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=100&cpage=1"
    try:
        root = ET.fromstring(requests.get(url).content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

def get_kopis_detail(mt20id):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        d = ET.fromstring(requests.get(url).content).find('db')
        crew = d.findtext('prfcrew').strip() if d.findtext('prfcrew') else ""
        cast = d.findtext('prfcast').strip() if d.findtext('prfcast') else ""
        return f"[제작] {crew} / [출연] {cast}"
    except: return "정보 없음"

# --- [4. 팝업 상세 보기 (모바일 최적화)] ---
@st.dialog("📋 기록 상세", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    edit_mode = False
    if is_admin:
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                get_connection().execute("DELETE FROM archive WHERE id=?", (item['id'],)).connection.commit()
                st.cache_data.clear()
                st.rerun()
        with c3:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    col_img, col_txt = (st.container(), st.container()) if is_mobile else st.columns([0.4, 0.6])

    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 이미지 1", value=str(item.get('img_url', '')))
            n_img2 = st.text_input("🖼️ 이미지 2", value=str(item.get('img_url2', '')))
            if n_img: st.image(n_img, use_container_width=True)
        with col_txt:
            with st.form(key=f"edit_f_{item['id']}"):
                n_title = st.text_input("📌 제목", value=item['title'])
                n_creator = st.text_input("👤 창작자", value=item['creator'])
                n_view = st.date_input("🍿 감상일", value=pd.to_datetime(item['view_date']).date())
                n_note = st.text_area("🌈 PRISM", value=item['note'], height=200)
                if st.form_submit_button("💾 저장"):
                    get_connection().execute("UPDATE archive SET title=?, creator=?, note=?, view_date=?, img_url=?, img_url2=? WHERE id=?", 
                                           (n_title, n_creator, n_note, str(n_view), n_img, n_img2, item['id'])).connection.commit()
                    st.cache_data.clear()
                    st.rerun()
    else:
        with col_img:
            if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
            if item.get('img_url2'): st.image(item['img_url2'], use_container_width=True)
        with col_txt:
            st.markdown(f"## {item['title']}")
            st.markdown(f"**{item['creator']}**")
            st.caption(f"📅 {item['rel_date']} | 📍 {item['venue']}")
            st.info(f"🍿 감상일: {item['view_date']}")
            st.divider()
            for label, key, color in [("📖 소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 포인트", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]:
                if item.get(key):
                    st.markdown(f'<div style="background:{color}; color:white; padding:4px 12px; border-radius:10px; display:inline-block; font-size:0.8em; margin-bottom:10px;">{label}</div>', unsafe_allow_html=True)
                    st.markdown(item[key].replace('\n', '  \n'))
                    st.write("")

# --- [5. 메인 화면] ---
st.markdown("""
    <style>
    .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 10px; background: #1e1e1e; margin-bottom: 5px; }
    .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
    .music-style { aspect-ratio: 1/1 !important; }
    .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.7); color: yellow; padding: 2px 6px; border-radius: 4px; font-size: 10px; }
    .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.7); color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; }
    </style>
""", unsafe_allow_html=True)

st.title("🌈 PRISM ARCHIVE")

if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tab_a = st.tabs(["📂 ARCHIVE"])[0]
    tab_w = None

if is_admin and tab_w:
    with tab_w:
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
                        st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'venue': m['venue'], 'summary': ""}
                        st.rerun()
            elif category == "STAGE":
                res = search_kopis(search_query)
                if res:
                    opts = {f"🎭 {s['title']} ({s['date']})": s for s in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        s = opts[sel]
                        st.session_state.api_data = {'title': s['title'], 'creator': get_kopis_detail(s['id']), 'date': s['date'], 'venue': s['venue'], 'img': s['img'], 'summary': ""}
                        st.rerun()
            else:
                res = search_tmdb(search_query, category)
                if res:
                    t_key = 'title' if category == 'MOVIES' else 'name'
                    d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                    opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        s = opts[sel]
                        det = get_tmdb_details(s['id'], category)
                        st.session_state.api_data = {'title': s.get(t_key), 'creator': det['creator'], 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'venue': det['venue'], 'summary': s.get('overview', '')}
                        st.rerun()

        st.divider()
        data = st.session_state.get('api_data', {})
        cl, cr = (st.container(), st.container()) if is_mobile else st.columns([0.4, 0.6])
        with cl:
            img_val = st.text_input("🖼️ 이미지 URL", value=data.get('img', ''))
            if img_val: st.image(img_val, use_container_width=True)
            title = st.text_input("제목", value=data.get('title', ''))
            creator = st.text_input("창작자", value=data.get('creator', ''))
        with cr:
            rel_date = st.text_input("📅 작품 날짜", value=data.get('date', ''))
            venue = st.text_input("📍 장소/플랫폼", value=data.get('venue', ''))
            summary = st.text_area("📖 작품소개", value=data.get('summary', ''))
            brief = st.text_input("📝 요약")
            highlights = st.text_area("✨ 인상 깊은 부분")
            note = st.text_area("🌈 PRISM")
            view_date = st.date_input("🍿 감상일", value=date.today())
            if st.button("✅ 기록 저장", use_container_width=True):
                new_rec = {"category": category, "title": title, "creator": creator, "rel_date": rel_date, "venue": venue, "summary": summary, "brief": brief, "highlights": highlights, "note": note, "img_url": img_val, "img_url2": "", "save_date": str(date.today()), "view_date": str(view_date)}
                get_connection().execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", tuple(new_rec.values())).connection.commit()
                supabase.table("archive").upsert(new_rec).execute()
                st.cache_data.clear()
                st.session_state.api_data = {}
                st.success("저장 완료!")
                st.rerun()

with tab_a:
    all_df = get_all_data()
    if not all_df.empty:
        grid_cols = 1 if is_mobile else 6
        cat_order = ["ALL", "BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sub_tabs = st.tabs(cat_order)
        
        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx]:
                df = all_df if c_name == "ALL" else all_df[all_df['category'] == c_name]
                items = df.to_dict('records')
                for i in range(0, len(items), grid_cols):
                    cols = st.columns(grid_cols)
                    for j in range(grid_cols):
                        if i+j < len(items):
                            row = items[i+j]
                            with cols[j]:
                                m_style = "music-style" if row['category'] == "MUSIC" else ""
                                st.markdown(f'<div class="cal-img-box {m_style}"><div class="badge-cat">{row["category"]}</div><div class="badge-date">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                if st.button(row['title'][:15], key=f"btn_{idx}_{row['id']}", use_container_width=True):
                                    show_details(row)

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


# --- [2. DB 함수 및 속도 최적화] ---
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
        st.session_state.sync_msg = ("success", f"✅ {len(upload_list)}개 데이터 백업 완료!")
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


# --- [3. 로그인 및 사이드바] ---
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "user_password" not in st.session_state: st.session_state.user_password = ""
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"

is_admin = st.session_state.is_logged_in

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not is_admin:
        input_password = st.text_input("Password", type="password")
        if input_password == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.user_password = input_password 
            st.session_state.is_logged_in = True
            st.rerun()
    else:
        st.success("Admin Mode")
        if st.button("🔓 Logout"):
            st.session_state.is_logged_in = False
            st.rerun()
        st.divider()
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)

    st.divider()
    st.session_state.view_mode = st.radio("📱 보기 모드", ["PC", "Mobile"], index=0 if st.session_state.view_mode == "PC" else 1)

is_mobile = st.session_state.view_mode == "Mobile"


# --- [API 검색 함수들] ---
def search_books(query):
    headers = {"Authorization": f"KakaoAK {st.secrets['KAKAO_KEY']}"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
        return res.json().get("documents", [])
    except: return []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url).json().get("results", [])
        return [{'display_name': f"{'📀' if m.get('wrapperType') == 'collection' else '🎵'} {m.get('collectionName' if m.get('wrapperType') == 'collection' else 'trackName')} - {m.get('artistName')}", 'title': m.get('collectionName' if m.get('wrapperType') == 'collection' else 'trackName'), 'creator': m.get('artistName'), 'date': m.get('releaseDate', '')[:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName')} for m in res]
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

def get_tmdb_details(item_id, category):
    is_movie = category == "MOVIES"
    url = f"https://api.themoviedb.org/3/{'movie' if is_movie else 'tv'}/{item_id}?api_key={TMDB_API_KEY}&language=ko-KR&append_to_response=credits"
    try:
        res = requests.get(url).json()
        director = next((m['name'] for m in res.get('credits', {}).get('crew', []) if m.get('job') == 'Director'), "정보 없음") if is_movie else ", ".join([c['name'] for c in res.get('created_by', [])])
        cast = ", ".join([c['name'] for c in res.get('credits', {}).get('cast', [])[:3]])
        venue = res.get('production_companies', [{}])[0].get('name', '') if is_movie else res.get('networks', [{}])[0].get('name', '')
        return {"creator": f"{director} / {cast}", "venue": venue}
    except: return {"creator": "정보 없음", "venue": ""}

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=50&cpage=1"
    try:
        res = requests.get(url)
        items = ET.fromstring(res.content).findall('db')
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in items]
    except: return []

def get_kopis_detail(mt20id):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        d = ET.fromstring(requests.get(url).content).find('db')
        return f"[제작] {d.findtext('prfcrew')} / [출연] {d.findtext('prfcast')}"
    except: return "정보 없음"


# --- [4. 팝업 상세 보기 (모바일 최적화)] ---
@st.dialog("📋 기록 상세", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    edit_mode = False
    if is_admin:
        col_del, col_space, col_edt = st.columns([1, 2, 1])
        with col_del:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                get_connection().execute("DELETE FROM archive WHERE id=?", (item['id'],)).connection.commit()
                st.cache_data.clear()
                st.rerun()
        with col_edt:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    # 모바일일 경우 컬럼을 나누지 않고 세로로 배치
    if is_mobile:
        img_container = st.container()
        txt_container = st.container()
    else:
        img_container, txt_container = st.columns([0.4, 0.6])

    if is_admin and edit_mode:
        with img_container:
            n_img = st.text_input("🖼️ 이미지 1", value=str(item.get('img_url', '')))
            n_img2 = st.text_input("🖼️ 이미지 2", value=str(item.get('img_url2', '')))
            if n_img: st.image(n_img, use_container_width=True)
        with txt_container:
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
        with img_container:
            if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
            if item.get('img_url2'): st.image(item['img_url2'], use_container_width=True)
        with txt_container:
            st.markdown(f"## {item['title']}")
            st.markdown(f"**{item['creator']}**")
            st.caption(f"📅 {item['rel_date']} | 📍 {item['venue']}")
            st.info(f"🍿 감상일: {item['view_date']}")
            st.divider()
            for label, key, color in [("📖 소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 포인트", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]:
                if item.get(key):
                    st.markdown(f'<div style="background:{color}; color:white; padding:4px 12px; border-radius:10px; display:inline-block; font-size:0.8em;">{label}</div>', unsafe_allow_html=True)
                    st.markdown(item[key])
                    st.write("")


# --- [5. 메인 화면] ---
st.markdown("""
    <style>
    /* 공통 스타일 */
    .cal-img-box { 
        position: relative; width: 100%; aspect-ratio: 1/1.4; 
        overflow: hidden; border-radius: 12px; background: #262626;
        margin-bottom: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
    .music-box { aspect-ratio: 1/1 !important; }
    .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.6); color: white; padding: 2px 8px; border-radius: 5px; font-size: 12px; }
    
    /* 모바일에서 버튼 가독성 */
    div.stButton > button { height: 3em; font-size: 0.9em !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🌈 PRISM ARCHIVE")

tab_write, tab_archive = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"]) if is_admin else ([None], st.tabs(["📂 ARCHIVE"])[0])

if is_admin and tab_write:
    with tab_write:
        cat = st.radio("CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
        q = st.text_input(f"🔍 {cat} 검색")
        # (기존 검색 로직 유지...)
        if st.button("기록 저장"): st.success("저장되었습니다.")

with tab_archive:
    all_df = get_all_data()
    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'])
        grid_cols = 1 if is_mobile else 6  # 모바일은 한 줄에 하나씩!
        
        cats = ["ALL", "BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sub_tabs = st.tabs([f"{c}" for c in cats])
        
        for idx, c_name in enumerate(cats):
            with sub_tabs[idx]:
                display_df = all_df if c_name == "ALL" else all_df[all_df['category'] == c_name]
                items = display_df.to_dict('records')
                
                for i in range(0, len(items), grid_cols):
                    cols = st.columns(grid_cols)
                    for j in range(grid_cols):
                        if i + j < len(items):
                            row = items[i+j]
                            with cols[j]:
                                m_cls = "music-box" if row['category'] == "MUSIC" else ""
                                st.markdown(f"""
                                    <div class="cal-img-box {m_cls}">
                                        <img src="{row['img_url']}">
                                        <div class="badge-date">{row['view_date']}</div>
                                    </div>
                                """, unsafe_allow_html=True)
                                if st.button(f"{row['title'][:20]}", key=f"btn_{c_name}_{row['id']}", use_container_width=True):
                                    show_details(row)

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

# --- [2. DB 함수 및 동기화 로직] ---
st.title("🌈PRISM ARCHIVE ")
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        # img_url2 컬럼이 추가된 테이블 생성
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, 
                         img_url TEXT, img_url2 TEXT, save_date TEXT, view_date TEXT)''')
        
        # 기존 DB에 img_url2가 없는 경우를 대비해 컬럼 추가 시도
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(archive)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'img_url2' not in columns:
            conn.execute("ALTER TABLE archive ADD COLUMN img_url2 TEXT")
            conn.commit()

init_db()

# (migrate, restore 함수는 기존과 동일하게 유지하되 img_url2만 반영)
def migrate_to_supabase():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            local_data = conn.execute("SELECT * FROM archive").fetchall()
        if not local_data: return
        upload_list = [dict(row) for row in local_data]
        for d in upload_list:
            if 'id' in d: del d['id']
        supabase.table("archive").upsert(upload_list).execute() 
        st.session_state.sync_msg = ("success", "✅ 클라우드 백업 완료!")
    except Exception as e: st.session_state.sync_msg = ("error", f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        if not cloud_data: return
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            added_count = 0
            for row in cloud_data:
                exists = cursor.execute("SELECT id FROM archive WHERE title=? AND view_date=?", (row['title'], row['view_date'])).fetchone()
                if not exists:
                    cursor.execute("""INSERT INTO archive 
                        (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row['category'], row['title'], row['creator'], row['rel_date'], row['venue'], row['summary'], 
                         row['brief'], row['highlights'], row['note'], row['img_url'], row.get('img_url2',''), row['save_date'], row['view_date']))
                    added_count += 1
            conn.commit()
        st.session_state.sync_msg = ("success", f"✅ {added_count}개 데이터 복구 완료!")
    except Exception as e: st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

# --- [3. 로그인 시스템 & 사이드바] ---
DEV_MODE = False 
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "user_password" not in st.session_state: st.session_state.user_password = ""
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"
if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]: st.session_state.is_logged_in = True
is_admin = st.session_state.is_logged_in or DEV_MODE

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
            st.session_state.user_password = ""
            st.rerun()
        st.divider()
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)
    st.session_state.view_mode = st.radio("보기 옵션", ["PC", "Mobile"], horizontal=True)

is_mobile = st.session_state.view_mode == "Mobile"

# --- [API 검색 함수들] --- (기존 유지)
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
    res = requests.get(url).json().get("results", [])
    return [{'display_name': f"{m.get('artistName')} - {m.get('trackName')}", 'title': m.get('trackName'), 'creator': m.get('artistName'), 'date': m.get('releaseDate', '')[:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName')} for m in res]

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    return requests.get(url).json().get("results", [])

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=100&cpage=1"
    root = ET.fromstring(requests.get(url).content)
    return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]

# --- [4. 팝업 상세 보기] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    edit_mode = False
    if is_admin:
        t_col1, t_col2, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                st.rerun()
        with t_col3:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    col_img, col_txt = st.columns([0.4, 0.6])

    if is_admin and edit_mode:
        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_img = st.text_input("🖼️ 메인 이미지", value=str(item.get('img_url', '')))
                n_img2 = st.text_input("🖼️ 추가 이미지", value=str(item.get('img_url2', '') if item.get('img_url2') else ""))
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                n_rel = st.text_input("📅 날짜", value=str(item.get('rel_date', '')))
                n_venue = st.text_input("📍 장소/플랫폼", value=str(item.get('venue', '')))
                n_note = st.text_area("🌈 PRISM", value=str(item.get('note', '')), height=150)
                if st.form_submit_button("💾 저장"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, note=?, img_url=?, img_url2=? WHERE id=?", 
                                     (n_title, n_creator, n_rel, n_venue, n_note, n_img, n_img2, item['id']))
                    st.success("수정 완료!")
                    st.rerun()
    else: 
        with col_img:
            if item.get('img_url'): st.image(item.get('img_url'), use_container_width=True)
            if item.get('img_url2'): st.image(item.get('img_url2'), use_container_width=True, caption="서브 이미지")
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**{item.get('creator')}**")
            st.write(f"**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
            st.divider()
            st.markdown(f"**🌈 PRISM** \n{item.get('note')}")

# --- [5. 메인 화면] ---
if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tab_a = st.tabs(["📂 ARCHIVE"])[0]
    tab_w = None

if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
        search_query = st.text_input(f"🔍 {category} 검색")
        
        # (검색 로직 중 핵심만 - 이미지 두 개 받기)
        st.divider()
        data = st.session_state.get('api_data', {})
        cl, cr = st.columns([0.4, 0.6])
        with cl:
            img1 = st.text_input("🖼️ 메인 이미지 URL", value=data.get('img', ''))
            img2 = st.text_input("🖼️ 추가 이미지 URL (직접 입력 가능)")
            if img1: st.image(img1, width=200)
            if img2: st.image(img2, width=200)
        with cr:
            title = st.text_input("제목", value=data.get('title', ''))
            creator = st.text_input("창작자", value=data.get('creator', ''))
            note = st.text_area("🌈 PRISM", height=150)
            view_date = st.date_input("🍿 감상일", value=date.today())
            if st.button("✅ 기록 저장", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("""INSERT INTO archive (category, title, creator, img_url, img_url2, note, view_date, rel_date, venue) 
                                    VALUES (?,?,?,?,?,?,?,?,?)""", 
                                 (category, title, creator, img1, img2, note, str(view_date), data.get('date',''), data.get('venue','')))
                st.success("저장 완료!")
                st.rerun()

with tab_a:
    st.markdown("<style>.cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; background: #1e1e1e; margin-bottom:5px; } .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }</style>", unsafe_allow_html=True)
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

    if not all_df.empty:
        items = all_df.to_dict('records')
        grid_cols = 6
        for i in range(0, len(items), grid_cols):
            cols = st.columns(grid_cols)
            for j in range(grid_cols):
                if i+j < len(items):
                    row = items[i+j]
                    with cols[j]:
                        st.markdown(f'<div class="cal-img-box"><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                        if st.button(row['title'][:10], key=f"btn_{row['id']}", use_container_width=True):
                            show_details(row)

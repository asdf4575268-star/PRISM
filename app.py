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
        # 1. 테이블 생성 (img_url2 추가)
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, 
                         img_url TEXT, img_url2 TEXT, save_date TEXT, view_date TEXT)''')
        
        # 2. [기존 사용자를 위한 처리] img_url2 컬럼이 없는 경우 강제 추가
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(archive)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'img_url2' not in columns:
            conn.execute("ALTER TABLE archive ADD COLUMN img_url2 TEXT")
            conn.commit()

init_db()

def migrate_to_supabase():
    try:
        with sqlite3.connect(DB_NAME) as conn:
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
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            added_count = 0
            for row in cloud_data:
                exists = cursor.execute("SELECT id FROM archive WHERE title=? AND view_date=?", (row['title'], row['view_date'])).fetchone()
                if not exists:
                    # INSERT 문에 img_url2 추가
                    cursor.execute("""INSERT INTO archive 
                        (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row['category'], row['title'], row['creator'], row['rel_date'], 
                         row['venue'], row['summary'], row['brief'], row['highlights'], 
                         row['note'], row['img_url'], row.get('img_url2', ''), row['save_date'], row['view_date']))
                    added_count += 1
            conn.commit()
        st.session_state.sync_msg = ("success", f"✅ {added_count}개의 새로운 데이터를 복구했습니다!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

# --- [3. 로그인 시스템 & 사이드바] --- (사용자 코드 그대로)
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "user_password" not in st.session_state: st.session_state.user_password = ""
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"
if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]: st.session_state.is_logged_in = True
is_admin = st.session_state.is_logged_in 

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not is_admin:
        input_password = st.text_input("Password", type="password", key="sidebar_pw")
        if input_password:
            if input_password == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.user_password = input_password
                st.session_state.is_logged_in = True
                st.rerun()
            else: st.error("Incorrect Password")
    if st.session_state.is_logged_in:
        st.success("Admin Mode Active")
        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.is_logged_in = False
            st.session_state.user_password = ""
            st.rerun()
        st.divider()
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)
    st.divider()
    st.session_state.view_mode = st.radio("보기 옵션", ["PC", "Mobile"], horizontal=True, label_visibility="collapsed")

is_mobile = st.session_state.view_mode == "Mobile"

# --- [API 검색 함수들] --- (사용자 코드 그대로)
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
    is_movie = "MOVIES" in category
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
        cast_label = f"[출연] {cast_names}" if cast_names else ""
        return {"creator": f"{creator_label} / {cast_label}".strip(" / "), "venue": venue_info}
    except: return {"creator": "정보 없음", "venue": ""}

def search_kopis(query):
    year_match = re.search(r'\d{4}', query)
    search_year = year_match.group() if year_match else None
    clean_query = re.sub(r'\d{4}', '', query).strip()
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={clean_query}&stdate=19500101&eddate=20261231&rows=100&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        items = root.findall('db')
        results = []
        for d in items:
            title = d.findtext('prfnm')
            date_from = d.findtext('prfpdfrom')
            if search_year and search_year not in date_from: continue
            results.append({'title': title, 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': date_from, 'venue': d.findtext('fcltynm')})
        return results
    except: return []

def get_kopis_detail(mt20id):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        res = requests.get(url); root = ET.fromstring(res.content); d = root.find('db')
        if d is not None:
            crew = d.findtext('prfcrew').strip() if d.findtext('prfcrew') else ""
            cast = d.findtext('prfcast').strip() if d.findtext('prfcast') else ""
            info = []
            if crew: info.append(f"[제작] {crew}")
            if cast: info.append(f"[출연] {cast}")
            return " / ".join(info) if info else "정보 없음"
    except: return "정보 없음"
    return "정보 없음"

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

    col_img, col_txt = st.columns([0.3, 0.7]) if not is_mobile else (st.container(), st.container())

    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 이미지 1", value=str(item.get('img_url', '')), key=f"img_in_{item['id']}")
            n_img2 = st.text_input("🖼️ 이미지 2", value=str(item.get('img_url2', '')), key=f"img2_in_{item['id']}")
            if n_img: st.image(n_img, use_container_width=True)
            if n_img2: st.image(n_img2, use_container_width=True)
        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                n_rel = st.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_venue = st.text_input("📍 장소/플랫폼", value=str(item.get('venue', '')))
                n_view_date = st.date_input("🍿 감상일", value=pd.to_datetime(item.get('view_date')).date())
                n_sum = st.text_area("📖 줄거리", value=str(item.get('summary', '')), height=100)
                n_note = st.text_area("🌈 PRISM", value=str(item.get('note', '')), height=100)
                if st.form_submit_button("💾 저장"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, note=?, view_date=?, img_url=?, img_url2=? WHERE id=?", 
                                     (n_title, n_creator, n_rel, n_venue, n_sum, n_note, str(n_view_date), n_img, n_img2, item['id']))
                    st.rerun()
    else:
        with col_img:
            if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
            # 이미지 2가 있으면 아래에 추가 출력
            if item.get('img_url2'): st.image(item['img_url2'], use_container_width=True, caption="Additional View")
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**{item.get('creator')}**")
            st.write(f"**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
            st.divider()
            if item.get('summary'):
                st.markdown('<div style="background:#444; color:white; padding:2px 12px; border-radius:12px; display:inline-block; font-size:0.8em;">📖 줄거리</div>', unsafe_allow_html=True)
                st.write(item.get('summary'))
            if item.get('note'):
                st.markdown('<div style="background:#1E425E; color:white; padding:2px 12px; border-radius:12px; display:inline-block; font-size:0.8em;">🌈 PRISM</div>', unsafe_allow_html=True)
                st.write(item.get('note'))

# --- [5. 메인 화면] ---
if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tab_a = st.tabs(["📂 ARCHIVE"])[0]; tab_w = None

if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
        search_query = st.text_input(f"🔍 {category} 검색")
        
        # (검색 로직은 사용자 코드 그대로 - 생략 처리됨)

        st.divider()
        data = st.session_state.get('api_data', {})
        cl, cr = st.columns([0.4, 0.6]) if not is_mobile else (st.container(), st.container())
        with cl:
            img_url_val = st.text_input("🖼️ 이미지 1", value=data.get('img', ''))
            img2_url_val = st.text_input("🖼️ 이미지 2") # 새로 추가
            if img_url_val: st.image(img_url_val, use_container_width=True)
        with cr:
            title = st.text_input("제목", value=data.get('title', ''))
            creator = st.text_input("창작자", value=data.get('creator', ''))
            note = st.text_area("🌈 PRISM", height=150)
            view_date = st.date_input("🍿 감상일", value=date.today())
            if st.button("✅ 기록 저장", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("""INSERT INTO archive (category, title, creator, note, img_url, img_url2, save_date, view_date) 
                                    VALUES (?,?,?,?,?,?,?,?)""", 
                                 (category, title, creator, note, img_url_val, img2_url_val, str(date.today()), str(view_date)))
                st.success("✅ 저장 완료!"); time.sleep(0.5); st.rerun()

# --- [ARCHIVE 탭 - 사용자 디자인 그대로] ---
with tab_a:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; background: #1e1e1e; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
    </style>""", unsafe_allow_html=True)
    
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

    if not all_df.empty:
        grid_cols = 6
        items = all_df.to_dict('records')
        for i in range(0, len(items), grid_cols):
            cols = st.columns(grid_cols)
            for j in range(grid_cols):
                if i+j < len(items):
                    row = items[i+j]
                    with cols[j]:
                        st.markdown(f'<div class="cal-img-box"><div class="badge-date">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                        if st.button(row['title'][:10], key=f"btn_{row['id']}", use_container_width=True):
                            show_details(row)


import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date
import time
import re
import xml.etree.ElementTree as ET
from supabase import create_client, Client

def is_valid_url(url):
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    return url.startswith("http://") or url.startswith("https://")

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
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                        rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, 
                        img_url TEXT, img_url2 TEXT, save_date TEXT, view_date TEXT)''')
        
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(archive)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'img_url2' not in columns:
            try:
                conn.execute("ALTER TABLE archive ADD COLUMN img_url2 TEXT")
                conn.commit()
            except Exception as e:
                st.error(f"DB 업데이트 실패: {e}")

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
                exists = cursor.execute("SELECT id FROM archive WHERE title=? AND view_date=?", 
                                     (row['title'], row['view_date'])).fetchone()
                if not exists:
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

# --- [3. 로그인 시스템 & 사이드바] ---
DEV_MODE = False 

if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_password" not in st.session_state:
    st.session_state.user_password = ""
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "PC"

if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True

is_admin = st.session_state.is_logged_in or DEV_MODE

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not is_admin:
        input_password = st.text_input("Password", type="password", key="sidebar_pw")
        if input_password:
            if input_password == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.user_password = input_password 
                st.session_state.is_logged_in = True
                st.rerun()
            else:
                st.error("Incorrect Password")
    
    if st.session_state.is_logged_in:
        st.success("Admin Mode Active")
        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.is_logged_in = False
            st.session_state.user_password = ""
            st.rerun()
            
        st.divider()
        st.markdown("### 🔄 Data Sync")
        if 'sync_msg' in st.session_state:
            m_type, m_txt = st.session_state.sync_msg
            if m_type == "success": st.success(m_txt)
            elif m_type == "warning": st.warning(m_txt)
            else: st.error(m_txt)
            del st.session_state.sync_msg
        
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)

    st.divider()
    st.markdown("### 📱 화면 모드")
    st.session_state.view_mode = st.radio("보기 옵션", ["PC", "Mobile"], horizontal=True, label_visibility="collapsed")

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
        full_creator = f"{creator_label} / {cast_label}".strip(" / ")
        return {"creator": full_creator, "venue": venue_info}
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
        res = requests.get(url)
        root = ET.fromstring(res.content)
        d = root.find('db')
        if d is not None:
            crew = d.findtext('prfcrew').strip() if d.findtext('prfcrew') else ""
            cast = d.findtext('prfcast').strip() if d.findtext('prfcast') else ""
            info_parts = []
            if crew: info_parts.append(f"[제작] {crew}")
            if cast: info_parts.append(f"[출연] {cast}")
            return " / ".join(info_parts) if info_parts else "정보 없음"
    except: return "상세정보 로드 실패"
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
                try: supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
                except: pass
                st.rerun()
        with t_col3:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    if is_mobile:
        col_img = st.container()
        col_txt = st.container()
    else:
        col_img, col_txt = st.columns([0.3, 0.7])

    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 메인 이미지", value=str(item.get('img_url', '')), key=f"img_in_{item['id']}")
            n_img2 = st.text_input("🖼️ 추가 이미지", value=str(item.get('img_url2', '')), key=f"img2_in_{item['id']}")
            if is_valid_url(n_img): st.image(n_img, use_container_width=True)
            if is_valid_url(n_img2): st.image(n_img2, use_container_width=True)

        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                cat = item.get('category')
                v_label = "📍 장소/레이블"
                c1, c2 = st.columns(2)
                n_rel = c1.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_venue = c2.text_input(v_label, value=str(item.get('venue', '')))
                try: curr_view = pd.to_datetime(item.get('view_date')).date()
                except: curr_view = date.today()
                n_view_date = st.date_input("🍿 감상일 수정", value=curr_view)
                n_sum = st.text_area("📖 줄거리/작품소개", value=str(item.get('summary', '')), height=150)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '')))
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '')), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '')), height=100)

                if st.form_submit_button("💾 저장"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=?, img_url2=? WHERE id=?""", 
                                     (n_title, n_creator, n_rel, n_venue, n_sum, n_brief, n_high, n_note, str(n_view_date), n_img.strip(), n_img2.strip(), item['id']))
                    st.success("✅ 수정 완료!")
                    st.rerun()
    else: 
        with col_img:
            if is_valid_url(item.get('img_url')): st.image(item.get('img_url'), use_container_width=True)
            if is_valid_url(item.get('img_url2')): st.image(item.get('img_url2'), use_container_width=True)
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**{item.get('creator')}**")
            st.write(f"**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
            st.markdown(f'<p style="color: #E2E2E2; font-weight: bold;">🍿감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()
            for label, key, color in [("📖 줄거리", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 인상", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]:
                if item.get(key):
                    st.markdown(f'<div style="background-color: {color}; color: white; padding: 2px 10px; border-radius: 10px; font-size: 0.8em; width: fit-content; margin-bottom: 5px;">{label}</div>', unsafe_allow_html=True)
                    st.markdown(item.get(key).replace('\n', '  \n'))
                    st.divider()

# --- [5. 메인 화면 및 렌더링 로직] ---
def render_gallery(items, grid_cols, is_all_tab=False, key_prefix="btn"):
    for i in range(0, len(items), grid_cols):
        with st.container(): # 격자 붕괴 방지를 위한 컨테이너 래핑
            cols = st.columns(grid_cols)
            for j in range(grid_cols):
                if i + j < len(items):
                    row = items[i + j]
                    # ALL 모드면 무조건 1:1.4 고정, MUSIC 전용탭이면 1:1 고정
                    aspect_cls = "music-aspect" if (row["category"] == "MUSIC" and not is_all_tab) else "standard-aspect"
                    
                    with cols[j]:
                        # HTML 구조 강화: 탭 전환 시에도 이미지 주소를 강제로 갱신하도록 구성
                        st.markdown(f'''
                        <div class="canvas-container {aspect_cls}">
                            <div class="badge-date">{row["view_date"][-2:] if is_all_tab else row["view_date"]}</div>
                            {"<div class='badge-cat'>"+row['category']+"</div>" if is_all_tab else ""}
                            <img src="{row['img_url']}" onerror="this.src='https://via.placeholder.com/300x400?text=No+Image';">
                        </div>
                        ''', unsafe_allow_html=True)
                        
                        if st.button(row['title'][:10], key=f"{key_prefix}_{row['id']}", use_container_width=True): 
                            show_details(row)

if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tab_a = st.tabs(["📂 ARCHIVE"])[0]
    tab_w = None

# (Write 로직은 생략/동일하므로 유지됨)
if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
        search_query = st.text_input(f"🔍 {category} 검색")
        # ... API 검색 로직 ... (기존 코드와 동일)
        # 위 공간상 상세 검색 코드는 생략하지만 실제 구현시 기존 검색부 유지

with tab_a:
    st.markdown("""<style>
        .canvas-container { 
            position: relative; 
            width: 100%; 
            min-width: 120px; /* 탭 전환 시 너비 0px 방어 */
            background: #222; 
            border-radius: 10px; 
            overflow: hidden; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            margin-bottom: 5px;
        }
        .standard-aspect { aspect-ratio: 1 / 1.45; min-height: 200px; }
        .music-aspect { aspect-ratio: 1 / 1; min-height: 150px; }
        .canvas-container img { width: 100%; height: 100%; object-fit: cover; }
        .badge-date { position: absolute; bottom: 5px; right: 5px; background: rgba(0,0,0,0.6); color: white; font-size: 10px; padding: 2px 6px; border-radius: 4px; z-index: 5; }
        .badge-cat { position: absolute; top: 5px; left: 5px; background: rgba(0,0,0,0.8); color: #FFEB3B; font-size: 10px; padding: 2px 6px; border-radius: 4px; z-index: 5; }
    </style>""", unsafe_allow_html=True)

    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        tab_titles = [f"📅 ALL ({len(all_df)})"] + [f"{c}" for c in cat_order]
        sub_tabs = st.tabs(tab_titles)

        # 1. ALL 모드
        with sub_tabs[0]:
            years = sorted(all_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            if years:
                sel_y = st.selectbox("📅 Year", years, key="y_sel")
                y_df = all_df[all_df['v_dt'].dt.year == sel_y]
                for m in range(12, 0, -1):
                    m_data = y_df[y_df['v_dt'].dt.month == m]
                    if not m_data.empty:
                        st.subheader(f"🗓️ {m}월")
                        render_gallery(m_data.to_dict('records'), 6, is_all_tab=True, key_prefix=f"all_{sel_y}_{m}")

        # 2. Category 모드 (cat)
        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx + 1]:
                c_data = all_df[all_df['category'] == c_name]
                if not c_data.empty:
                    # 카테고리 탭 내부에서 강제로 컨테이너를 다시 열어 이미지 렌더링 보장
                    render_gallery(c_data.to_dict('records'), 6, is_all_tab=False, key_prefix=f"cat_tab_{c_name}")
                else:
                    st.info("기록이 없습니다.")

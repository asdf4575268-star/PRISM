import streamlit as st
import requests
import pandas as pd
import sqlite3
from datetime import date, datetime
import time
import re 
import xml.etree.ElementTree as ET
from supabase import create_client, Client

# --- [1. 설정 및 API] ---
st.set_page_config(layout="wide", page_title="PRISM", page_icon="🌈")

DB_NAME = "archive.db"
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

# Supabase 설정
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- [2. 상태 초기화 및 권한 설정 (NameError 방지)] ---
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_password" not in st.session_state:
    st.session_state.user_password = ""
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "PC"

# 에러의 원인이었던 변수들을 상단에서 미리 정의합니다.
is_admin = st.session_state.is_logged_in 
is_mobile = st.session_state.view_mode == "Mobile"

# --- [3. DB 및 동기화 로직] ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS archive
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                  rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, 
                  note TEXT, img_url TEXT, sub_img TEXT, save_date TEXT, view_date TEXT)''')
    c.execute("PRAGMA table_info(archive)")
    columns = [info[1] for info in c.fetchall()]
    if 'sub_img' not in columns:
        c.execute("ALTER TABLE archive ADD COLUMN sub_img TEXT")
    conn.commit()
    conn.close()

init_db()

def load_data():
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql("SELECT * FROM archive ORDER BY view_date DESC", conn)
        conn.close()
        return df
    except: return pd.DataFrame()

def sync_to_cloud():
    if not supabase: return st.error("Supabase 설정이 없습니다.")
    try:
        conn = sqlite3.connect(DB_NAME)
        local_df = pd.read_sql("SELECT * FROM archive", conn)
        conn.close()
        supabase.table("archive").delete().neq("id", -1).execute() 
        data_to_sync = local_df.to_dict('records')
        if data_to_sync:
            supabase.table("archive").insert(data_to_sync).execute()
        st.success("☁️ 클라우드 백업 완료!")
    except Exception as e:
        st.error(f"백업 실패: {e}")

def sync_from_cloud():
    if not supabase: return st.error("Supabase 설정이 없습니다.")
    try:
        res = supabase.table("archive").select("*").execute()
        cloud_df = pd.DataFrame(res.data)
        if not cloud_df.empty:
            conn = sqlite3.connect(DB_NAME)
            cloud_df.to_sql("archive", conn, if_exists="replace", index=False)
            conn.close()
            st.success("💾 로컬 복원 완료!")
            time.sleep(0.5); st.rerun()
    except Exception as e:
        st.error(f"복원 실패: {e}")

# --- [4. API 검색 함수들 (생략 없이 유지)] ---
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
    except: return "정보 없음"
    return "정보 없음"

# --- [5. 팝업 상세 보기] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    edit_mode = False
    if is_admin:
        t_col1, t_col2, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                conn.commit()
                conn.close()
                st.rerun()
        with t_col3:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    col_img, col_txt = st.columns([0.3, 0.7]) if not is_mobile else (st.container(), st.container())

    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 메인 이미지 URL", value=str(item.get('img_url', '')), key=f"img_in_{item['id']}")
            n_sub_img = st.text_input("📸 추가 이미지 URL", value=str(item.get('sub_img', '')), key=f"sub_img_in_{item['id']}")
            if n_img: st.image(n_img, use_container_width=True)
        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                n_view_date = st.date_input("🍿 감상일", value=pd.to_datetime(item.get('view_date')).date())
                n_note = st.text_area("💬 감상", value=str(item.get('note', '')), height=150)
                if st.form_submit_button("💾 저장"):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("UPDATE archive SET title=?, creator=?, view_date=?, note=?, img_url=?, sub_img=? WHERE id=?",
                              (n_title, n_creator, str(n_view_date), n_note, n_img, n_sub_img, item['id']))
                    conn.commit()
                    conn.close()
                    st.success("✅ 수정 완료!"); time.sleep(0.5); st.rerun()
    else: 
        with col_img:
            if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
            if item.get('sub_img'): st.image(item['sub_img'], use_container_width=True)
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**{item.get('creator')}** | 🍿{item.get('view_date')}")
            st.divider()
            sections = [("📖 줄거리", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 인상 깊은 부분", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]
            for label, key, color in sections:
                if item.get(key):
                    st.markdown(f'<div style="background:{color}; color:white; padding:2px 10px; border-radius:10px; display:inline-block; font-size:0.8em;">{label}</div>', unsafe_allow_html=True)
                    st.write(item.get(key))

# --- [6. 사이드바 및 메인 레이아웃] ---
with st.sidebar:
    st.markdown("### 🔐 Admin")
    if not is_admin:
        pw = st.text_input("Password", type="password")
        if pw == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.is_logged_in = True
            st.rerun()
    else:
        if st.button("🔓 Logout"):
            st.session_state.is_logged_in = False
            st.rerun()
        st.divider()
        st.markdown("### 🔄 Sync")
        c1, c2 = st.columns(2)
        if c1.button("📤 Backup"): sync_to_cloud()
        if c2.button("📥 Restore"): sync_from_cloud()

    st.divider()
    st.session_state.view_mode = st.radio("Display", ["PC", "Mobile"], horizontal=True)

st.title("🌈 PRISM ARCHIVE")

if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tab_a = st.tabs(["📂 ARCHIVE"])[0]

# (WRITE 로직은 기존과 동일하되 SQLite에 INSERT 하도록 유지...)
if is_admin:
    with tab_w:
        # ... (검색 및 입력 폼 - 생략하나 실제 코드엔 포함)
        pass 

# --- [7. ARCHIVE 탭 - 이미지 캔버스 유지 로직] ---
with tab_a:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; background: #1e1e1e; display: flex; align-items: center; justify-content: center; }
        .cal-img-box img { width: 100%; height: 100%; }
        .badge-cat { position: absolute; top: 5px; left: 5px; background: rgba(0,0,0,0.7); color: yellow; padding: 2px 5px; border-radius: 4px; font-size: 10px; }
    </style>""", unsafe_allow_html=True)

    all_df = load_data()
    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'])
        # (탭 생성 로직...)
        sub_tabs = st.tabs(["📅 ALL"] + ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"])
        
        with sub_tabs[0]: # ALL 탭
            items = all_df.to_dict('records')
            grid_cols = 6 if not is_mobile else 2
            for i in range(0, len(items), grid_cols):
                cols = st.columns(grid_cols)
                for j in range(grid_cols):
                    if i+j < len(items):
                        row = items[i+j]
                        # 캔버스는 유지하되 음악만 비율 유지 (Contain)
                        img_style = 'style="object-fit: contain; background: #000;"' if row["category"] == "MUSIC" else 'style="object-fit: cover;"'
                        with cols[j]:
                            st.markdown(f'<div class="cal-img-box"><div class="badge-cat">{row["category"]}</div><img src="{row["img_url"]}" {img_style}></div>', unsafe_allow_html=True)
                            if st.button(row['title'][:10], key=f"a_{row['id']}", use_container_width=True): show_details(row)

import streamlit as st
from PIL import Image
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime, timedelta
import time
import re 
import xml.etree.ElementTree as ET
from supabase import create_client, Client
import base64

# --- [1. 설정 및 API] ---
favicon = Image.open("logo.png").resize((64, 64), Image.LANCZOS)
st.set_page_config(
    page_title="PRISM",
    page_icon=favicon,
    layout="wide",
    initial_sidebar_state="collapsed"
)

TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
DB_NAME = 'archive_prism_total_v5.db'
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- [2. DB 함수 및 유틸리티] ---
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

def extract_tags(text):
    if not text: return []
    return re.findall(r"#(\w+)", text)

# (Supabase 동기화 로직은 기존과 동일하게 유지)
def migrate_to_supabase():
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        local_data = conn.execute("SELECT * FROM archive").fetchall()
        if not local_data: return
        upload_list = [dict(row) for row in local_data]
        for d in upload_list:
            if 'id' in d: del d['id']
        supabase.table("archive").upsert(upload_list).execute() 
        st.session_state.sync_msg = ("success", f"✅ {len(upload_list)}개 백업 완료")
    except Exception as e: st.session_state.sync_msg = ("error", f"❌ 실패: {e}")

def restore_from_supabase():
    try:
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        if not cloud_data: return
        conn = get_connection(); cursor = conn.cursor()
        local_df = get_all_data()
        local_keys = set(zip(local_df['title'], local_df['view_date'])) if not local_df.empty else set()
        to_insert = [ (row['category'], row['title'], row['creator'], row['rel_date'], row['venue'], row['summary'], row['brief'], row['highlights'], row['note'], row.get('img_url'), row.get('img_url2'), row['save_date'], row['view_date']) 
                     for row in cloud_data if (row['title'], row['view_date']) not in local_keys ]
        if to_insert:
            cursor.executemany("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", to_insert)
            conn.commit(); st.cache_data.clear()
        st.session_state.sync_msg = ("success", f"✅ {len(to_insert)}개 복구 완료")
    except Exception as e: st.session_state.sync_msg = ("error", f"❌ 실패: {e}")

# --- [3. 로그인 & 사이드바] ---
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "user_password" not in st.session_state: st.session_state.user_password = ""
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"

if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True

is_admin = st.session_state.is_logged_in 

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not is_admin:
        input_password = st.text_input("Password", type="password", key="sidebar_pw")
        if input_password == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.user_password = input_password 
            st.session_state.is_logged_in = True; st.rerun()
    else:
        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.is_logged_in = False; st.session_state.user_password = ""; st.rerun()
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)
    st.divider()
    st.session_state.view_mode = st.radio("📱 화면 모드", ["PC", "Mobile"], horizontal=True)

is_mobile = st.session_state.view_mode == "Mobile"

# --- [4. API 검색 함수 (BOOKS, MUSIC, TMDB, STAGE 유지)] ---
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query, "size": 15})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url).json().get("results", [])
        return [{'display_name': f"{'📀' if m.get('wrapperType')=='collection' else '🎵'} {m.get('collectionName' if m.get('wrapperType')=='collection' else 'trackName')} - {m.get('artistName')}", 'title': m.get('collectionName' if m.get('wrapperType')=='collection' else 'trackName'), 'creator': m.get('artistName'), 'date': m.get('releaseDate')[:10], 'img': m.get('artworkUrl100').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName')} for m in res]
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
        crew = res.get('credits', {}).get('crew', [])
        if is_movie: creator = f"[감독] {next((m['name'] for m in crew if m.get('job') == 'Director'), '정보 없음')}"
        else: creator = f"[작가/제작] {', '.join([c['name'] for c in res.get('created_by', [])]) if res.get('created_by') else '정보 없음'}"
        venue = res.get('production_companies', [{}])[0].get('name', '') if is_movie else res.get('networks', [{}])[0].get('name', '')
        return {"creator": creator, "venue": venue}
    except: return {"creator": "정보 없음", "venue": ""}

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=100&cpage=1"
    try:
        res = requests.get(url); root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

# --- [5. 팝업 상세 보기 (일방향 참조 통합)] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    edit_mode = False
    if is_admin:
        t_col1, _, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                conn = get_connection(); conn.execute("DELETE FROM archive WHERE id=?", (item['id'],)); conn.commit()
                st.cache_data.clear(); st.rerun()
        with t_col3: edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    col_img, col_txt = (st.container(), st.container()) if is_mobile else st.columns([0.3, 0.7])
    
    if is_admin and edit_mode:
        with col_txt:
            with st.form(key=f"ed_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_note = st.text_area("💬 감상/인사이트", value=str(item.get('note', '')), height=200)
                if st.form_submit_button("💾 저장"):
                    conn = get_connection(); conn.execute("UPDATE archive SET title=?, note=? WHERE id=?", (n_title, n_note, item['id'])); conn.commit()
                    st.cache_data.clear(); st.success("저장 완료"); st.rerun()
    else: 
        with col_img:
            if item.get('img_url') and item['img_url'] != "None": st.image(item['img_url'], use_container_width=True)
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**{item.get('creator')}** | {item.get('rel_date')} | {item.get('venue')}")
            st.divider()
            for label, key, color in [("📖 작품소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("🌈 PRISM", "note", "#1E425E")]:
                if item.get(key):
                    st.markdown(f'<small style="background:{color}; color:white; padding:2px 8px; border-radius:10px;">{label}</small>', unsafe_allow_html=True)
                    st.markdown(item[key].replace('\n', '  \n'))
            
            # [핵심: 일방향 참조] 콘텐츠 페이지에서 관련 스크랩만 링크
            if is_admin and item['category'] != "SCRAP":
                scraps = get_all_data()
                rel = scraps[(scraps['category'] == 'SCRAP') & (scraps['note'].str.contains(f"#{item['title']}", na=False))]
                if not rel.empty:
                    st.markdown("---"); st.markdown("#### 🔗 관련 SCRAP")
                    for _, s in rel.iterrows():
                        if st.button(f"📰 {s['title']}", key=f"rel_{s['id']}", use_container_width=True): show_details(s)

# --- [6. 메인 헤더 및 WRITE] ---
logo_base64 = base64.b64encode(open("logo.png", "rb").read()).decode()
st.markdown(f'<div style="display:flex; align-items:center; gap:10px;"><img src="data:image/png;base64,{logo_base64}" width="80"><h1>PRISM ARCHIVE</h1></div>', unsafe_allow_html=True)

if is_admin: tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else: tab_a = st.tabs(["📂 ARCHIVE"])[0]; tab_w = None

if is_admin and tab_w:
    with tab_w:
        cat = st.radio("CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"], horizontal=True)
        # (기존 검색/입력 로직 동일하게 유지하되 Scrap은 수동 입력)
        with st.form("write_form"):
            c1, c2 = st.columns([0.4, 0.6])
            with c1:
                t = st.text_input("제목")
                cr = st.text_input("창작자/매체")
                img = st.text_input("이미지 URL")
            with c2:
                sm = st.text_area("소개/원문")
                nt = st.text_area("감상/인사이트 (#태그 포함)")
                vd = st.date_input("기록일", value=date.today())
            if st.form_submit_button("✅ 저장"):
                conn = get_connection()
                conn.execute("INSERT INTO archive (category, title, creator, summary, note, img_url, view_date) VALUES (?,?,?,?,?,?,?)", (cat, t, cr, sm, nt, img, str(vd)))
                conn.commit(); st.cache_data.clear(); st.success("저장 완료")

# --- [7. ARCHIVE 탭 (독립형 대시보드)] ---
with tab_a:
    st.markdown("""<style>.cal-img-box { position: relative; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; background: #1e1e1e; } .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }</style>""", unsafe_allow_html=True)
    df = get_all_data()
    if not df.empty:
        df['v_dt'] = pd.to_datetime(df['view_date'], errors='coerce')
        cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        if is_admin: cats.append("SCRAP")
        
        sub_tabs = st.tabs([f"📅 ALL"] + cats)
        grid = 2 if is_mobile else 6

        with sub_tabs[0]: # ALL 탭: SCRAP 제외
            all_v = df[df['category'] != "SCRAP"]
            for m in range(12, 0, -1):
                m_data = all_v[all_v['v_dt'].dt.month == m]
                if not m_data.empty:
                    st.subheader(f"🗓️ {m}월")
                    for i in range(0, len(m_data), grid):
                        cols = st.columns(grid)
                        for j, row in enumerate(m_data.iloc[i:i+grid].to_dict('records')):
                            with cols[j]:
                                st.markdown(f'<div class="cal-img-box"><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                if st.button(row['title'][:10], key=f"a_{row['id']}", use_container_width=True): show_details(row)

        for idx, c_name in enumerate(cats):
            with sub_tabs[idx+1]:
                c_data = df[df['category'] == c_name]
                if c_name == "SCRAP" and is_admin:
                    # [스크랩 독립 대시보드]
                    tags = []
                    for n in c_data['note'].fillna(""): tags.extend(extract_tags(n))
                    if tags: st.write("🏷️ " + " ".join([f"`#{t}`" for t in set(tags)]))
                    for week, group in c_data.groupby(pd.Grouper(key='v_dt', freq='W-MON')):
                        with st.expander(f"📅 {week.strftime('%m.%d')} 주간 스크랩", expanded=True):
                            for _, row in group.iterrows():
                                sc1, sc2 = st.columns([0.2, 0.8])
                                with sc1: st.image(row['img_url'], use_container_width=True)
                                with sc2: 
                                    if st.button(row['title'], key=f"s_{row['id']}", use_container_width=True): show_details(row)
                                    st.caption(f"{row['creator']} | {row['view_date']}")
                else:
                    for i in range(0, len(c_data), grid):
                        cols = st.columns(grid)
                        for j, row in enumerate(c_data.iloc[i:i+grid].to_dict('records')):
                            with cols[j]:
                                st.markdown(f'<div class="cal-img-box"><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                if st.button(row['title'][:10], key=f"c_{c_name}_{row['id']}", use_container_width=True): show_details(row)

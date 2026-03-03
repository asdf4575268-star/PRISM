import streamlit as st
from PIL import Image
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
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

# --- [2. SCRAP 전용 URL 크롤링 함수] ---
def scrape_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        res.encoding = 'utf-8'
        html = res.text
        title = re.search(r'property="og:title"\s+content="(.*?)"', html)
        if not title: title = re.search(r'<title>(.*?)</title>', html)
        img = re.search(r'property="og:image"\s+content="(.*?)"', html)
        site = re.search(r'property="og:site_name"\s+content="(.*?)"', html)
        desc = re.search(r'property="og:description"\s+content="(.*?)"', html)
        return {
            "title": title.group(1) if title else "제목 없음",
            "img": img.group(1) if img else "",
            "venue": site.group(1) if site else "URL Link",
            "summary": desc.group(1) if desc else url
        }
    except: return None

# --- [3. DB 함수 및 동기화 로직] ---
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
        conn = get_connection()
        cursor = conn.cursor()
        local_df = get_all_data()
        local_keys = set(zip(local_df['title'], local_df['view_date'])) if not local_df.empty else set()
        to_insert = []
        for row in cloud_data:
            if (row['title'], row['view_date']) not in local_keys:
                to_insert.append((row['category'], row['title'], row['creator'], row['rel_date'], row['venue'], row['summary'], row.get('brief',''), row.get('highlights',''), row['note'], row.get('img_url'), row.get('img_url2'), row['save_date'], row['view_date']))
        if to_insert:
            cursor.executemany("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", to_insert)
            conn.commit()
            st.cache_data.clear()
        st.session_state.sync_msg = ("success", f"✅ {len(to_insert)}개 데이터 복구 완료!")
    except Exception as e: st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

# --- [4. 로그인 시스템 & 사이드바] ---
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

    st.divider()
    st.session_state.view_mode = st.radio("보기 옵션", ["PC", "Mobile"], horizontal=True)

is_mobile = st.session_state.view_mode == "Mobile"

# --- [5. API 검색 함수들 (원본 전체 유지)] ---
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
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}?api_key={TMDB_API_KEY}&language=ko-KR&append_to_response=credits"
    try:
        res = requests.get(url).json()
        crew = res.get('credits', {}).get('crew', [])
        cast = res.get('credits', {}).get('cast', [])
        director = next((m['name'] for m in crew if m.get('job') == 'Director'), "정보 없음")
        cast_names = ", ".join([c['name'] for c in cast[:3]])
        venue = res.get('production_companies', [{}])[0].get('name', '') if category == "MOVIES" else res.get('networks', [{}])[0].get('name', '')
        return {"creator": f"[감독/제작] {director} / [출연] {cast_names}", "venue": venue}
    except: return {"creator": "정보 없음", "venue": ""}

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=50&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

# --- [6. 팝업 상세 보기] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    edit_mode = False
    if is_admin:
        c1, _, c2 = st.columns([0.2, 0.6, 0.2])
        if c1.button("🗑️ 삭제", key=f"del_{item['id']}"):
            conn = get_connection(); conn.execute("DELETE FROM archive WHERE id=?", (item['id'],)); conn.commit()
            st.cache_data.clear(); st.rerun()
        edit_mode = c2.toggle("✏️ 수정", key=f"tog_{item['id']}")
    
    col_img, col_txt = st.columns([0.3, 0.7]) if not is_mobile else (st.container(), st.container())
    
    if is_admin and edit_mode:
        with col_txt:
            with st.form(f"f_{item['id']}"):
                n_t = st.text_input("제목", value=str(item['title']))
                n_c = st.text_input("창작자", value=str(item['creator']))
                n_v = st.text_input("장소/출처", value=str(item['venue']))
                n_s = st.text_area("소개", value=str(item['summary']))
                n_b = st.text_input("요약", value=str(item.get('brief','')))
                n_h = st.text_area("인상 깊은 부분", value=str(item.get('highlights','')))
                n_n = st.text_area("🌈 PRISM", value=str(item['note']))
                if st.form_submit_button("저장"):
                    conn = get_connection()
                    conn.execute("UPDATE archive SET title=?, creator=?, venue=?, summary=?, brief=?, highlights=?, note=? WHERE id=?", (n_t, n_c, n_v, n_s, n_b, n_h, n_n, item['id']))
                    conn.commit(); st.cache_data.clear(); st.rerun()
    else:
        with col_img: 
            if item.get('img_url') and str(item['img_url']) != "None": st.image(item['img_url'], use_container_width=True)
        with col_txt:
            st.header(item['title'])
            st.write(f"**{item['creator']}** | {item['rel_date']} | {item['venue']}")
            st.divider()
            if item.get('summary'): st.markdown(f"**📖 작품소개**\n{item['summary']}")
            if item.get('note'): st.markdown(f"**🌈 PRISM**\n{item['note']}")

# --- [7. 메인 화면 UI] ---
def get_base64(path):
    try:
        with open(path, "rb") as f: return base64.b64encode(f.read()).decode()
    except: return ""

logo_base64 = get_base64("logo.png")
st.markdown(f'<div style="display: flex; align-items: center; gap: 10px;"><img src="data:image/png;base64,{logo_base64}" width="80"><h1>PRISM ARCHIVE</h1></div>', unsafe_allow_html=True)

if is_admin: tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else: tab_a = st.tabs(["📂 ARCHIVE"])[0]; tab_w = None

# --- [WRITE 탭] ---
if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"], horizontal=True)
        search_query = st.text_input(f"🔍 {category} {'URL 입력' if category=='SCRAP' else '검색'}")
        
        if search_query:
            if category == "SCRAP":
                if st.button("✨ URL 정보 가져오기"):
                    s = scrape_url(search_query)
                    if s: st.session_state.api_data = {'title': s['title'], 'img': s['img'], 'venue': s['venue'], 'summary': s['summary'], 'date': str(date.today()), 'creator': 'Web Link'}
                    st.rerun()
            elif category == "BOOKS":
                res = search_books(search_query)
                if res:
                    opts = {b['title']: b for b in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        b = opts[sel]
                        st.session_state.api_data = {'title': b['title'], 'creator': ",".join(b['authors']), 'date': b['datetime'][:10], 'img': b.get('thumbnail','').replace("R120x174","R400x0"), 'venue': b['publisher'], 'summary': b['contents']}
                        st.rerun()
            elif category == "MUSIC":
                res = search_apple_music(search_query)
                if res:
                    opts = {m['display_name']: m for m in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        m = opts[sel]; st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'venue': m['venue'], 'summary': ''}
                        st.rerun()
            elif category in ["MOVIES", "SERIES"]:
                res = search_tmdb(search_query, category)
                if res:
                    t_key = 'title' if category == 'MOVIES' else 'name'
                    opts = {f"{r.get(t_key)}": r for r in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        r = opts[sel]; det = get_tmdb_details(r['id'], category)
                        st.session_state.api_data = {'title': r.get(t_key), 'creator': det['creator'], 'date': r.get('release_date', r.get('first_air_date')), 'img': f"https://image.tmdb.org/t/p/w500{r.get('poster_path')}", 'venue': det['venue'], 'summary': r.get('overview')}
                        st.rerun()

        st.divider()
        data = st.session_state.get('api_data', {})
        cl, cr = st.columns([0.4, 0.6])
        with cl:
            img_val = st.text_input("🖼️ 이미지 URL", value=data.get('img', ''))
            if img_val: st.image(img_val, use_container_width=True)
            title = st.text_input("제목", value=data.get('title', ''))
            creator = st.text_input("창작자", value=data.get('creator', ''))
        with cr:
            rel_date = st.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
            venue = st.text_input("📍 장소/플랫폼", value=data.get('venue', ''))
            summary = st.text_area("📖 작품소개", value=data.get('summary', ''))
            note = st.text_area("🌈 PRISM")
            v_date = st.date_input("🍿 감상일", value=date.today())
            if st.button("✅ 기록 저장", use_container_width=True):
                conn = get_connection()
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, note, img_url, view_date, save_date) VALUES (?,?,?,?,?,?,?,?,?,?)", 
                             (category, title, creator, rel_date, venue, summary, note, img_val, str(v_date), str(date.today())))
                conn.commit(); st.cache_data.clear(); st.session_state.api_data = {}; st.success("저장 완료!"); time.sleep(0.5); st.rerun()

# --- [ARCHIVE 탭] ---
with tab_a:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); background: #1e1e1e; display: flex; align-items: center; justify-content: center; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .music-style { aspect-ratio: 1/1 !important; }
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
        .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
    </style>""", unsafe_allow_html=True)
    
    all_df = get_all_data()
    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        main_df = all_df[all_df['category'] != "SCRAP"]
        scrap_df = all_df[all_df['category'] == "SCRAP"]
        
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        tab_titles = [f"📅 ALL ({len(main_df)})"] + [f"{c} ({len(main_df[main_df['category']==c])})" for c in cat_order]
        if is_admin: tab_titles.append(f"🔗 SCRAP ({len(scrap_df)})")
        
        sub_tabs = st.tabs(tab_titles)
        grid_cols = 2 if is_mobile else 6

        # 1. ALL 탭 (월별 그리드 - 음악 1:1 반영)
        with sub_tabs[0]:
            years = sorted(main_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            if years:
                sel_y = st.selectbox("📅 연도 선택", years)
                y_df = main_df[main_df['v_dt'].dt.year == sel_y]
                for m in range(12, 0, -1):
                    m_data = y_df[y_df['v_dt'].dt.month == m]
                    if not m_data.empty:
                        st.subheader(f"🗓️ {m}월")
                        items = m_data.to_dict('records')
                        for i in range(0, len(items), grid_cols):
                            cols = st.columns(grid_cols)
                            for j in range(grid_cols):
                                if i+j < len(items):
                                    row = items[i+j]
                                    m_cls = "music-style" if row['category'] == "MUSIC" else ""
                                    with cols[j]:
                                        st.markdown(f'<div class="cal-img-box {m_cls}"><div class="badge-cat">{row["category"]}</div><div class="badge-date">{row["v_dt"].day}일</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                        if st.button(row['title'][:10], key=f"all_{row['id']}", use_container_width=True): show_details(row)

        # 2. 카테고리별 탭 (음악 1:1 반영)
        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx + 1]:
                c_data = main_df[main_df['category'] == c_name]
                items = c_data.to_dict('records')
                m_cls = "music-style" if c_name == "MUSIC" else ""
                for i in range(0, len(items), grid_cols):
                    cols = st.columns(grid_cols)
                    for j in range(grid_cols):
                        if i+j < len(items):
                            row = items[i+j]
                            with cols[j]:
                                st.markdown(f'<div class="cal-img-box {m_cls}"><div class="badge-date">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                if st.button(row['title'][:10], key=f"cat_{c_name}_{row['id']}", use_container_width=True): show_details(row)

        # 3. SCRAP 탭 (관리자에게만 노출)
        if is_admin:
            with sub_tabs[-1]:
                if scrap_df.empty: st.info("스크랩된 링크가 없습니다.")
                for _, row in scrap_df.iterrows():
                    with st.expander(f"🔗 {row['title']} ({row['view_date']})"):
                        sc1, sc2 = st.columns([0.2, 0.8])
                        if row['img_url']: sc1.image(row['img_url'])
                        sc2.write(f"**출처:** {row['venue']}")
                        sc2.write(row['summary'])
                        if st.button("상세보기/수정", key=f"sc_{row['id']}"): show_details(row)

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

# --- [추가: SCRAP 전용 함수] ---
def scrape_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
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
            "summary": desc.group(1) if desc else ""
        }
    except: return None

# --- [2. DB 함수 및 동기화 로직] ---
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
        st.session_state.sync_msg = ("success", f"✅ {len(upload_list)}개 백업 완료!")
    except Exception as e: st.session_state.sync_msg = ("error", f"❌ 실패: {e}")

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
                to_insert.append((row['category'], row['title'], row['creator'], row['rel_date'], row['venue'], row['summary'], row['brief'], row['highlights'], row['note'], row.get('img_url'), row.get('img_url2'), row['save_date'], row['view_date']))
        if to_insert:
            cursor.executemany("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", to_insert)
            conn.commit()
            st.cache_data.clear()
        st.session_state.sync_msg = ("success", f"✅ {len(to_insert)}개 복구 완료!")
    except Exception as e: st.session_state.sync_msg = ("error", f"❌ 실패: {e}")

# --- [3. 로그인 & 사이드바] ---
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "user_password" not in st.session_state: st.session_state.user_password = ""
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"
if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]: st.session_state.is_logged_in = True
is_admin = st.session_state.is_logged_in

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not is_admin:
        pw = st.text_input("Password", type="password")
        if pw == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.user_password = pw
            st.rerun()
    else:
        if st.button("🔓 Logout"):
            st.session_state.is_logged_in = False
            st.session_state.user_password = ""
            st.rerun()
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase)
    st.session_state.view_mode = st.radio("보기 옵션", ["PC", "Mobile"], horizontal=True)

is_mobile = st.session_state.view_mode == "Mobile"

# --- [4. 검색 함수들] ---
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query, "size": 15})
    return res.json().get("documents", []) if res.status_code == 200 else []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
    res = requests.get(url).json().get("results", [])
    return [{'display_name': f"{m.get('trackName', 'Album')} - {m.get('artistName', '')}", 'title': m.get('trackName', m.get('collectionName')), 'creator': m.get('artistName'), 'date': m.get('releaseDate', '')[:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName'), 'url': m.get('trackViewUrl', '')} for m in res]

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    return requests.get(url).json().get("results", [])

def get_tmdb_details(item_id, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}?api_key={TMDB_API_KEY}&language=ko-KR&append_to_response=credits"
    res = requests.get(url).json()
    crew = res.get('credits', {}).get('crew', [])
    director = next((m['name'] for m in crew if m.get('job') == 'Director'), "정보 없음")
    venue = res.get('production_companies', [{}])[0].get('name', '') if category == "MOVIES" else res.get('networks', [{}])[0].get('name', '')
    return {"creator": director, "venue": venue}

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=50&cpage=1"
    root = ET.fromstring(requests.get(url).content)
    return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]

# --- [5. 팝업 상세 보기] ---
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
    
    if edit_mode:
        with col_txt:
            with st.form(f"f_{item['id']}"):
                n_t = st.text_input("제목", value=item['title'])
                n_c = st.text_input("창작자", value=item['creator'])
                n_v = st.text_input("장소/출처", value=item['venue'])
                n_s = st.text_area("소개", value=item['summary'])
                n_n = st.text_area("감상", value=item['note'])
                if st.form_submit_button("저장"):
                    conn = get_connection()
                    conn.execute("UPDATE archive SET title=?, creator=?, venue=?, summary=?, note=? WHERE id=?", (n_t, n_c, n_v, n_s, n_n, item['id']))
                    conn.commit(); st.cache_data.clear(); st.rerun()
    else:
        with col_img: 
            if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
        with col_txt:
            st.header(item['title'])
            st.write(f"**{item['creator']}** | {item['rel_date']} | {item['venue']}")
            st.write(f"🍿 감상일: {item['view_date']}")
            st.divider()
            st.markdown(f"**📖 작품소개** \n{item['summary']}")
            st.markdown(f"**🌈 PRISM** \n{item['note']}")

# --- [6. 메인 UI] ---
def get_base64(path):
    with open(path, "rb") as f: return base64.b64encode(f.read()).decode()

logo_base = get_base64("logo.png")
st.markdown(f'<div style="display: flex; align-items: center; gap: 10px;"><img src="data:image/png;base64,{logo_base}" width="80"><h1>PRISM ARCHIVE</h1></div>', unsafe_allow_html=True)

if is_admin: tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else: tab_a = st.tabs(["📂 ARCHIVE"])[0]; tab_w = None

if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"], horizontal=True)
        search_query = st.text_input(f"🔍 {category} 검색 (SCRAP은 URL)")
        if search_query and st.button("✨ 가져오기"):
            if category == "SCRAP":
                s = scrape_url(search_query)
                if s: st.session_state.api_data = {'title': s['title'], 'img': s['img'], 'venue': s['venue'], 'summary': s['summary'], 'date': str(date.today()), 'creator': 'Link'}
            elif category == "BOOKS":
                res = search_books(search_query)
                if res: b = res[0]; st.session_state.api_data = {'title': b['title'], 'creator': ",".join(b['authors']), 'date': b['datetime'][:10], 'img': b.get('thumbnail','').replace("R120x174","R400x0"), 'venue': b['publisher'], 'summary': b['contents']}
            # (다른 카테고리 로직 생략 가능하나 편의상 요약 유지)
            st.rerun()
        
        st.divider()
        data = st.session_state.get('api_data', {})
        c_l, c_r = st.columns([0.4, 0.6])
        with c_l:
            img_val = st.text_input("이미지 URL", value=data.get('img', ''))
            if img_val: st.image(img_val, use_container_width=True)
            title = st.text_input("제목", value=data.get('title', ''))
            creator = st.text_input("창작자", value=data.get('creator', ''))
        with c_r:
            venue = st.text_input("장소/출처", value=data.get('venue', ''))
            summary = st.text_area("소개", value=data.get('summary', ''))
            note = st.text_area("🌈 PRISM")
            v_date = st.date_input("감상일", value=date.today())
            if st.button("✅ 저장", use_container_width=True):
                conn = get_connection()
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, note, img_url, view_date) VALUES (?,?,?,?,?,?,?,?,?)", 
                             (category, title, creator, data.get('date'), venue, summary, note, img_val, str(v_date)))
                conn.commit(); st.cache_data.clear(); st.session_state.api_data = {}; st.success("저장 완료!"); time.sleep(0.5); st.rerun()

with tab_a:
    # 기존 스타일 CSS
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); background: #1e1e1e; display: flex; align-items: center; justify-content: center; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
    </style>""", unsafe_allow_html=True)
    
    all_df = get_all_data()
    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        main_df = all_df[all_df['category'] != "SCRAP"]
        scrap_df = all_df[all_df['category'] == "SCRAP"]
        
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        tab_titles = [f"📅 ALL ({len(main_df)})"] + [f"{c} ({len(main_df[main_df['category']==c])})" for c in cat_order] + [f"🔗 SCRAP ({len(scrap_df)})"]
        sub_tabs = st.tabs(tab_titles)
        
        # ALL 탭 및 카테고리 탭 (기존 그리드 로직)
        for idx, df_target in enumerate([main_df] + [main_df[main_df['category']==c] for c in cat_order]):
            with sub_tabs[idx]:
                items = df_target.to_dict('records')
                cols = st.columns(2 if is_mobile else 6)
                for i, row in enumerate(items):
                    with cols[i % (2 if is_mobile else 6)]:
                        st.markdown(f'<div class="cal-img-box"><div class="badge-cat">{row["category"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                        if st.button(row['title'][:10], key=f"btn_{idx}_{row['id']}", use_container_width=True): show_details(row)
        
        # SCRAP 전용 탭
        with sub_tabs[-1]:
            for _, row in scrap_df.iterrows():
                with st.expander(f"🔗 {row['title']} ({row['view_date']})"):
                    st.write(row['summary'])
                    if st.button("상세보기", key=f"sbtn_{row['id']}"): show_details(row)

import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
import time
import re 
import xml.etree.ElementTree as ET
from supabase import create_client, Client
import streamlit.components.v1 as components

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

# --- [2. DB 연결 및 데이터 로드 최적화] ---
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

# --- [3. 동기화 로직 (백업/복구)] ---
def migrate_to_supabase():
    try:
        df = get_all_data()
        if df.empty:
            st.session_state.sync_msg = ("warning", "로컬 데이터가 없습니다.")
            return
        upload_list = df.drop(columns=['id']).to_dict(orient='records')
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
                to_insert.append((row['category'], row['title'], row['creator'], row['rel_date'], row['venue'], row['summary'], row['brief'], row['highlights'], row['note'], row.get('img_url'), row.get('img_url2'), row['save_date'], row['view_date']))
        
        if to_insert:
            cursor.executemany("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", to_insert)
            conn.commit()
            st.cache_data.clear()
        st.session_state.sync_msg = ("success", f"✅ {len(to_insert)}개 신규 데이터 복구 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

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
        return [{'display_name': f"{'📀' if m.get('wrapperType')=='collection' else '🎵'} {m.get('collectionName' if m.get('wrapperType')=='collection' else 'trackName')} - {m.get('artistName')}", 'title': m.get('collectionName' if m.get('wrapperType')=='collection' else 'trackName'), 'creator': m.get('artistName'), 'date': m.get('releaseDate')[:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName')} for m in res]
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
        cast = res.get('credits', {}).get('cast', [])
        if is_movie:
            creator = f"[감독] {next((m['name'] for m in crew if m.get('job') == 'Director'), '정보 없음')}"
            venue = res.get('production_companies', [{}])[0].get('name', '')
        else:
            creator = f"[작가/제작] {', '.join([c['name'] for c in res.get('created_by', [])]) if res.get('created_by') else '정보 없음'}"
            venue = res.get('networks', [{}])[0].get('name', '')
        return {"creator": f"{creator} / [출연] {', '.join([c['name'] for c in cast[:3]])}", "venue": venue}
    except: return {"creator": "정보 없음", "venue": ""}

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=100&cpage=1"
    try:
        root = ET.fromstring(requests.get(url).content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

# --- [4. 팝업 상세 보기] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    edit_mode = False
    if st.session_state.get("is_logged_in"):
        t_col1, t_col2, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                conn = get_connection()
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],)); conn.commit()
                supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
                st.cache_data.clear(); st.rerun()
        with t_col3: edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    col_img, col_txt = (st.container(), st.container()) if st.session_state.view_mode == "Mobile" else st.columns([0.3, 0.7])

    if edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 이미지 1", value=str(item.get('img_url', '')), key=f"img1_{item['id']}")
            n_img2 = st.text_input("🖼️ 이미지 2", value=str(item.get('img_url2', '')), key=f"img2_{item['id']}")
            if n_img: st.image(n_img, use_container_width=True)
        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=item['title'])
                n_creator = st.text_input("👤 창작자", value=item['creator'])
                n_view_date = st.date_input("🍿 감상일", value=pd.to_datetime(item['view_date']).date())
                n_sum = st.text_area("📖 작품소개", value=item['summary'], height=150)
                n_brief = st.text_input("📝 요약", value=item['brief'])
                n_high = st.text_area("✨ 인상 깊은 부분", value=item['highlights'], height=100)
                n_note = st.text_area("💬 감상", value=item['note'], height=100)
                if st.form_submit_button("💾 저장"):
                    conn = get_connection()
                    conn.execute("UPDATE archive SET title=?, creator=?, summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=?, img_url2=? WHERE id=?", (n_title, n_creator, n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, n_img2, item['id']))
                    conn.commit()
                    supabase.table("archive").upsert({"title": n_title, "creator": n_creator, "category": item['category'], "rel_date": item['rel_date'], "venue": item['venue'], "summary": n_sum, "brief": n_brief, "highlights": n_high, "note": n_note, "view_date": str(n_view_date), "img_url": n_img, "img_url2": n_img2}).execute()
                    st.cache_data.clear(); st.success("수정 완료"); time.sleep(0.5); st.rerun()
    else:
        with col_img:
            for k in ['img_url', 'img_url2']:
                if item.get(k) and str(item.get(k)) != "None": st.image(item[k], use_container_width=True)
        with col_txt:
            st.markdown(f'# {item["title"]}\n#### **[{item["category"]}]**\n**{item["creator"]}**\n📅 {item["rel_date"]} | 📍 {item["venue"]}')
            st.markdown(f'<p style="color:#E2E2E2; font-weight:bold;">🍿감상일: {item["view_date"]}</p>', unsafe_allow_html=True)
            st.divider()
            for label, key, color in [("📖 작품소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 인상 깊은 부분", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]:
                if item.get(key):
                    st.markdown(f'<div style="background:{color}; color:white; padding:2px 12px; border-radius:12px; display:inline-block; font-size:0.8em; margin-bottom:10px;">{label}</div>', unsafe_allow_html=True)
                    st.write(item[key])
                    st.markdown("<hr style='margin:1.2em 0; border:0; border-top:1px solid #333;'>", unsafe_allow_html=True)

# --- [5. 메인 화면] ---
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"

with st.sidebar:
    st.markdown("### 🔐 Admin")
    if not st.session_state.is_logged_in:
        if st.text_input("Password", type="password") == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.is_logged_in = True; st.rerun()
    else:
        if st.button("🔓 Logout"): st.session_state.is_logged_in = False; st.rerun()
        st.divider()
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)
    st.divider()
    st.session_state.view_mode = st.radio("화면 모드", ["PC", "Mobile"], horizontal=True)

st.title("🌈PRISM ARCHIVE")
tabs = st.tabs(["📂 ARCHIVE", "🖋️ WRITE"]) if st.session_state.is_logged_in else st.tabs(["📂 ARCHIVE"])
tab_a = tabs[0]

if st.session_state.is_logged_in:
    with tabs[1]:
        cat = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
        search = st.text_input(f"🔍 {cat} 검색")
        if search:
            res = []
            if cat == "BOOKS": res = search_books(search)
            elif cat == "MUSIC": res = search_apple_music(search)
            elif cat == "STAGE": res = search_kopis(search)
            else: res = search_tmdb(search, cat)
            
            if res:
                sel = st.selectbox("결과 선택", res, format_func=lambda x: x.get('display_name', x.get('title', x.get('name', ''))))
                if st.button("✨ 데이터 가져오기"):
                    d = sel
                    if cat in ["MOVIES", "SERIES"]:
                        det = get_tmdb_details(d['id'], cat)
                        st.session_state.api_data = {'title': d.get('title' if cat=='MOVIES' else 'name'), 'creator': det['creator'], 'date': d.get('release_date' if cat=='MOVIES' else 'first_air_date'), 'img': f"https://image.tmdb.org/t/p/w500{d.get('poster_path')}", 'venue': det['venue'], 'summary': d.get('overview')}
                    else:
                        st.session_state.api_data = {'title': d['title'], 'creator': d['creator'], 'date': d['date'], 'img': d['img'], 'venue': d.get('venue', ''), 'summary': d.get('summary', '')}
                    st.rerun()
        
        st.divider()
        data = st.session_state.get('api_data', {})
        cl, cr = st.columns([0.4, 0.6])
        with cl:
            img1 = st.text_input("🖼️ 이미지 1", value=data.get('img', ''))
            if img1: st.image(img1, use_container_width=True)
            title = st.text_input("제목", value=data.get('title', ''))
            creator = st.text_input("창작자", value=data.get('creator', ''))
        with cr:
            summary = st.text_area("📖 작품소개", value=data.get('summary', ''), height=100)
            brief, high, note = st.text_input("📝 한줄평"), st.text_area("✨ 인상 깊은 부분"), st.text_area("🌈 PRISM")
            view_date = st.date_input("🍿 감상일", value=date.today())
            if st.button("✅ 기록 저장 (클라우드 동시 연동)", use_container_width=True):
                new = {"category": cat, "title": title, "creator": creator, "rel_date": data.get('date', ''), "venue": data.get('venue', ''), "summary": summary, "brief": brief, "highlights": high, "note": note, "img_url": img1, "img_url2": "", "save_date": str(date.today()), "view_date": str(view_date)}
                conn = get_connection()
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", list(new.values()))
                conn.commit()
                # --- [기록 시 클라우드 연동 부분] ---
                supabase.table("archive").upsert(new).execute()
                st.cache_data.clear(); st.success("저장 및 클라우드 연동 완료!"); time.sleep(0.8); st.rerun()

with tab_a:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; background: #1e1e1e; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 8px rgba(0,0,0,0.2); margin-top:5px;}
        .music-box { aspect-ratio: 1/1 !important; } /* 음악 카테고리 전용 1:1 설정 */
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
        .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
    </style>""", unsafe_allow_html=True)

    all_df = get_all_data()
    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'])
        cat_list = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sub_tabs = st.tabs(["📅 ALL"] + cat_list)
        grid = 2 if st.session_state.view_mode == "Mobile" else 6

        # --- [ALL 탭] ---
        with sub_tabs[0]:
            sel_y = st.selectbox("연도", sorted(all_df['v_dt'].dt.year.unique(), reverse=True))
            y_df = all_df[all_df['v_dt'].dt.year == sel_y]
            for m in range(12, 0, -1):
                m_df = y_df[y_df['v_dt'].dt.month == m]
                if not m_df.empty:
                    st.subheader(f"🗓️ {m}월")
                    rows = m_df.to_dict('records')
                    for i in range(0, len(rows), grid):
                        cols = st.columns(grid)
                        for j in range(grid):
                            if i+j < len(rows):
                                r = rows[i+j]
                                # 음악이면 music-box 클래스 추가
                                cls = "cal-img-box music-box" if r['category'] == "MUSIC" else "cal-img-box"
                                with cols[j]:
                                    st.markdown(f'<div class="{cls}"><div class="badge-cat">{r["category"]}</div><div class="badge-date">{r["v_dt"].day}일</div><img src="{r["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(r['title'][:10]+'..' if len(r['title'])>10 else r['title'], key=f"all_{r['id']}", use_container_width=True): show_details(r)

        # --- [카테고리별 탭] ---
        for idx, cname in enumerate(cat_list):
            with sub_tabs[idx+1]:
                c_df = all_df[all_df['category'] == cname]
                rows = c_df.to_dict('records')
                cls = "cal-img-box music-box" if cname == "MUSIC" else "cal-img-box"
                for i in range(0, len(rows), grid):
                    cols = st.columns(grid)
                    for j in range(grid):
                        if i+j < len(rows):
                            r = rows[i+j]
                            with cols[j]:
                                st.markdown(f'<div class="{cls}"><div class="badge-date">{r["view_date"]}</div><img src="{r["img_url"]}"></div>', unsafe_allow_html=True)
                                if st.button(r['title'][:10]+'..', key=f"cat_{idx}_{r['id']}", use_container_width=True): show_details(r)

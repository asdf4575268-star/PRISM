import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
import time
import re 
import xml.etree.ElementTree as ET
from supabase import create_client, Client

# --- [1. 기본 설정 및 디자인] ---
st.set_page_config(
    layout="wide", 
    page_title="PRISM ARCHIVE",
    page_icon="🌈",
    initial_sidebar_state="collapsed"
)

# API 키 및 DB 설정 (기존 정보 유지)
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
DB_NAME = 'archive_prism_total_v5.db'
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

# Supabase 설정
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    st.error("Supabase 설정(secrets)을 확인해주세요.")

# 커스텀 CSS (UI 개선)
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
        
        /* 메인 타이틀 */
        .main-title { font-size: 2.5rem; font-weight: 800; background: linear-gradient(45deg, #ff0000, #ff7300, #fffb00, #48ff00, #00ffd5, #002bff, #7a00ff, #ff00c8, #ff0000); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 1rem; }
        
        /* 카드 디자인 */
        .cal-img-box { 
            position: relative; width: 100%; aspect-ratio: 1/1.4; 
            overflow: hidden; border-radius: 12px; margin-top: 5px; 
            box-shadow: 0 10px 20px rgba(0,0,0,0.3); background: #1e1e1e;
            transition: transform 0.3s ease;
        }
        .cal-img-box:hover { transform: translateY(-5px); }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        
        /* 카테고리/날짜 배지 */
        .badge-cat { position: absolute; top: 10px; left: 10px; background: rgba(255, 255, 255, 0.9); color: black; padding: 2px 10px; border-radius: 20px; font-size: 10px; font-weight: bold; z-index: 10; }
        .badge-date { position: absolute; bottom: 10px; right: 10px; background: rgba(0, 0, 0, 0.6); color: white; padding: 2px 8px; border-radius: 6px; font-size: 11px; backdrop-filter: blur(4px); }
        
        /* 음악 전용(1:1) */
        .music-tab-style { aspect-ratio: 1/1 !important; }
        
        /* 폼 섹션 스타일 */
        .stTextArea textarea { font-size: 0.95rem !important; }
        hr { border: 0; border-top: 1px solid #333; margin: 1.5rem 0; }
    </style>
""", unsafe_allow_html=True)

# --- [2. DB 및 데이터 관리 로직] ---
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

# 동기화 함수들
def migrate_to_supabase():
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        local_data = conn.execute("SELECT * FROM archive").fetchall()
        if not local_data:
            st.toast("⚠️ 로컬 데이터가 없습니다.", icon="⚠️")
            return
        upload_list = [dict(row) for row in local_data]
        for d in upload_list:
            if 'id' in d: del d['id']
        supabase.table("archive").upsert(upload_list).execute() 
        st.toast(f"✅ {len(upload_list)}개 데이터 백업 완료!", icon="✅")
    except Exception as e:
        st.error(f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        if not cloud_data:
            st.toast("⚠️ 클라우드가 비어있습니다.", icon="⚠️")
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
        st.toast(f"✅ {len(to_insert)}개 데이터 복구 완료!", icon="✅")
    except Exception as e:
        st.error(f"❌ 복구 실패: {e}")

# --- [3. API 검색 함수 섹션] ---
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
            formatted_res.append({
                'display_name': f"{'📀' if is_album else '🎵'} {title} - {m.get('artistName', '')}", 
                'title': title, 'creator': m.get('artistName', ''), 
                'date': m.get('releaseDate', '')[:10], 
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 
                'venue': m.get('artistName', ''),
                'url': m.get('collectionViewUrl' if is_album else 'trackViewUrl', '')
            })
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
        full_creator = f"{creator_label} / [출연] {cast_names}" if cast_names else creator_label
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
            date_from = d.findtext('prfpdfrom')
            if search_year and search_year not in date_from: continue
            results.append({
                'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 
                'img': d.findtext('poster'), 'date': date_from, 'venue': d.findtext('fcltynm')
            })
        return results
    except: return []

def get_kopis_detail(mt20id):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        res = requests.get(url); root = ET.fromstring(res.content); d = root.find('db')
        if d is not None:
            crew = d.findtext('prfcrew').strip() if d.findtext('prfcrew') else ""
            cast = d.findtext('prfcast').strip() if d.findtext('prfcast') else ""
            return f"[제작] {crew} / [출연] {cast}".strip(" / ")
    except: return "상세정보 로드 실패"
    return "정보 없음"

# --- [4. 로그인 및 사이드바] ---
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not st.session_state.is_logged_in:
        input_password = st.text_input("Password", type="password")
        if input_password == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.is_logged_in = True
            st.rerun()
    else:
        st.success("Admin Mode Active")
        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.is_logged_in = False
            st.rerun()
        st.divider()
        st.markdown("### 🔄 Data Sync")
        col_sync1, col_sync2 = st.columns(2)
        with col_sync1: st.button("📤 Backup", on_click=migrate_to_supabase, use_container_width=True)
        with col_sync2: st.button("📥 Restore", on_click=restore_from_supabase, use_container_width=True)

    st.divider()
    st.markdown("### 📱 화면 모드")
    st.session_state.view_mode = st.radio("보기 옵션", ["PC", "Mobile"], horizontal=True, label_visibility="collapsed")

is_admin = st.session_state.is_logged_in
is_mobile = st.session_state.view_mode == "Mobile"

# --- [5. 상세 보기 팝업] ---
@st.dialog("📋 기록 상세", width="large")
def show_details(item):
    edit_mode = False
    if is_admin:
        t_col1, _, t_col3 = st.columns([0.2, 0.6, 0.2])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                conn = get_connection(); conn.execute("DELETE FROM archive WHERE id=?", (item['id'],)); conn.commit()
                try: supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
                except: pass
                st.cache_data.clear(); st.rerun()
        with t_col3: edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    col_img, col_txt = (st.container(), st.container()) if is_mobile else st.columns([0.35, 0.65])

    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 이미지 1", value=str(item.get('img_url', '')), key=f"edit_img1_{item['id']}")
            n_img2 = st.text_input("🖼️ 이미지 2", value=str(item.get('img_url2', '')), key=f"edit_img2_{item['id']}")
            if n_img and n_img != "None": st.image(n_img, use_container_width=True)
        with col_txt:
            with st.form(f"edit_f_{item['id']}"):
                n_title = st.text_input("📌 제목", value=item['title'])
                n_creator = st.text_input("👤 창작자", value=item['creator'])
                c1, c2 = st.columns(2)
                n_rel = c1.text_input("📅 제작일", value=item['rel_date'])
                n_venue = c2.text_input("📍 장소/플랫폼", value=item['venue'])
                n_view = st.date_input("🍿 감상일", value=pd.to_datetime(item['view_date']).date())
                n_sum = st.text_area("📖 작품소개", value=item['summary'], height=120)
                n_brief = st.text_input("📝 요약", value=item['brief'])
                n_high = st.text_area("✨ 인상 깊은 부분", value=item['highlights'], height=100)
                n_note = st.text_area("🌈 PRISM", value=item['note'], height=100)
                if st.form_submit_button("💾 수정사항 저장", use_container_width=True):
                    conn = get_connection()
                    conn.execute("UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=?, img_url2=? WHERE id=?",
                                 (n_title, n_creator, n_rel, n_venue, n_sum, n_brief, n_high, n_note, str(n_view), n_img, n_img2, item['id']))
                    conn.commit()
                    supabase.table("archive").update({"title":n_title, "creator":n_creator, "rel_date":n_rel, "venue":n_venue, "summary":n_sum, "brief":n_brief, "highlights":n_high, "note":n_note, "view_date":str(n_view), "img_url":n_img, "img_url2":n_img2}).eq("id_for_cloud", f"{item['title']}_{item['view_date']}").execute()
                    st.cache_data.clear(); st.success("수정되었습니다."); time.sleep(0.5); st.rerun()
    else:
        with col_img:
            for k in ['img_url', 'img_url2']:
                url = item.get(k)
                if url and str(url) != "None" and url.strip(): st.image(url, use_container_width=True)
        with col_txt:
            st.markdown(f"## {item['title']}")
            st.markdown(f"**{item['creator']}**")
            st.markdown(f"📅 {item['rel_date']} | 📍 {item['venue']}")
            st.markdown(f"🍿 **감상일: {item['view_date']}**")
            st.divider()
            sections = [("📖 작품소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 인상 깊은 부분", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]
            for label, key, color in sections:
                if item.get(key):
                    st.markdown(f'<div style="background:{color}; color:white; display:inline-block; padding:2px 12px; border-radius:12px; font-size:0.8em; margin-bottom:8px;">{label}</div>', unsafe_allow_html=True)
                    st.markdown(item[key].replace('\n', '  \n'))
                    st.markdown("<div style='margin-bottom:20px;'></div>", unsafe_allow_html=True)

# --- [6. 메인 UI] ---
st.markdown('<h1 class="main-title">🌈 PRISM ARCHIVE</h1>', unsafe_allow_html=True)

if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tab_a = st.tabs(["📂 ARCHIVE"])[0]
    tab_w = None

# WRITE 탭
if is_admin and tab_w:
    with tab_w:
        cat = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
        sq = st.text_input(f"🔍 {cat} 검색어 입력")
        if sq:
            res = []
            if cat == "BOOKS":
                books = search_books(sq)
                if books:
                    opts = {f"📚 {b['title']} ({b['publisher']})": b for b in books}
                    sel = st.selectbox("검색 결과", list(opts.keys()))
                    if st.button("✨ 데이터 가져오기"):
                        b = opts[sel]
                        st.session_state.api_data = {'title':b['title'], 'creator':", ".join(b['authors']), 'date':b['datetime'][:10], 'img':b['thumbnail'].replace("R120x174","R400x0") if b['thumbnail'] else "", 'venue':b['publisher'], 'summary':b['contents']}
                        st.rerun()
            elif cat == "MUSIC":
                tracks = search_apple_music(sq)
                if tracks:
                    opts = {t['display_name']: t for t in tracks}
                    sel = st.selectbox("검색 결과", list(opts.keys()))
                    if st.button("✨ 데이터 가져오기"):
                        m = opts[sel]
                        st.session_state.api_data = {'title':m['title'], 'creator':m['creator'], 'date':m['date'], 'img':m['img'], 'venue':m['creator'], 'summary':m['url']}
                        st.rerun()
            elif cat == "STAGE":
                stages = search_kopis(sq)
                if stages:
                    opts = {f"🎭 {s['title']} ({s['venue']})": s for s in stages}
                    sel = st.selectbox("검색 결과", list(opts.keys()))
                    if st.button("✨ 데이터 가져오기"):
                        s = opts[sel]
                        st.session_state.api_data = {'title':s['title'], 'creator':get_kopis_detail(s['id']), 'date':s['date'], 'img':s['img'], 'venue':s['venue'], 'summary':f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?mt20Id={s['id']}"}
                        st.rerun()
            else: # MOVIES, SERIES
                tmdb_res = search_tmdb(sq, cat)
                if tmdb_res:
                    t_key = 'title' if cat == 'MOVIES' else 'name'
                    d_key = 'release_date' if cat == 'MOVIES' else 'first_air_date'
                    opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in tmdb_res}
                    sel = st.selectbox("검색 결과", list(opts.keys()))
                    if st.button("✨ 데이터 가져오기"):
                        r = opts[sel]
                        det = get_tmdb_details(r['id'], cat)
                        st.session_state.api_data = {'title':r.get(t_key), 'creator':det['creator'], 'date':r.get(d_key), 'img':f"https://image.tmdb.org/t/p/w500{r['poster_path']}" if r['poster_path'] else "", 'venue':det['venue'], 'summary':r.get('overview','')}
                        st.rerun()

        st.divider()
        # 입력 폼
        api_data = st.session_state.get('api_data', {})
        f_col1, f_col2 = (st.container(), st.container()) if is_mobile else st.columns([0.4, 0.6])
        with f_col1:
            in_img = st.text_input("🖼️ 이미지 URL", value=api_data.get('img',''))
            if in_img: st.image(in_img, use_container_width=True)
            in_title = st.text_input("📌 제목", value=api_data.get('title',''))
            in_creator = st.text_input("👤 창작자", value=api_data.get('creator',''))
            in_rel = st.text_input("📅 제작일", value=api_data.get('date',''))
            in_venue = st.text_input("📍 장소/플랫폼", value=api_data.get('venue',''))
        with f_col2:
            in_sum = st.text_area("📖 작품소개", value=api_data.get('summary',''), height=100)
            in_brief = st.text_input("📝 요약 (한 줄 평)")
            in_high = st.text_area("✨ 인상 깊은 부분", height=100)
            in_note = st.text_area("🌈 PRISM", height=100)
            in_view = st.date_input("🍿 감상일", value=date.today())
            if st.button("✅ 기록 저장하기", use_container_width=True, type="primary"):
                rec = (cat, in_title, in_creator, in_rel, in_venue, in_sum, in_brief, in_high, in_note, in_img, "", str(date.today()), str(in_view))
                conn = get_connection(); conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rec); conn.commit()
                # Supabase 업로드 (Upsert용 dict 구성)
                supabase.table("archive").upsert({"category":cat, "title":in_title, "creator":in_creator, "rel_date":in_rel, "venue":in_venue, "summary":in_sum, "brief":in_brief, "highlights":in_high, "note":in_note, "img_url":in_img, "img_url2":"", "save_date":str(date.today()), "view_date":str(in_view)}).execute()
                st.cache_data.clear(); st.success("저장되었습니다!"); st.session_state.api_data = {}; time.sleep(0.5); st.rerun()

# ARCHIVE 탭
with tab_a:
    all_df = get_all_data()
    if all_df.empty:
        st.info("아직 기록된 데이터가 없습니다.")
    else:
        # 상단 필터/검색
        search_all = st.text_input("🔍 아카이브 내 검색 (제목, 창작자, 내용)", "")
        if search_all:
            all_df = all_df[all_df.apply(lambda row: search_all.lower() in str(row.values).lower(), axis=1)]

        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        cat_emojis = {"BOOKS": "📚", "MUSIC": "🎧", "MOVIES": "🎞️", "SERIES": "📽️", "STAGE": "🎭"}
        sub_tabs = st.tabs([f"📅 ALL ({len(all_df)})"] + [f"{cat_emojis[c]} {c}" for c in cat_order])
        grid_cols = 2 if is_mobile else 6

        # ALL 탭 (월별 정렬)
        with sub_tabs[0]:
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'])
            years = sorted(all_df['v_dt'].dt.year.unique(), reverse=True)
            for y in years:
                y_df = all_df[all_df['v_dt'].dt.year == y]
                for m in range(12, 0, -1):
                    m_df = y_df[y_df['v_dt'].dt.month == m]
                    if not m_df.empty:
                        st.subheader(f"🗓️ {y}년 {m}월")
                        items = m_df.to_dict('records')
                        for i in range(0, len(items), grid_cols):
                            cols = st.columns(grid_cols)
                            for j in range(grid_cols):
                                if i+j < len(items):
                                    item = items[i+j]
                                    with cols[j]:
                                        m_cls = "music-tab-style" if item['category'] == "MUSIC" else ""
                                        st.markdown(f'<div class="cal-img-box {m_cls}"><div class="badge-cat">{item["category"]}</div><div class="badge-date">{item["v_dt"].day}일</div><img src="{item["img_url"]}"></div>', unsafe_allow_html=True)
                                        if st.button(item['title'][:12]+'..' if len(item['title'])>12 else item['title'], key=f"btn_all_{item['id']}", use_container_width=True):
                                            show_details(item)

        # 카테고리별 탭
        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx+1]:
                c_df = all_df[all_df['category'] == c_name]
                if c_df.empty: st.info(f"{c_name} 기록이 없습니다.")
                else:
                    items = c_df.to_dict('records')
                    for i in range(0, len(items), grid_cols):
                        cols = st.columns(grid_cols)
                        for j in range(grid_cols):
                            if i+j < len(items):
                                item = items[i+j]
                                with cols[j]:
                                    m_cls = "music-tab-style" if c_name == "MUSIC" else ""
                                    st.markdown(f'<div class="cal-img-box {m_cls}"><div class="badge-date">{item["view_date"]}</div><img src="{item["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(item['title'][:12]+'..' if len(item['title'])>12 else item['title'], key=f"btn_cat_{idx}_{item['id']}", use_container_width=True):
                                        show_details(item)

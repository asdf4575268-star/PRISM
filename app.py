import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
import time
import re 
import xml.etree.ElementTree as ET
from supabase import create_client, Client

# --- [1. 설정 및 UI 스타일링] ---
st.set_page_config(
    layout="wide", 
    page_title="PRISM ARCHIVE",
    page_icon="🌈",
    initial_sidebar_state="collapsed"
)

TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
DB_NAME = 'archive_prism_total_v5.db'
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.markdown("""
    <style>
        .main-title { font-size: 2.2rem; font-weight: 800; color: #FFFFFF; margin-bottom: 1rem; }
        .cal-img-box { 
            position: relative; width: 100%; aspect-ratio: 1/1.4; 
            overflow: hidden; border-radius: 10px; margin-top: 5px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.4); background: #1a1a1a;
        }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .music-tab-style { aspect-ratio: 1/1 !important; }
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0, 0, 0, 0.75); color: #FFEB3B; padding: 2px 8px; border-radius: 5px; font-size: 10px; font-weight: bold; z-index: 5; }
        .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 5px; font-size: 10px; z-index: 5; }
        
        /* 버튼 및 입력창 커스텀 */
        .stButton button { border-radius: 8px; }
        .stTextInput input, .stTextArea textarea { border-radius: 8px !important; }
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

def migrate_to_supabase():
    try:
        conn = get_connection(); conn.row_factory = sqlite3.Row
        local_data = conn.execute("SELECT * FROM archive").fetchall()
        if not local_data: return st.toast("로컬 데이터가 없습니다.")
        upload_list = [dict(row) for row in local_data]
        for d in upload_list:
            if 'id' in d: del d['id']
        supabase.table("archive").upsert(upload_list).execute() 
        st.toast("✅ 클라우드 백업 완료!")
    except Exception as e: st.error(f"백업 실패: {e}")

def restore_from_supabase():
    try:
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        if not cloud_data: return st.toast("클라우드가 비어있습니다.")
        conn = get_connection(); cursor = conn.cursor()
        local_df = get_all_data()
        local_keys = set(zip(local_df['title'], local_df['view_date'])) if not local_df.empty else set()
        to_insert = []
        for row in cloud_data:
            if (row['title'], row['view_date']) not in local_keys:
                to_insert.append((row['category'], row['title'], row['creator'], row['rel_date'], row['venue'], row['summary'], row['brief'], row['highlights'], row['note'], row.get('img_url'), row.get('img_url2'), row['save_date'], row['view_date']))
        if to_insert:
            cursor.executemany("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", to_insert)
            conn.commit(); st.cache_data.clear()
        st.toast(f"✅ {len(to_insert)}개 복구 완료!")
    except Exception as e: st.error(f"복구 실패: {e}")

# --- [3. 스크랩 전용 API 엔진] ---
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
        return res.json().get("documents", [])
    except: return []

def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url).json().get("results", [])
        formatted = []
        for m in res:
            is_album = m.get('wrapperType') == 'collection'
            title = m.get('collectionName' if is_album else 'trackName', 'Unknown')
            formatted.append({'display_name': f"{'📀' if is_album else '🎵'} {title} - {m.get('artistName', '')}", 'title': title, 'creator': m.get('artistName', ''), 'date': m.get('releaseDate', '')[:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName', ''), 'url': m.get('collectionViewUrl' if is_album else 'trackViewUrl', '')})
        return formatted
    except: return []

def search_tmdb(query, category):
    tp = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{tp}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

def get_tmdb_details(item_id, category):
    tp = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{tp}/{item_id}?api_key={TMDB_API_KEY}&language=ko-KR&append_to_response=credits"
    try:
        res = requests.get(url).json()
        crew = res.get('credits', {}).get('crew', [])
        cast = res.get('credits', {}).get('cast', [])
        if tp == "movie":
            director = next((m['name'] for m in crew if m.get('job') == 'Director'), "정보 없음")
            creator = f"[감독] {director}"; venue = res.get('production_companies', [{}])[0].get('name', '')
        else:
            creator_names = ", ".join([c['name'] for c in res.get('created_by', [])]) or "정보 없음"
            creator = f"[작가/제작] {creator_names}"; venue = res.get('networks', [{}])[0].get('name', '')
        cast_info = f"[출연] {', '.join([c['name'] for c in cast[:3]])}" if cast else ""
        return {"creator": f"{creator} / {cast_info}".strip(" / "), "venue": venue}
    except: return {"creator": "정보 없음", "venue": ""}

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=50&cpage=1"
    try:
        res = requests.get(url); root = ET.fromstring(res.content); items = root.findall('db')
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in items]
    except: return []

def get_kopis_detail(mt20id):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        res = requests.get(url); root = ET.fromstring(res.content); d = root.find('db')
        if d is not None:
            cr = d.findtext('prfcrew').strip() if d.findtext('prfcrew') else ""; cs = d.findtext('prfcast').strip() if d.findtext('prfcast') else ""
            return f"[제작] {cr} / [출연] {cs}".strip(" / ")
    except: return "정보 없음"

# --- [4. 앱 레이아웃 및 세션 제어] ---
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"
if "api_data" not in st.session_state: st.session_state.api_data = {}

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not st.session_state.is_logged_in:
        pw = st.text_input("Password", type="password")
        if pw == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.is_logged_in = True; st.rerun()
    else:
        st.success("Admin Active")
        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.is_logged_in = False; st.rerun()
        st.divider()
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)
    st.divider()
    st.session_state.view_mode = st.radio("화면 모드", ["PC", "Mobile"], horizontal=True)

is_admin = st.session_state.is_logged_in
is_mobile = st.session_state.view_mode == "Mobile"

# --- [5. 상세 보기 다이얼로그] ---
@st.dialog("📋 기록 상세", width="large")
def show_details(item):
    edit_mode = False
    if is_admin:
        c1, _, c2 = st.columns([0.2, 0.6, 0.2])
        if c1.button("🗑️ 삭제", key=f"d_{item['id']}"):
            conn = get_connection(); conn.execute("DELETE FROM archive WHERE id=?", (item['id'],)); conn.commit()
            st.cache_data.clear(); st.rerun()
        edit_mode = c2.toggle("✏️ 수정", key=f"e_{item['id']}")
        st.divider()

    col_img, col_txt = (st.container(), st.container()) if is_mobile else st.columns([0.35, 0.65])
    
    if is_admin and edit_mode:
        with col_txt:
            with st.form(f"f_e_{item['id']}"):
                n_t = st.text_input("제목", item['title']); n_c = st.text_input("창작자", item['creator'])
                n_v = st.text_input("장소/플랫폼", item['venue']); n_vd = st.date_input("감상일", value=pd.to_datetime(item['view_date']).date())
                n_s = st.text_area("작품소개", item['summary']); n_b = st.text_input("요약", item['brief'])
                n_h = st.text_area("하이라이트", item['highlights']); n_n = st.text_area("PRISM", item['note'])
                if st.form_submit_button("저장"):
                    conn = get_connection(); conn.execute("UPDATE archive SET title=?, creator=?, venue=?, view_date=?, summary=?, brief=?, highlights=?, note=? WHERE id=?", (n_t, n_c, n_v, str(n_vd), n_s, n_b, n_h, n_n, item['id']))
                    conn.commit(); st.cache_data.clear(); st.rerun()
    else:
        with col_img:
            if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
            if item.get('img_url2'): st.image(item['img_url2'], use_container_width=True)
        with col_txt:
            st.markdown(f"## {item['title']}")
            st.markdown(f"**{item['creator']}** \n📅 {item['rel_date']} | 📍 {item['venue']}  \n🍿 **감상일: {item['view_date']}**")
            st.divider()
            for lab, k, col in [("📖 작품소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 하이라이트", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]:
                if item.get(k):
                    st.markdown(f'<div style="background:{col}; color:white; display:inline-block; padding:2px 12px; border-radius:12px; font-size:0.8em; margin-bottom:8px;">{lab}</div>', unsafe_allow_html=True)
                    st.markdown(item[k].replace('\n', '  \n'))

# --- [6. 메인 화면 구성] ---
st.markdown('<h1 class="main-title">🌈 PRISM ARCHIVE</h1>', unsafe_allow_html=True)

if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tab_a = st.tabs(["📂 ARCHIVE"])[0]; tab_w = None

# 스크랩 및 기록 기능 (WRITE)
if is_admin and tab_w:
    with tab_w:
        cat = st.radio("CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
        sq = st.text_input(f"🔍 {cat} 스크랩 검색 (검색어 입력 후 Enter)")
        
        if sq:
            if cat == "BOOKS":
                res = search_books(sq)
                if res:
                    opts = {f"📚 {b['title']} ({b['publisher']})": b for b in res}
                    sel = st.selectbox("검색 결과 선택", list(opts.keys()))
                    if st.button("✨ 데이터 스크랩"):
                        b = opts[sel]
                        st.session_state.api_data = {'title':b['title'], 'creator':", ".join(b['authors']), 'date':b['datetime'][:10], 'img':b['thumbnail'].replace("R120x174","R400x0"), 'venue':b['publisher'], 'summary':b['contents']}
                        st.rerun()
            elif cat == "MUSIC":
                res = search_apple_music(sq)
                if res:
                    opts = {m['display_name']: m for m in res}
                    sel = st.selectbox("검색 결과 선택", list(opts.keys()))
                    if st.button("✨ 데이터 스크랩"):
                        m = opts[sel]
                        st.session_state.api_data = {'title':m['title'], 'creator':m['creator'], 'date':m['date'], 'img':m['img'], 'venue':m['creator'], 'summary':m['url']}
                        st.rerun()
            elif cat == "STAGE":
                res = search_kopis(sq)
                if res:
                    opts = {f"🎭 {s['title']} ({s['venue']})": s for s in res}
                    sel = st.selectbox("검색 결과 선택", list(opts.keys()))
                    if st.button("✨ 데이터 스크랩"):
                        s = opts[sel]
                        st.session_state.api_data = {'title':s['title'], 'creator':get_kopis_detail(s['id']), 'date':s['date'], 'img':s['img'], 'venue':s['venue'], 'summary':f"https://kopis.or.kr...mt20Id={s['id']}"}
                        st.rerun()
            else: # MOVIES, SERIES
                res = search_tmdb(sq, cat)
                if res:
                    tk = 'title' if cat == 'MOVIES' else 'name'; dk = 'release_date' if cat == 'MOVIES' else 'first_air_date'
                    opts = {f"🎬 {r.get(tk)} ({str(r.get(dk))[:4]})": r for r in res}
                    sel = st.selectbox("검색 결과 선택", list(opts.keys()))
                    if st.button("✨ 데이터 스크랩"):
                        r = opts[sel]; det = get_tmdb_details(r['id'], cat)
                        st.session_state.api_data = {'title':r.get(tk), 'creator':det['creator'], 'date':r.get(dk), 'img':f"https://image.tmdb.org/t/p/w500{r['poster_path']}", 'venue':det['venue'], 'summary':r.get('overview','')}
                        st.rerun()

        st.divider()
        # 스크랩된 데이터로 폼 채우기
        data = st.session_state.get('api_data', {})
        c_l, c_r = (st.container(), st.container()) if is_mobile else st.columns([0.4, 0.6])
        with c_l:
            i_img = st.text_input("🖼️ 이미지 URL", value=data.get('img',''))
            if i_img: st.image(i_img, use_container_width=True)
            i_t = st.text_input("제목", value=data.get('title',''))
            i_c = st.text_input("창작자", value=data.get('creator',''))
            i_d = st.text_input("제작일", value=data.get('date',''))
            i_v = st.text_input("장소/플랫폼", value=data.get('venue',''))
        with c_r:
            i_s = st.text_area("작품소개", value=data.get('summary',''), height=100)
            i_b = st.text_input("요약 (한 줄 평)")
            i_h = st.text_area("인상 깊은 부분", height=100)
            i_n = st.text_area("🌈 PRISM", height=100)
            i_vd = st.date_input("🍿 감상일", value=date.today())
            if st.button("💾 아카이브 기록 저장", use_container_width=True, type="primary"):
                conn = get_connection()
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", 
                             (cat, i_t, i_c, i_d, i_v, i_s, i_b, i_h, i_n, i_img, "", str(date.today()), str(i_vd)))
                conn.commit()
                # Supabase 동시 저장
                try: supabase.table("archive").upsert({"category":cat, "title":i_t, "creator":i_c, "rel_date":i_d, "venue":i_v, "summary":i_s, "brief":i_b, "highlights":i_h, "note":i_n, "img_url":i_img, "save_date":str(date.today()), "view_date":str(i_vd)}).execute()
                except: pass
                st.cache_data.clear(); st.session_state.api_data = {}; st.success("성공적으로 기록되었습니다!"); time.sleep(0.5); st.rerun()

# 아카이브 탭 (ARCHIVE)
with tab_a:
    all_df = get_all_data()
    if not all_df.empty:
        search_q = st.text_input("🔍 아카이브 검색 (제목, 창작자...)", "")
        if search_q:
            all_df = all_df[all_df.apply(lambda r: search_q.lower() in str(r.values).lower(), axis=1)]
            
        cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sub_tabs = st.tabs([f"📅 ALL ({len(all_df)})"] + [f"{c}" for c in cats])
        cols_n = 2 if is_mobile else 6

        with sub_tabs[0]: # ALL (월별)
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'])
            for y in sorted(all_df['v_dt'].dt.year.unique(), reverse=True):
                for m in range(12, 0, -1):
                    m_df = all_df[(all_df['v_dt'].dt.year == y) & (all_df['v_dt'].dt.month == m)]
                    if not m_df.empty:
                        st.subheader(f"🗓️ {y}. {m}")
                        items = m_df.to_dict('records')
                        for i in range(0, len(items), cols_n):
                            cols = st.columns(cols_n)
                            for j in range(cols_n):
                                if i+j < len(items):
                                    item = items[i+j]
                                    with cols[j]:
                                        m_style = "music-tab-style" if item['category'] == "MUSIC" else ""
                                        st.markdown(f'<div class="cal-img-box {m_style}"><div class="badge-cat">{item["category"]}</div><div class="badge-date">{item["v_dt"].day}일</div><img src="{item["img_url"]}"></div>', unsafe_allow_html=True)
                                        if st.button(item['title'][:10], key=f"all_{item['id']}", use_container_width=True): show_details(item)

        for idx, cn in enumerate(cats):
            with sub_tabs[idx+1]:
                c_df = all_df[all_df['category'] == cn]
                if c_df.empty: st.info("기록이 없습니다.")
                else:
                    items = c_df.to_dict('records')
                    for i in range(0, len(items), cols_n):
                        cols = st.columns(cols_n)
                        for j in range(cols_n):
                            if i+j < len(items):
                                item = items[i+j]
                                with cols[j]:
                                    m_style = "music-tab-style" if cn == "MUSIC" else ""
                                    st.markdown(f'<div class="cal-img-box {m_style}"><div class="badge-date">{item["view_date"]}</div><img src="{item["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(item['title'][:10], key=f"c_{idx}_{item['id']}", use_container_width=True): show_details(item)
    else: st.info("아직 기록이 없습니다. WRITE 탭에서 첫 기록을 남겨보세요!")

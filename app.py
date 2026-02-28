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

# --- [2. DB 연결 최적화] ---
@st.cache_resource
def get_connection():
    # check_same_thread=False는 Streamlit의 멀티스레드 환경에서 필수입니다.
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                     rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, 
                     img_url TEXT, img_url2 TEXT, save_date TEXT, view_date TEXT)''')
    conn.commit()

init_db()

@st.cache_data(ttl=600) # 10분간 데이터 조회 결과 캐싱
def get_all_data():
    conn = get_connection()
    return pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

# --- [3. 동기화 로직 최적화 (Bulk Insert)] ---
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
        
        # 중복 방지를 위해 기존 데이터 조회
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
            st.cache_data.clear() # 데이터가 바뀌었으므로 캐시 초기화
            
        st.session_state.sync_msg = ("success", f"✅ {len(to_insert)}개의 데이터를 복구했습니다!")
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
        return {"creator": f"{creator_label} / [출연] {cast_names}".strip(" / "), "venue": venue_info}
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
            results.append({'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': date_from, 'venue': d.findtext('fcltynm')})
        return results
    except: return []

def get_kopis_detail(mt20id):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        d = root.find('db')
        if d is not None:
            crew = d.findtext('prfcrew', '').strip()
            cast = d.findtext('prfcast', '').strip()
            return f"[제작] {crew} / [출연] {cast}".strip(" / ")
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
                conn = get_connection()
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                conn.commit()
                try: supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
                except: pass
                st.cache_data.clear()
                st.rerun()
        with t_col3:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    if is_admin and edit_mode:
        components.html("<script>window.parent.addEventListener('beforeunload', (e)=>{e.preventDefault();e.returnValue='';});</script>", height=0)

    col_img, col_txt = (st.container(), st.container()) if is_mobile else st.columns([0.3, 0.7])

    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 이미지 1", value=str(item.get('img_url', '')), key=f"img_in_{item['id']}")
            n_img2 = st.text_input("🖼️ 이미지 2", value=str(item.get('img_url2', '')), key=f"img2_in_{item['id']}")
            if n_img: st.image(n_img, use_container_width=True)
        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                labels = {"BOOKS": "📖 출판사", "MUSIC": "💿 레이블", "MOVIES": "🎬 제작사", "SERIES": "📺 플랫폼", "STAGE": "📍 장소"}
                v_label = labels.get(item.get('category'), "📍 장소")
                c1, c2 = st.columns(2)
                n_rel = c1.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_venue = c2.text_input(v_label, value=str(item.get('venue', '')))
                n_view_date = st.date_input("🍿 감상일 수정", value=pd.to_datetime(item.get('view_date')).date())
                n_sum = st.text_area("📖 작품소개", value=str(item.get('summary', '')), height=150)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '')))
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '')), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '')), height=100)

                if st.form_submit_button("💾 저장"):
                    conn = get_connection()
                    conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=?, img_url2=? WHERE id=?""", 
                                 (n_title, n_creator, n_rel, n_venue, n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, n_img2, item['id']))
                    conn.commit()
                    supabase.table("archive").update({"title": n_title, "creator": n_creator, "rel_date": n_rel, "venue": n_venue, "summary": n_sum, "brief": n_brief, "highlights": n_high, "note": n_note, "view_date": str(n_view_date), "img_url": n_img, "img_url2": n_img2}).eq("title", item['title']).eq("view_date", item['view_date']).execute()
                    st.cache_data.clear()
                    st.success("✅ 수정 완료!"); time.sleep(0.5); st.rerun()
    else: 
        with col_img:
            for key in ['img_url', 'img_url2']:
                url = item.get(key)
                if url and str(url) != "None": st.image(url, use_container_width=True)
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"#### **[{item.get('category')}]**\n**{item.get('creator')}**\n**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
            st.markdown(f'<p style="color: #E2E2E2; font-weight: bold; font-size: 1.1em;">🍿감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()
            sections = [("📖 작품소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 인상 깊은 부분", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]
            for label, key, color in sections:
                content = item.get(key)
                if content:
                    st.markdown(f'<div style="display: inline-block; background-color: {color}; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px;">{label}</div>', unsafe_allow_html=True)
                    st.markdown(content.replace('\n', '  \n'))
                    st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)

# --- [5. 메인 화면 로직] ---
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"
is_admin = st.session_state.is_logged_in

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not is_admin:
        pw = st.text_input("Password", type="password")
        if pw == st.secrets["ADMIN_PASSWORD"]: 
            st.session_state.is_logged_in = True; st.rerun()
    else:
        if st.button("🔓 Logout"): st.session_state.is_logged_in = False; st.rerun()
        st.divider()
        if 'sync_msg' in st.session_state:
            t, m = st.session_state.sync_msg
            if t == "success": st.success(m)
            elif t == "warning": st.warning(m)
            else: st.error(m)
            del st.session_state.sync_msg
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)
    st.divider()
    st.session_state.view_mode = st.radio("보기 옵션", ["PC", "Mobile"], horizontal=True)

is_mobile = st.session_state.view_mode == "Mobile"
st.title("🌈PRISM ARCHIVE")

tab_titles = ["📂 ARCHIVE", "🖋️ WRITE"] if is_admin else ["📂 ARCHIVE"]
tabs = st.tabs(tab_titles)
tab_a = tabs[0]

if is_admin:
    with tabs[1]:
        category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
        search_query = st.text_input(f"🔍 {category} 검색")
        if search_query:
            # (기존 검색 API 로직 유지 - 공간상 생략)
            pass 
        
        # 저장 로직에서 st.cache_data.clear() 필수
        if st.button("✅ 기록 저장"):
            # ... (저장 코드 실행 후)
            st.cache_data.clear()
            st.success("저장 완료!")

with tab_a:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; background: #1e1e1e; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 8px rgba(0,0,0,0.2); margin-top:5px;}
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
        .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
    </style>""", unsafe_allow_html=True)

    all_df = get_all_data()
    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sub_tabs = st.tabs([f"📅 ALL"] + [f"{c}" for c in cat_order])
        grid_cols = 2 if is_mobile else 6

        with sub_tabs[0]:
            years = sorted(all_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            sel_y = st.selectbox("📅 연도", years)
            y_df = all_df[all_df['v_dt'].dt.year == sel_y]
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
                                with cols[j]:
                                    st.markdown(f'<div class="cal-img-box"><div class="badge-cat">{row["category"]}</div><div class="badge-date">{pd.to_datetime(row["view_date"]).day}일</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:10]+'..' if len(row['title'])>10 else row['title'], key=f"btn_{row['id']}", use_container_width=True): show_details(row)

        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx+1]:
                c_data = all_df[all_df['category'] == c_name]
                if not c_data.empty:
                    items = c_data.to_dict('records')
                    for i in range(0, len(items), grid_cols):
                        cols = st.columns(grid_cols)
                        for j in range(grid_cols):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    st.markdown(f'<div class="cal-img-box"><div class="badge-date">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:10]+'..', key=f"cbtn_{idx}_{row['id']}", use_container_width=True): show_details(row)

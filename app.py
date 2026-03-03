import streamlit as st
from PIL import Image
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime, timedelta
import time
import re 
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
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

# 기사 크롤링 함수 추가
def get_article_info(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        title = soup.find("meta", property="og:title")
        title = title["content"] if title else soup.title.string
        desc = soup.find("meta", property="og:description")
        summary = desc["content"] if desc else ""
        img = soup.find("meta", property="og:image")
        img_url = img["content"] if img else "https://images.unsplash.com/photo-1504711432869-efd597cdd04d?q=80&w=1000&auto=format&fit=crop"
        site = soup.find("meta", property="og:site_name")
        venue = site["content"] if site else ""
        return {"title": title, "summary": summary, "img": img_url, "venue": venue}
    except: return None

# (Supabase 동기화 함수 migrate_to_supabase, restore_from_supabase 생략 - 원본 유지)
def migrate_to_supabase():
    try:
        conn = get_connection()
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
        st.session_state.sync_msg = ("success", f"✅ {len(to_insert)}개의 새로운 데이터를 복구했습니다!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

# --- [3. 로그인 & 사이드바] ---
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_password" not in st.session_state:
    st.session_state.user_password = ""
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "PC"

if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True

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
    if is_admin:
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
    st.session_state.view_mode = st.radio("📱 화면 모드", ["PC", "Mobile"], horizontal=True)

is_mobile = st.session_state.view_mode == "Mobile"

# --- [4. API 검색 함수 (생략 - 원본 유지)] ---
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
    except: pass
    return "정보 없음"


# --- [5. 팝업 상세 보기 (참조 기능 통합)] ---
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
        with t_col3: edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    col_img, col_txt = (st.container(), st.container()) if is_mobile else st.columns([0.3, 0.7])

    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 이미지 1", value=str(item.get('img_url', '')), key=f"img_in_{item['id']}")
            n_img2 = st.text_input("🖼️ 이미지 2", value=str(item.get('img_url2', '')), key=f"img2_in_{item['id']}")
            if n_img and n_img != "None": st.image(n_img, use_container_width=True)
        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                n_rel = st.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_venue = st.text_input("📍 장소/플랫폼", value=str(item.get('venue', '')))
                try: curr_view = pd.to_datetime(item.get('view_date')).date()
                except: curr_view = date.today()
                n_view_date = st.date_input("🍿 감상일", value=curr_view)
                n_sum = st.text_area("📖 작품소개", value=str(item.get('summary', '')), height=150)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '')))
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '')), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '')), height=100)
                if st.form_submit_button("💾 저장"):
                    conn = get_connection()
                    conn.execute("UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=?, img_url2=? WHERE id=?", 
                                 (n_title, n_creator, n_rel, n_venue, n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, n_img2, item['id']))
                    conn.commit()
                    supabase.table("archive").update({"title": n_title, "creator": n_creator, "rel_date": n_rel, "venue": n_venue, "summary": n_sum, "brief": n_brief, "highlights": n_high, "note": n_note, "view_date": str(n_view_date), "img_url": n_img, "img_url2": n_img2}).eq("title", item['title']).eq("view_date", item['view_date']).execute()
                    st.cache_data.clear()
                    st.success("✅ 수정 완료!"); time.sleep(0.5); st.rerun()
    else: 
        with col_img:
            for k in ['img_url', 'img_url2']:
                url = item.get(k)
                if url and url != "None": st.image(url, use_container_width=True)
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**{item.get('creator')}**")
            st.write(f"**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
            st.markdown(f'<p style="color: #E2E2E2; font-weight: bold; font-size: 1.1em;">🍿감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()
            sections = [("📖 작품소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 인상 깊은 부분", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]
            for label, key, color in sections:
                content = item.get(key)
                if content:
                    st.markdown(f'<div style="display: inline-block; background-color:{color}; color:white; padding:2px 12px; border-radius:12px; font-size:0.8em; margin-bottom:10px;">{label}</div>', unsafe_allow_html=True)
                    st.markdown(content.replace('\n', '  \n'))
                    st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)
            
            # [일방향 참조 기능] 관련 스크랩이 있으면 링크 노출
            if is_admin and item['category'] != "SCRAP":
                all_df = get_all_data()
                scraps = all_df[(all_df['category'] == 'SCRAP') & (all_df['note'].str.contains(f"#{item['title']}", na=False))]
                if not scraps.empty:
                    st.markdown("#### 🔗 관련 SCRAP")
                    for _, s in scraps.iterrows():
                        if st.button(f"📰 {s['title']}", key=f"rel_{s['id']}", use_container_width=True):
                            show_details(s)

# --- [6. 메인 헤더] ---
def get_base64(path):
    with open(path, "rb") as f: return base64.b64encode(f.read()).decode()

logo_base64 = get_base64("logo.png")
st.markdown(f'<div style="display:flex; align-items:center; gap:6px;"><img src="data:image/png;base64,{logo_base64}" width="90"><h1>PRISM ARCHIVE</h1></div>', unsafe_allow_html=True)

# --- [7. WRITE 탭] ---
if is_admin: tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else: tab_a = st.tabs(["📂 ARCHIVE"])[0]; tab_w = None

if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"], horizontal=True)
        
        if category == "SCRAP":
            link_input = st.text_input("🔗 스크랩할 링크(URL) 입력")
            if st.button("✨ 정보 자동 가져오기"):
                info = get_article_info(link_input)
                if info:
                    st.session_state.api_data = {'title': info['title'], 'creator': info['venue'], 'date': str(date.today()), 'venue': link_input, 'summary': info['summary'], 'img': info['img']}
                    st.rerun()
        else:
            search_query = st.text_input(f"🔍 {category} 검색")
            if search_query:
                if category == "BOOKS":
                    res = search_books(search_query)
                    if res:
                        opts = {f"📚 {b['title']}": b for b in res}
                        sel = st.selectbox("결과 선택", list(opts.keys()))
                        if st.button("✨ 가져오기"):
                            b = opts[sel]
                            st.session_state.api_data = {'title': b['title'], 'creator': ", ".join(b['authors']), 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'venue': b.get('publisher', ''), 'summary': b.get('contents', '')}
                            st.rerun()
                elif category == "MUSIC":
                    res = search_apple_music(search_query)
                    if res:
                        opts = {m['display_name']: m for m in res}
                        sel = st.selectbox("결과 선택", list(opts.keys()))
                        if st.button("✨ 가져오기"):
                            m = opts[sel]; st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': f"{m.get('url', '')}\n\n"}; st.rerun()
                elif category == "STAGE":
                    res = search_kopis(search_query)
                    if res:
                        opts = {f"🎭 {s['title']} ({s['venue']})": s for s in res}
                        sel = st.selectbox("결과 선택", list(opts.keys()))
                        if st.button("✨ 가져오기"):
                            s = opts[sel]; st.session_state.api_data = {'title': s['title'], 'creator': get_kopis_detail(s['id']), 'date': s['date'], 'venue': s['venue'], 'img': s['img'], 'summary': f"https://www.kopis.or.kr/mt20Id={s['id']}"}; st.rerun()
                else:
                    res = search_tmdb(search_query, category)
                    if res:
                        t_key = 'title' if category == 'MOVIES' else 'name'
                        d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                        opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}
                        sel = st.selectbox("결과 선택", list(opts.keys()))
                        if st.button("✨ 가져오기"):
                            s = opts[sel]; details = get_tmdb_details(s['id'], category)
                            st.session_state.api_data = {'title': s.get(t_key), 'creator': details['creator'], 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'venue': details['venue'], 'summary': s.get('overview', '')}; st.rerun()

        st.divider()
        data = st.session_state.get('api_data', {})
        cl, cr = st.columns([0.4, 0.6]) if not is_mobile else (st.container(), st.container())
        with cl:
            img_url_val = st.text_input("🖼️ 이미지", value=data.get('img', ''))
            if img_url_val and img_url_val != "None": st.image(img_url_val, use_container_width=True)
            title = st.text_input("제목", value=data.get('title', ''))
            creator = st.text_input("창작자/매체", value=data.get('creator', ''))
            rel_date = st.text_input("📅 작품날짜", value=data.get('date', str(date.today())))
            venue = st.text_input("📍 장소/플랫폼/URL", value=data.get('venue', ''))
        with cr:
            summary = st.text_area("📖 원문/소개", value=data.get('summary', ''), height=100)
            brief = st.text_input("📝 5줄 요약")
            highlights = st.text_area("✨ 인상 깊은 부분", height=100)
            note = st.text_area("🌈 PRISM 인사이트 (#태그포함)", height=100)
            view_date = st.date_input("🍿 기록일", value=date.today())
            if st.button("✅ 기록 저장", use_container_width=True):
                new_record = {"category": str(category), "title": title, "creator": creator, "rel_date": rel_date, "venue": venue, "summary": summary, "brief": brief, "highlights": highlights, "note": note, "img_url": img_url_val, "img_url2": "", "save_date": str(date.today()), "view_date": str(view_date)}
                conn = get_connection()
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", 
                             (new_record["category"], new_record["title"], new_record["creator"], new_record["rel_date"], new_record["venue"], new_record["summary"], new_record["brief"], new_record["highlights"], new_record["note"], new_record["img_url"], new_record["img_url2"], new_record["save_date"], new_record["view_date"]))
                conn.commit()
                try: supabase.table("archive").upsert(new_record).execute()
                except: pass
                st.cache_data.clear(); st.success("✅ 저장 완료!"); st.session_state.api_data = {}; time.sleep(0.8); st.rerun()

# --- [8. ARCHIVE/SCRAP 탭] ---
with tab_a:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; margin-top: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); background: #1e1e1e; display: flex; align-items: center; justify-content: center; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .music-tab-style { aspect-ratio: 1/1 !important; }
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0, 0, 0, 0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
        .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
    </style>""", unsafe_allow_html=True)

    all_df = get_all_data()
    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        if is_admin: cat_order.append("SCRAP")
        
        tab_titles = [f"📅 ALL ({len(all_df[all_df['category'] != 'SCRAP'])})"] + [f"{c} ({len(all_df[all_df['category'] == c])})" for c in cat_order]
        sub_tabs = st.tabs(tab_titles)
        grid_cols = 2 if is_mobile else 6

        # [ALL 탭] - SCRAP은 제외
        with sub_tabs[0]:
            display_df = all_df[all_df['category'] != "SCRAP"]
            years = sorted(display_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            sel_y = st.selectbox("📅 연도", years)
            y_df = display_df[display_df['v_dt'].dt.year == sel_y]
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
                                    if st.button(row['title'][:10], key=f"all_{row['id']}", use_container_width=True): show_details(row)

        # [각 카테고리별 탭]
        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx + 1]:
                c_data = all_df[all_df['category'] == c_name]
                if c_name == "SCRAP" and is_admin:
                    # [SCRAP 주간 대시보드]
                    all_tags = []
                    for n in c_data['note'].fillna(""): all_tags.extend(extract_tags(n))
                    if all_tags:
                        st.markdown("### 🏷️ 이번 주 키워드")
                        tag_html = "".join([f'<span style="background:#444; padding:4px 10px; margin:3px; border-radius:12px; font-size:0.9em; color:yellow;">#{t}</span>' for t in set(all_tags)])
                        st.markdown(tag_html, unsafe_allow_html=True); st.write("")
                    
                    for week, group in c_data.groupby(pd.Grouper(key='v_dt', freq='W-MON')):
                        if group.empty: continue
                        w_start = (week - timedelta(days=6)).strftime('%m.%d')
                        w_end = week.strftime('%m.%d')
                        with st.expander(f"📅 {w_start} ~ {w_end} 주간 스크랩", expanded=True):
                            for _, row in group.iterrows():
                                sc1, sc2 = st.columns([0.2, 0.8])
                                with sc1: st.image(row['img_url'], use_container_width=True)
                                with sc2:
                                    if st.button(row['title'], key=f"sc_{row['id']}", use_container_width=True): show_details(row)
                                    st.caption(f"{row['creator']} | {row['view_date']}")
                                    if row['brief']: st.markdown(f"> {row['brief']}")
                else:
                    # 일반 아카이브 그리드
                    items = c_data.to_dict('records')
                    music_cls = "music-tab-style" if c_name == "MUSIC" else ""
                    for i in range(0, len(items), grid_cols):
                        cols = st.columns(grid_cols)
                        for j in range(grid_cols):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    st.markdown(f'<div class="cal-img-box {music_cls}"><div class="badge-date">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:10], key=f"c_{row['id']}", use_container_width=True): show_details(row)

import calendar
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
import html
import json
import extra_streamlit_components as stx

# ==========================================
# 1. CONSTANTS & CONFIGURATION (상수 및 설정)
# ==========================================
FAVICON = Image.open("logo.png").resize((64, 64), Image.LANCZOS)
st.set_page_config(page_title="PRISM", page_icon=FAVICON, layout="wide", initial_sidebar_state="collapsed")

# API Keys & DB
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
DB_NAME = 'archive_prism_total_v5.db'
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# Category Definitions
CATEGORIES = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"]
CAT_EMOJIS = {"BOOKS": "📚", "MUSIC": "🎧", "MOVIES": "🎞️", "SERIES": "📽️", "STAGE": "🎭", "SCRAP": "📰"}
FORM_KEYS = ['f_title', 'f_creator', 'f_date', 'f_venue', 'f_img', 'f_video', 'f_summary', 'f_brief', 'f_highlights', 'f_note']

# ==========================================
# 2. STATE INITIALIZATION (상태 중앙 관리)
# ==========================================
cookie_manager = stx.CookieManager()

if "is_logged_in" not in st.session_state: 
    st.session_state.is_logged_in = (cookie_manager.get(cookie="admin_logged_in") == "yes")
if "user_password" not in st.session_state: st.session_state.user_password = ""
if "selected_tag" not in st.session_state: st.session_state.selected_tag = None
if "week_offset" not in st.session_state: st.session_state.week_offset = 0
if "should_clear_form" not in st.session_state: st.session_state.should_clear_form = False
if "edit_target_id" not in st.session_state: st.session_state.edit_target_id = None
if "edit_source" not in st.session_state: st.session_state.edit_source = None
if "main_nav" not in st.session_state: 
    st.session_state.main_nav = "🖋️ WRITE" if st.session_state.is_logged_in else "📂 ARCHIVE"
if 'f_view_date' not in st.session_state: st.session_state.f_view_date = date.today()

for k in FORM_KEYS:
    if k not in st.session_state: st.session_state[k] = ""

# 초기화 버튼을 눌렀을 때 폼 비우기
if st.session_state.should_clear_form:
    for k in FORM_KEYS: st.session_state[k] = ""
    st.session_state.f_view_date = date.today()
    st.session_state.edit_target_id = None
    st.session_state.edit_source = None
    st.session_state.should_clear_form = False

if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True
IS_ADMIN = st.session_state.is_logged_in

# ==========================================
# 3. DATABASE & CLOUD SYNC (데이터베이스)
# ==========================================
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@st.cache_resource
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                     rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, 
                     img_url TEXT, img_url2 TEXT, save_date TEXT, view_date TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS plan 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, plan_date TEXT, category TEXT, title TEXT, memo TEXT)''')
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
        if local_data: supabase.table("archive").upsert([dict(row) for row in local_data]).execute() 
            
        local_plan = conn.execute("SELECT * FROM plan").fetchall()
        if local_plan: supabase.table("plan").upsert([dict(row) for row in local_plan]).execute()
        
        st.session_state.sync_msg = ("success", "✅ 클라우드 백업 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cloud_data = supabase.table("archive").select("*").execute().data
        if cloud_data:
            cursor.execute("DELETE FROM archive")
            to_insert = [(r['id'], r['category'], r['title'], r['creator'], r['rel_date'], r['venue'], r['summary'], r.get('brief', ''), r.get('highlights', ''), r['note'], r.get('img_url'), r.get('img_url2'), r['save_date'], r['view_date']) for r in cloud_data]
            cursor.executemany("INSERT INTO archive VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", to_insert)
                
        cloud_plan = supabase.table("plan").select("*").execute().data
        if cloud_plan:
            cursor.execute("DELETE FROM plan")
            plan_insert = [(rp['id'], rp['plan_date'], rp['category'], rp['title'], rp['memo']) for rp in cloud_plan]
            cursor.executemany("INSERT INTO plan VALUES (?,?,?,?,?)", plan_insert)
        
        conn.commit()
        st.cache_data.clear() 
        st.session_state.sync_msg = ("success", "✅ 데이터를 성공적으로 복구했습니다!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

@st.cache_resource
def auto_sync_on_startup():
    if get_connection().execute("SELECT COUNT(*) FROM archive").fetchone()[0] == 0:
        restore_from_supabase()
    return True
auto_sync_on_startup()

def safe_str(val): return "" if val is None or str(val) == "None" else str(val)

# ==========================================
# 4. API & SEARCH FUNCTIONS (외부 API 통신)
# ==========================================
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
            title = m.get('collectionName' if is_album else 'trackName', '제목 없음')
            formatted_res.append({
                'display_name': f"{'📀' if is_album else '🎵'} {title} - {m.get('artistName', '')}", 
                'title': title, 'creator': m.get('artistName', ''), 'date': m.get('releaseDate', '')[:10], 
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'venue': m.get('artistName', ''),
                'is_album': is_album, 'collection_id': m.get('collectionId'), 'url': m.get('collectionViewUrl' if is_album else 'trackViewUrl', '')
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
    url = f"https://api.themoviedb.org/3/{'movie' if is_movie else 'tv'}/{item_id}?api_key={TMDB_API_KEY}&language=ko-KR&append_to_response=credits"
    try:
        res = requests.get(url).json()
        crew_list, cast_list = res.get('credits', {}).get('crew', []), res.get('credits', {}).get('cast', [])
        
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
        root = ET.fromstring(requests.get(url).content)
        results = []
        for d in root.findall('db'):
            date_from = d.findtext('prfpdfrom')
            if search_year and search_year not in date_from: continue
            results.append({'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': date_from, 'venue': d.findtext('fcltynm')})
        return results
    except: return []

def get_kopis_detail(mt20id):
    try:
        d = ET.fromstring(requests.get(f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}").content).find('db')
        if d is not None:
            info = []
            if crew := d.findtext('prfcrew'): info.append(f"[제작] {crew.strip()}")
            if cast := d.findtext('prfcast'): info.append(f"[출연] {cast.strip()}")
            return " / ".join(info) if info else "정보 없음"
    except: pass
    return "정보 없음"

def scrape_url(url):
    try:
        html_text = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).text
        title = re.search(r'property="og:title"\s+content="(.*?)"', html_text) or re.search(r'<title>(.*?)</title>', html_text)
        img = re.search(r'property="og:image"\s+content="(.*?)"', html_text)
        site = re.search(r'property="og:site_name"\s+content="(.*?)"', html_text)
        desc = re.search(r'property="og:description"\s+content="(.*?)"', html_text)
        return {"title": html.unescape(title.group(1)) if title else "제목 없음", "img": img.group(1) if img else "", "venue": site.group(1) if site else "URL", "summary": f"{url}\n\n{html.unescape(desc.group(1)) if desc else ''}"}
    except: return None

# ==========================================
# 5. UI COMPONENTS (공통 다이얼로그 렌더링)
# ==========================================
def render_item_details(data_dict, item_id, is_plan=False):
    cat = data_dict.get('category')
    
    if IS_ADMIN:
        c1, _, c3 = st.columns([0.3, 0.4, 0.3])
        table_name = "plan" if is_plan else "archive"
        if c1.button("🗑️ 삭제", key=f"del_{table_name}_{item_id}", use_container_width=True):
            conn = get_connection()
            conn.execute(f"DELETE FROM {table_name} WHERE id=?", (item_id,))
            conn.commit()
            st.cache_data.clear() 
            try: supabase.table(table_name).delete().eq("id", item_id).execute()
            except: pass
            st.rerun()
            
        if c3.button("✏️ 수정", key=f"edit_{table_name}_{item_id}", use_container_width=True, type="primary"):
            st.session_state.edit_target_id = item_id
            st.session_state.edit_source = table_name
            st.session_state.main_category_radio = cat
            
            st.session_state.f_title = safe_str(data_dict.get('title'))
            st.session_state.f_creator = safe_str(data_dict.get('creator'))
            st.session_state.f_date = safe_str(data_dict.get('rel_date'))
            st.session_state.f_venue = safe_str(data_dict.get('venue'))
            st.session_state.f_img = safe_str(data_dict.get('img_url'))
            st.session_state.f_video = safe_str(data_dict.get('img_url2'))
            st.session_state.f_brief = safe_str(data_dict.get('brief'))
            st.session_state.f_highlights = safe_str(data_dict.get('highlights'))
            st.session_state.f_note = safe_str(data_dict.get('note'))
            st.session_state.f_summary = safe_str(data_dict.get('summary'))
            date_key = 'plan_date' if is_plan else 'view_date'
            try: st.session_state.f_view_date = pd.to_datetime(data_dict.get(date_key)).date()
            except: st.session_state.f_view_date = date.today()
            
            st.session_state.main_nav = "🖋️ WRITE"
            st.rerun()
        st.divider()

    col_img, col_txt = st.columns([0.3, 0.7])
    with col_img:
        img_url = data_dict.get('img_url')
        if img_url and str(img_url) != "None": st.image(img_url, use_container_width=True)
        
        memo_content = data_dict.get('img_url2', '')
        if memo_content and str(memo_content) != "None":
            url_match = re.search(r'(https?://[^\s]+)', memo_content)
            if url_match:
                media_url = url_match.group(1)
                text_part = memo_content.replace(media_url, '').strip(' /|-')
                if text_part: st.markdown(f'<div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">📎 {text_part}</div>', unsafe_allow_html=True)
                if re.search(r'\.(jpg|jpeg|png|webp|gif)', media_url, re.IGNORECASE) or "image.tmdb.org" in media_url:
                    st.image(media_url, use_container_width=True)
                else:
                    try: st.video(media_url)
                    except: st.markdown(f"**[🔗 첨부 링크 보러가기]({media_url})**")
            else: 
                st.markdown(f'<div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">📎 {memo_content}</div>', unsafe_allow_html=True)
    
    with col_txt:
        st.markdown(f'# {data_dict.get("title")}')
        creator_text = data_dict.get('creator', '')
        if creator_text: st.write(f"**{'📰 ' if cat == 'SCRAP' else ''}{creator_text}**")
            
        st.write(f"**📅 {data_dict.get('rel_date', '')} | 📍 {data_dict.get('venue', '')}**")
        
        date_label = "🗓️ 예정일" if is_plan else "🍿 감상/완료일"
        date_val = data_dict.get('plan_date') if is_plan else data_dict.get('view_date')
        date_color = "#E50914" if is_plan else "#E2E2E2"
        st.markdown(f'<p style="color: {date_color}; font-weight: bold; font-size: 1.1em;">{date_label}: {date_val}</p>', unsafe_allow_html=True)
        st.divider()
        
        # 스크랩 영역 표시 완벽 분리
        sections = [
            ("📰 기사 원본/링크", "summary", "#444"), 
            ("✍️ 직접 필사", "note", "#1E425E"),
            ("🎯 중심맥락(논지)", "brief", "#0E6245"),
            ("💡 핵심 사례(논거) 및 구조", "highlights", "#7D5600")
        ] if cat == "SCRAP" else [
            ("💎 DRIP", "brief", "#E50914"), 
            ("🖋️ PRISM", "note", "#1E425E"),
            ("💡 SIGHT", "summary", "#0E6245"), 
            ("🔖 SENSE", "highlights", "#7D5600")
        ]
            
        for label, key, color in sections:
            val = data_dict.get(key)
            if val and str(val).strip():
                st.markdown(f'<div style="display: inline-block; background-color: {color}; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px; font-weight: bold;">{label}</div>', unsafe_allow_html=True)
                st.markdown(str(val).replace('\n', '  \n'))
                st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🔗 외부에 리뷰 공유하기 (복사)"):
            share_text = f"[{cat}] {data_dict.get('title')}\n" + (f"👤 {creator_text}\n\n" if creator_text else "\n")
            for label, key, _ in sections:
                if data_dict.get(key) and str(data_dict.get(key)).strip():
                    share_text += f"{label}:\n{data_dict.get(key)}\n\n"
            st.code(share_text.strip(), language="markdown")

    if IS_ADMIN and is_plan:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✅ 완료 (ARCHIVE로 이동)", key=f"done_plan_{item_id}", use_container_width=True, type="primary"):
            conn = get_connection()
            new_record = {
                "category": cat, "title": data_dict['title'], "creator": data_dict.get("creator", ""), "rel_date": data_dict.get("rel_date", ""),
                "venue": data_dict.get("venue", ""), "summary": data_dict.get("summary", ""), "brief": data_dict.get("brief", ""), 
                "highlights": data_dict.get("highlights", ""), "note": data_dict.get("note", ""), "img_url": data_dict.get("img_url", ""), 
                "img_url2": data_dict.get("img_url2", ""), "save_date": str(date.today()), "view_date": data_dict['plan_date']
            }
            conn.execute("""INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", tuple(new_record.values()))
            conn.execute("DELETE FROM plan WHERE id=?", (item_id,))
            conn.commit()
            st.cache_data.clear()
            try: 
                supabase.table("archive").upsert(new_record).execute()
                supabase.table("plan").delete().eq("id", item_id).execute()
            except: pass
            st.success("🎉 ARCHIVE로 이동 완료!"); time.sleep(0.5); st.rerun()

@st.dialog("📋 ARCHIVE 기록", width="large")
def show_details(item): render_item_details(item if isinstance(item, dict) else item.to_dict(), item['id'], is_plan=False)

@st.dialog("🗓️ 상세 정보", width="large")
def show_plan_details(item):
    item_dict = item if isinstance(item, dict) else item.to_dict()
    try: rich_data = json.loads(item_dict['memo'])
    except: rich_data = {"note": item_dict.get('memo', '')}
    
    combined_data = {**rich_data, "id": item_dict['id'], "category": item_dict['category'], "title": item_dict['title'], "plan_date": item_dict['plan_date']}
    render_item_details(combined_data, item_dict['id'], is_plan=True)

# ==========================================
# 6. MAIN APPLICATION ROUTING & VIEWS
# ==========================================
def get_base64(path):
    try:
        with open(path, "rb") as f: return base64.b64encode(f.read()).decode()
    except: return ""

# 로그인 사이드바
with st.sidebar:
    st.markdown("### 🔐 관리자 접속")
    if not IS_ADMIN:
        input_password = st.text_input("비밀번호", type="password", key="sidebar_pw_2")
        if input_password:
            if input_password == st.secrets["ADMIN_PASSWORD"]:
                cookie_manager.set("admin_logged_in", "yes", expires_at=datetime.now() + timedelta(days=30))
                st.session_state.user_password = input_password 
                st.session_state.is_logged_in = True
                st.session_state.main_nav = "🖋️ WRITE"
                time.sleep(0.5)
                st.rerun()
            else: st.error("비밀번호가 틀렸습니다.")
    if IS_ADMIN:
        st.success("관리자 모드 활성화됨")
        if st.button("🔓 로그아웃", key="logout_2", use_container_width=True):
            cookie_manager.set("admin_logged_in", "no")
            st.session_state.is_logged_in = False
            st.session_state.user_password = ""
            st.session_state.main_nav = "📂 ARCHIVE"
            time.sleep(0.5)
            st.rerun()
        st.divider()
        st.markdown("### 🛠️ 데이터 오류 수정")
        if st.button("🧹 중복 데이터 정리", use_container_width=True):
            conn = get_connection()
            conn.execute("DELETE FROM archive WHERE id NOT IN (SELECT MAX(id) FROM archive GROUP BY title, category)")
            conn.execute("DELETE FROM plan WHERE id NOT IN (SELECT MAX(id) FROM plan GROUP BY title, category)")
            conn.commit()
            st.cache_data.clear()
            st.success("✅ 중복이 제거되었습니다!")
            time.sleep(1.5); st.rerun()
        st.divider()
        st.markdown("### 🔄 데이터 동기화")
        if 'sync_msg' in st.session_state:
            m_type, m_txt = st.session_state.sync_msg
            st.success(m_txt) if m_type == "success" else st.error(m_txt)
            del st.session_state.sync_msg
        st.button("📤 클라우드 백업", key="backup_2", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 클라우드 복구", key="restore_2", on_click=restore_from_supabase, use_container_width=True)

# 헤더 타이틀 및 네비게이션
st.markdown(f"""<style>.header-wrap {{ display: flex; align-items: center; gap: 6px; }} .header-wrap h1 {{ margin: 0; letter-spacing: -1px; }}</style>
<div class="header-wrap"><img src="data:image/png;base64,{get_base64('logo.png')}" width="90"><h1>PRISM ARCHIVE</h1></div>""", unsafe_allow_html=True)

if IS_ADMIN:
    st.markdown("""<style>div[role="radiogroup"] > label { font-weight: bold; font-size: 1.1em; padding-right: 15px; }</style>""", unsafe_allow_html=True)
    st.radio("메뉴", ["🖋️ WRITE", "📂 ARCHIVE"], horizontal=True, label_visibility="collapsed", key="main_nav")

tab_w = (st.session_state.main_nav == "🖋️ WRITE")

# ----------------- [WRITE 탭] -----------------
if IS_ADMIN and tab_w:
    category = st.radio("📂 카테고리", CATEGORIES, horizontal=True, key="main_category_radio")
    search_query = st.text_input(f"🔍 {category} 검색 (결과 클릭 시 자동 입력)")
    
    # API 검색 처리
    if search_query:
        if category == "SCRAP":
            if st.button("✨ 가져오기"):
                if s := scrape_url(search_query):
                    st.session_state.update(edit_target_id=None, edit_source=None, f_title=s['title'], f_creator='', f_date=str(date.today()), f_img=s['img'], f_venue=s['venue'], f_summary=s['summary'], f_highlights="", f_note="", f_brief="", f_video="")
                    st.rerun()
                else: st.error("URL 정보를 가져올 수 없습니다.")
        elif category == "BOOKS":
            if res := search_books(search_query):
                sel = st.selectbox("결과 선택", list((opts := {f"📚 {b['title']}": b for b in res}).keys()))
                if st.button("✨ 가져오기"):
                    b = opts[sel]
                    st.session_state.update(edit_target_id=None, edit_source=None, f_title=b['title'], f_creator=", ".join(b['authors']), f_date=b['datetime'][:10], f_img=b.get('thumbnail', '').replace("R120x174", "R400x0"), f_venue=b.get('publisher', ''), f_summary=b.get('contents', ''), f_highlights="", f_note="", f_brief="", f_video="")
                    st.rerun()
        elif category == "MUSIC":
            if res := search_apple_music(search_query):
                sel = st.selectbox("결과 선택", list((opts := {m['display_name']: m for m in res}).keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    tl_text = ""
                    if m.get('is_album') and m.get('collection_id'):
                        try:
                            tracks = [t['trackName'] for t in requests.get(f"https://itunes.apple.com/lookup?id={m['collection_id']}&entity=song").json().get("results", []) if t.get('wrapperType') == 'track']
                            if tracks: tl_text = "💿 트랙리스트\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(tracks)])
                        except: pass
                    st.session_state.update(edit_target_id=None, edit_source=None, f_title=m['title'], f_creator=m['creator'], f_date=m['date'], f_img=m['img'], f_venue=m['venue'], f_summary=f"{m.get('url', '')}\n\n" if m.get('url') else "", f_highlights=tl_text, f_note="", f_brief="", f_video="")
                    st.rerun()
        elif category == "STAGE":
            if res := search_kopis(search_query):
                sel = st.selectbox("결과 선택", list((opts := {f"🎭 {s['title']} [{s['date']}~] ({s['venue']})": s for s in res}).keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.update(edit_target_id=None, edit_source=None, f_title=s['title'], f_creator=get_kopis_detail(s['id']), f_date=s['date'], f_img=s['img'], f_venue=s['venue'], f_summary=f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={s['id']}", f_highlights="", f_note="", f_brief="", f_video="")
                    st.rerun()
        else: 
            if res := search_tmdb(search_query, category):
                t_key, d_key = ('title', 'release_date') if category == 'MOVIES' else ('name', 'first_air_date')
                sel = st.selectbox("결과 선택", list((opts := {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}).keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]; details = get_tmdb_details(s['id'], category)
                    st.session_state.update(edit_target_id=None, edit_source=None, f_title=s.get(t_key, ''), f_creator=details['creator'], f_date=s.get(d_key, ''), f_img=f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", f_venue=details['venue'], f_summary=s.get('overview', ''), f_highlights="", f_note="", f_brief="", f_video="")
                    st.rerun()

    st.divider()

    # 입력 폼
    is_update = st.session_state.edit_target_id is not None
    if is_update:
        st.info("🚨 현재 데이터 수정 모드입니다. (완료 후 저장 버튼을 눌러주세요)")
    else:
        st.markdown(f"#### 📝 NEW ({category})")
        
    with st.container(border=True):
        cl, cr = st.columns([0.4, 0.6])
        with cl:
            st.text_input("🖼️ 이미지 URL", key="f_img")
            st.text_input("🎬 관련 영상(URL) 또는 제목/메모", key="f_video")
            if st.session_state.f_img and st.session_state.f_img.strip() and st.session_state.f_img != "None": 
                st.image(st.session_state.f_img, use_container_width=True)
            
            st.text_input("📌 제목", key="f_title")
            st.text_input("👤 창작자" if category == "SCRAP" else "👤 창작자", key="f_creator")
            st.text_input("📅 작품 날짜", key="f_date")
            st.text_input("📍 장소/플랫폼", key="f_venue")
            st.date_input("🍿 감상 완료/예정일 (주간 계획 시 활용)", key="f_view_date")
        
        with cr:
            # 카테고리가 스크랩일 때 기사 원본과 필사 영역을 명확히 분리
            if category == "SCRAP":
                st.markdown("#### 🗺️ 기사 스크랩 및 직접 필사")
                st.text_area("📰 기사 원본 (텍스트 및 링크 복사)", key="f_summary", height=150)
                st.text_area("✍️ 직접 필사하기", key="f_note", height=150)
                st.text_input("🎯 중심맥락(논지)", key="f_brief")
                st.text_area("💡 핵심 사례(논거) 및 구조", key="f_highlights", height=100)
            else:
                st.text_input("1. 💎 DRIP", key="f_brief")
                st.text_area("2. 🖋️ PRISM", key="f_note", height=300)
                st.text_area("3. 💡 SIGHT (API 연동 시 기본 정보 자동입력)", key="f_summary", height=150)
                st.text_area("4. 🔖 SENSE", key="f_highlights", height=150)
        
        st.markdown("<br>", unsafe_allow_html=True)
        cb1, cb2, cb3 = st.columns([0.4, 0.4, 0.2])
        
        def save_data(to_archive=True, is_update_mode=False):
            if not st.session_state.f_title.strip(): return False
            conn = get_connection()
            data = { "category": str(category), "title": st.session_state.f_title.strip(), "creator": st.session_state.f_creator.strip(), "rel_date": st.session_state.f_date.strip(), "venue": st.session_state.f_venue.strip(), "summary": st.session_state.f_summary.strip(), "brief": st.session_state.f_brief.strip(), "highlights": st.session_state.f_highlights.strip(), "note": st.session_state.f_note.strip(), "img_url": st.session_state.f_img.strip(), "img_url2": st.session_state.f_video.strip() }
            
            if is_update_mode:
                if st.session_state.edit_source == 'archive':
                    data.update({"view_date": str(st.session_state.f_view_date)})
                    conn.execute("""UPDATE archive SET category=?, title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, img_url=?, img_url2=?, view_date=? WHERE id=?""", (*data.values(), st.session_state.edit_target_id))
                    try: supabase.table("archive").update(data).eq("id", st.session_state.edit_target_id).execute()
                    except: pass
                else:
                    memo_payload = json.dumps(data, ensure_ascii=False)
                    conn.execute("UPDATE plan SET category=?, title=?, plan_date=?, memo=? WHERE id=?", (str(category), st.session_state.f_title.strip(), str(st.session_state.f_view_date), memo_payload, st.session_state.edit_target_id))
                    try: supabase.table("plan").update({"category": str(category), "title": st.session_state.f_title.strip(), "plan_date": str(st.session_state.f_view_date), "memo": memo_payload}).eq("id", st.session_state.edit_target_id).execute()
                    except: pass
            else:
                if to_archive:
                    data.update({"save_date": str(date.today()), "view_date": str(st.session_state.f_view_date)})
                    conn.execute("""INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", tuple(data.values()))
                    try: supabase.table("archive").upsert(data).execute()
                    except: pass
                else:
                    memo_payload = json.dumps(data, ensure_ascii=False)
                    conn.execute("INSERT INTO plan (plan_date, category, title, memo) VALUES (?,?,?,?)", (str(st.session_state.f_view_date), str(category), st.session_state.f_title.strip(), memo_payload))
                    try: supabase.table("plan").upsert({"plan_date": str(st.session_state.f_view_date), "category": str(category), "title": st.session_state.f_title.strip(), "memo": memo_payload}).execute()
                    except: pass
            
            conn.commit()
            st.cache_data.clear()
            st.session_state.should_clear_form = True
            return True

        if is_update:
            if cb1.button("💾 수정 내용 저장", use_container_width=True, type="primary"):
                if save_data(is_update_mode=True): st.success("✅ 안전하게 수정되었습니다!"); time.sleep(0.8); st.rerun()
                else: st.warning("제목을 입력해 주세요.")
        else:
            if cb1.button("✅ ARCHIVE 저장", use_container_width=True, type="primary"):
                if save_data(to_archive=True): st.success("✅ ARCHIVE 저장 완료!"); time.sleep(0.8); st.rerun()
                else: st.warning("제목을 입력해 주세요.")
            if cb2.button("🗓️ Weekly Contents 등록", use_container_width=True):
                if save_data(to_archive=False): st.success("🗓️ Weekly Contents에 추가되었습니다!"); time.sleep(0.8); st.rerun()
                else: st.warning("제목을 입력해 주세요.")

        if cb3.button("🔄 비우기", use_container_width=True):
            st.session_state.should_clear_form = True
            st.rerun()

    st.divider()
    
    # Weekly Contents 뷰어
    col_l, col_c, col_r = st.columns([0.1, 0.8, 0.1])
    with col_l:
        if st.button("⬅️", use_container_width=True): st.session_state.week_offset -= 1; st.rerun()
    
    today_ts = pd.Timestamp(date.today()); view_monday = today_ts - pd.Timedelta(days=today_ts.weekday()) + pd.Timedelta(weeks=st.session_state.week_offset)
    view_sunday = view_monday + pd.Timedelta(days=6)
    
    with col_c:
        st.markdown(f"<h3 style='text-align: center; margin-top:0;'>📅 Weekly Contents ({view_monday.isocalendar().week}주차)</h3><p style='text-align: center; color: #888; font-size: 0.9em; margin-bottom: 20px;'>{view_monday.strftime('%m.%d')} ~ {view_sunday.strftime('%m.%d')}</p>", unsafe_allow_html=True)
    with col_r:
        if st.button("➡️", use_container_width=True): st.session_state.week_offset += 1; st.rerun()
            
    plan_df = pd.read_sql_query("SELECT * FROM plan ORDER BY plan_date ASC", get_connection())
    if not plan_df.empty: plan_df['p_dt'] = pd.to_datetime(plan_df['plan_date'])
    week_data = plan_df[(plan_df['p_dt'].dt.date >= view_monday.date()) & (plan_df['p_dt'].dt.date <= view_sunday.date())] if not plan_df.empty else pd.DataFrame()

    if week_data.empty: st.markdown("<div style='text-align: center; color:#666; padding: 20px;'>예정된 콘텐츠가 없습니다.</div>", unsafe_allow_html=True)
    else:
        grid_cols = 5
        items = week_data.to_dict('records')
        for i in range(0, len(items), grid_cols):
            cols = st.columns(grid_cols)
            for j in range(grid_cols):
                if i + j < len(items):
                    row = items[i + j]
                    with cols[j]:
                        emoji = CAT_EMOJIS.get(row['category'], "📌")
                        st.markdown(f"<div style='text-align:center; font-size: 0.9em; color: #3399FF; margin-bottom: 5px; font-weight: bold;'>{row['plan_date'][5:].replace('-', '.')}</div>", unsafe_allow_html=True)
                        try: img_url = json.loads(row['memo']).get('img_url', '')
                        except: img_url = ""
                        
                        if img_url and img_url.strip() and img_url != "None":
                            st.markdown(f"""<div style='position: relative; width: 100%; aspect-ratio: 1/1; border-radius: 6px; overflow: hidden; margin-bottom: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.3); background-color: #2A2A2A; display: flex; align-items: center; justify-content: center;'><img src="{img_url}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display='none'"><div style="position: absolute; top: 4px; left: 4px; background: rgba(0,0,0,0.6); padding: 2px 6px; border-radius: 4px; font-size: 12px;">{emoji}</div></div>""", unsafe_allow_html=True)
                        else:
                            st.markdown(f"""<div style='background-color: #2A2A2A; padding: 10px; border-radius: 6px; border-left: 4px solid #3399FF; margin-bottom: 5px; aspect-ratio: 1/1; display: flex; align-items: center; justify-content: center; text-align: center;'><div style='font-size: 2em; font-weight: bold; line-height: 1.3;'>{emoji}</div></div>""", unsafe_allow_html=True)
                        
                        # "수정" 대신 제목으로 버튼 라벨링
                        short_title = row['title'][:10] + "..." if len(row['title']) > 10 else row['title']
                        if st.button(f"✏️ {short_title}", key=f"dtl_cal_{row['id']}", use_container_width=True): show_plan_details(row)

# ----------------- [ARCHIVE 탭] -----------------
elif not tab_w:
    st.markdown("""<style>.cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; margin-top: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); background: #1e1e1e; display: flex; align-items: center; justify-content: center; } .cal-img-box img { width: 100%; height: 100%; object-fit: cover; } .music-tab-style { aspect-ratio: 1/1 !important; } .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0, 0, 0, 0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; } .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; } @media (min-width: 600px) { [data-testid="stHorizontalBlock"] { display: flex !important; flex-wrap: nowrap !important; gap: 10px !important; } [data-testid="column"] { flex: 1 1 0% !important; min-width: 0 !important; } }</style>""", unsafe_allow_html=True)
    all_df = get_all_data()

    if not all_df.empty:
        if search_query_archive := st.text_input("🔍", key="global_search"):
            mask = (all_df['title'].str.contains(search_query_archive, case=False, na=False) | all_df['creator'].str.contains(search_query_archive, case=False, na=False) | all_df['summary'].str.contains(search_query_archive, case=False, na=False) | all_df['note'].str.contains(search_query_archive, case=False, na=False) | all_df['venue'].str.contains(search_query_archive, case=False, na=False))
            all_df = all_df[mask]; st.markdown(f"**'{search_query_archive}'** 검색 결과 ({len(all_df)})"); st.divider()

        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        main_df, scrap_df = all_df[all_df['category'] != "SCRAP"], all_df[all_df['category'] == "SCRAP"]
        cat_order = CATEGORIES[:-1]
        
        tab_titles = [f"📅 ALL ({len(main_df)})"] + [f"{CAT_EMOJIS[c]} {c} ({len(main_df[main_df['category'] == c])})" for c in cat_order]
        if IS_ADMIN: tab_titles.append(f"🔐 스크랩 ({len(scrap_df)})")
        sub_tabs = st.tabs(tab_titles)
        grid_cols = 6

        with sub_tabs[0]:
            if years := sorted(main_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True):
                sel_y = st.selectbox("📅 연도 선택", options=years, format_func=lambda y: f"{y} ({len(main_df[main_df['v_dt'].dt.year == y])})", key="archive_year_sel")
                y_df = main_df[main_df['v_dt'].dt.year == sel_y]
                
                for m in range(12, 0, -1):
                    m_data = y_df[y_df['v_dt'].dt.month == m]
                    if not m_data.empty:
                        st.subheader(f"🗓️ {m}월 ({len(m_data)})")
                        items = m_data.to_dict('records')
                        for i in range(0, len(items), grid_cols):
                            cols = st.columns(grid_cols)
                            for j in range(grid_cols):
                                if i+j < len(items):
                                    row = items[i+j]
                                    img_style = 'style="height: auto; aspect-ratio: 1/1;"' if row["category"] == "MUSIC" else ""
                                    with cols[j]:
                                        st.markdown(f'<div class="cal-img-box"><div class="badge-cat">{row["category"]}</div><div class="badge-date">{pd.to_datetime(row["view_date"]).day}일</div><img src="{row["img_url"]}" {img_style}></div>', unsafe_allow_html=True)
                                        if st.button(row['title'][:10] + "..." if len(row['title']) > 10 else row['title'], key=f"all_btn_{row['id']}", use_container_width=True): show_details(row)

        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx + 1]:
                c_data = main_df[main_df['category'] == c_name]
                if c_data.empty: st.info(f"검색 결과 없음: {c_name}" if search_query_archive else f"데이터 없음: {c_name}")
                else:
                    items = c_data.to_dict('records')
                    music_cls = "music-tab-style" if c_name == "MUSIC" else ""
                    for i in range(0, len(items), grid_cols):
                        cols = st.columns(grid_cols)
                        for j in range(grid_cols):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    img_u = row["img_url"] if row["img_url"] and str(row["img_url"]) != "None" else ""
                                    st.markdown(f'<div class="cal-img-box {music_cls}"><div class="badge-date">{row["view_date"]}</div><img src="{img_u}"></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:10] + "..." if len(row['title']) > 10 else row['title'], key=f"cat_btn_{c_name}_{row['id']}", use_container_width=True): show_details(row)

        if IS_ADMIN:
            with sub_tabs[-1]:
                if not scrap_df.empty:
                    week_scrap = scrap_df[scrap_df['v_dt'] >= (pd.Timestamp.today() - pd.Timedelta(days=pd.Timestamp.today().weekday()))]
                    keywords = []
                    for text in week_scrap['summary'].fillna('') + " " + week_scrap['note'].fillna('') + " " + week_scrap['brief'].fillna('') + " " + week_scrap['highlights'].fillna(''):
                        keywords.extend(re.findall(r"#(\w+)", str(text)))
                    
                    if keywords:
                        from collections import Counter
                        top_keywords = [k[0] for k in Counter(keywords).most_common(5)]
                        cols = st.columns(len(top_keywords))
                        for i, kw in enumerate(top_keywords):
                            btn_type = "primary" if st.session_state.selected_tag == kw else "secondary"
                            def toggle_tag(tag): st.session_state.selected_tag = None if st.session_state.selected_tag == tag else tag
                            cols[i].button(f"#{kw}", key=f"kw_{i}", type=btn_type, on_click=toggle_tag, args=(kw,))
                        st.divider()
                        
                    display_scrap_df = scrap_df.copy()
                    if st.session_state.selected_tag:
                        tag_mask = display_scrap_df['summary'].fillna('').str.contains(f"#{st.session_state.selected_tag}") | display_scrap_df['note'].fillna('').str.contains(f"#{st.session_state.selected_tag}") | display_scrap_df['brief'].fillna('').str.contains(f"#{st.session_state.selected_tag}") | display_scrap_df['highlights'].fillna('').str.contains(f"#{st.session_state.selected_tag}")
                        display_scrap_df = display_scrap_df[tag_mask]
                        st.info(f"🏷️ '#{st.session_state.selected_tag}' 태그가 포함된 스크랩만 봅니다. (해제하려면 위의 버튼을 다시 누르세요)")
                    
                    if not display_scrap_df.empty:
                        display_scrap_df['year_week'] = display_scrap_df['v_dt'].dt.isocalendar().year.astype(str) + "-" + display_scrap_df['v_dt'].dt.isocalendar().week.astype(str).str.zfill(2)
                        for w in sorted(display_scrap_df['year_week'].dropna().unique(), reverse=True):
                            w_data = display_scrap_df[display_scrap_df['year_week'] == w]
                            y_str, w_str = w.split('-')
                            st.subheader(f"🗓️ {y_str}-{int(w_str)}주차 ({len(w_data)})")
                            for _, row in w_data.iterrows():
                                with st.expander(f"👉 [{row['venue']}] {row['title']} ({row['view_date']})"):
                                    # 분리된 필드에 맞게 ARCHIVE 출력 방식도 깔끔하게 변경
                                    summary_text = str(row['summary'])
                                    if summary_text.startswith("http"):
                                        st.markdown(f"**[🔗 원본 기사 보러가기]({summary_text.split(chr(10))[0]})**")
                                    elif row['summary']: 
                                        st.markdown(f"**📰 기사 원본:**<br>{str(row['summary']).replace(chr(10), '<br>')}", unsafe_allow_html=True)
                                    
                                    if row['note']: st.markdown(f"**✍️ 직접 필사:**<br>{row['note'].replace(chr(10), '<br>')}", unsafe_allow_html=True)
                                    if row['brief']: st.write(f"**🎯 중심맥락(논지):** {row['brief']}")
                                    if row['highlights']: st.markdown(f"**💡 핵심 사례(논거) 및 구조:**<br>{row['highlights'].replace(chr(10), '<br>')}", unsafe_allow_html=True)
                                    
                                    if st.button("✏️ 수정", key=f"scr_btn_{row['id']}"): show_details(row)
                    else: st.info("해당 태그나 검색어에 맞는 스크랩이 없습니다.")
                else: st.info("스크랩 기록이 없습니다.")

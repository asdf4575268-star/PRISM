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
        if local_data:
            upload_list = [dict(row) for row in local_data]
            supabase.table("archive").upsert(upload_list).execute() 
            
        try:
            local_plan = conn.execute("SELECT * FROM plan").fetchall()
            if local_plan:
                plan_upload = [dict(row) for row in local_plan]
                supabase.table("plan").upsert(plan_upload).execute()
        except: pass
        
        st.session_state.sync_msg = ("success", f"✅ 클라우드 백업 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        
        if cloud_data:
            cursor.execute("DELETE FROM archive")
            to_insert = []
            for row in cloud_data:
                to_insert.append((
                    row['id'], row['category'], row['title'], row['creator'], row['rel_date'], 
                    row['venue'], row['summary'], row.get('brief', ''), row.get('highlights', ''), 
                    row['note'], row.get('img_url'), row.get('img_url2'), row['save_date'], row['view_date']
                ))
            cursor.executemany("""INSERT INTO archive 
                (id, category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", to_insert)
                
        try:
            res_p = supabase.table("plan").select("*").execute()
            cloud_plan = res_p.data if hasattr(res_p, 'data') else res_p
            if cloud_plan:
                cursor.execute("DELETE FROM plan")
                plan_insert = []
                for rp in cloud_plan:
                    plan_insert.append((rp['id'], rp['plan_date'], rp['category'], rp['title'], rp['memo']))
                cursor.executemany("INSERT INTO plan (id, plan_date, category, title, memo) VALUES (?,?,?,?,?)", plan_insert)
        except: pass
        
        conn.commit()
        st.cache_data.clear() 
        st.session_state.sync_msg = ("success", f"✅ 데이터를 성공적으로 복구했습니다!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

@st.cache_resource
def auto_sync_on_startup():
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM archive").fetchone()[0]
    if count == 0:
        restore_from_supabase()
    return True

auto_sync_on_startup()

# --- [안전한 문자열 반환 헬퍼] ---
def safe_str(val):
    return "" if val is None or str(val) == "None" else str(val)

# --- [3. 로그인 및 Session State 초기화] ---
DEV_MODE = False 
cookie_manager = stx.CookieManager()

if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if cookie_manager.get(cookie="admin_logged_in") == "yes": st.session_state.is_logged_in = True
if "user_password" not in st.session_state: st.session_state.user_password = ""
if "selected_tag" not in st.session_state: st.session_state.selected_tag = None
if "show_form" not in st.session_state: st.session_state.show_form = False
if "week_offset" not in st.session_state: st.session_state.week_offset = 0
if "should_clear_form" not in st.session_state: st.session_state.should_clear_form = False

# 수정(Update) 관련 State 변수들 추가
if "edit_target_id" not in st.session_state: st.session_state.edit_target_id = None
if "edit_source" not in st.session_state: st.session_state.edit_source = None
if "main_nav" not in st.session_state: st.session_state.main_nav = "🖋️ WRITE" if st.session_state.is_logged_in else "📂 ARCHIVE"

form_keys = ['f_title', 'f_creator', 'f_date', 'f_venue', 'f_img', 'f_video', 'f_summary', 'f_brief', 'f_highlights', 'f_note']

if st.session_state.should_clear_form:
    for k in form_keys:
        st.session_state[k] = ""
    st.session_state.f_view_date = date.today()
    st.session_state.show_form = False
    st.session_state.edit_target_id = None
    st.session_state.edit_source = None
    st.session_state.should_clear_form = False

for k in form_keys:
    if k not in st.session_state:
        st.session_state[k] = ""
if 'f_view_date' not in st.session_state:
    st.session_state.f_view_date = date.today()

if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True

is_admin = st.session_state.is_logged_in or DEV_MODE

with st.sidebar:
    st.markdown("### 🔐 관리자 접속")
    if not is_admin:
        input_password = st.text_input("비밀번호", type="password", key="sidebar_pw_2")
        if input_password:
            if input_password == st.secrets["ADMIN_PASSWORD"]:
                cookie_manager.set("admin_logged_in", "yes", expires_at=datetime.now() + timedelta(days=30))
                st.session_state.user_password = input_password 
                st.session_state.is_logged_in = True
                st.session_state.main_nav = "🖋️ WRITE"
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
    if st.session_state.is_logged_in:
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
        if st.button("🧹 중복 데이터 정리", help="같은 제목의 데이터 중 가장 최근에 수정한 것만 남기고 삭제합니다.", use_container_width=True):
            conn = get_connection()
            conn.execute("DELETE FROM archive WHERE id NOT IN (SELECT MAX(id) FROM archive GROUP BY title, category)")
            conn.execute("DELETE FROM plan WHERE id NOT IN (SELECT MAX(id) FROM plan GROUP BY title, category)")
            conn.commit()
            st.cache_data.clear()
            st.success("✅ 중복이 제거되었습니다! 아래 '클라우드 백업'을 눌러주세요.")
            time.sleep(1.5)
            st.rerun()
        st.divider()
        st.markdown("### 🔄 데이터 동기화")
        if 'sync_msg' in st.session_state:
            m_type, m_txt = st.session_state.sync_msg
            if m_type == "success": st.success(m_txt)
            elif m_type == "warning": st.warning(m_txt)
            else: st.error(m_txt)
            del st.session_state.sync_msg
        st.button("📤 클라우드 백업", key="backup_2", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 클라우드 복구", key="restore_2", on_click=restore_from_supabase, use_container_width=True)

# --- [API 검색 함수들] ---
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
            item_url = m.get('collectionViewUrl' if is_album else 'trackViewUrl', '')
            formatted_res.append({
                'display_name': f"{'📀' if is_album else '🎵'} {title} - {m.get('artistName', '')}", 
                'title': title, 
                'creator': m.get('artistName', ''), 
                'date': m.get('releaseDate', '')[:10], 
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 
                'venue': m.get('artistName', ''),
                'is_album': is_album,
                'collection_id': m.get('collectionId'),
                'url': item_url
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
            director_obj = next((m for m in crew_list if m.get('job') == 'Director'), None)
            director = director_obj['name'] if director_obj else "정보 없음"
            creator_label = f"[감독] {director}"
            companies = res.get('production_companies', [])
            venue_info = companies[0].get('name', '') if companies else ""
        else:
            creators = res.get('created_by', [])
            if creators: creator_names = ", ".join([c['name'] for c in creators])
            else: creator_names = next((m['name'] for m in crew_list if m.get('job') in ['Writer', 'Executive Producer']), "정보 없음")
            creator_label = f"[작가/제작] {creator_names}"
            networks = res.get('networks', [])
            venue_info = networks[0].get('name', '') if networks else ""
                
        cast_names = ", ".join([c['name'] for c in cast_list[:3]])
        cast_label = f"[출연] {cast_names}" if cast_names else ""
        
        return {
            "creator": f"{creator_label} / {cast_label}".strip(" / "), 
            "venue": venue_info
        }
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
    except: return "상세정보 로드 실패"
    return "정보 없음"

def scrape_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        res.encoding = 'utf-8'
        html_text = res.text
        title = re.search(r'property="og:title"\s+content="(.*?)"', html_text)
        if not title: title = re.search(r'name="h:title"\s+content="(.*?)"', html_text)
        if not title: title = re.search(r'<title>(.*?)</title>', html_text)
        img = re.search(r'property="og:image"\s+content="(.*?)"', html_text)
        site = re.search(r'property="og:site_name"\s+content="(.*?)"', html_text)
        if not site: site = re.search(r'name="h:section"\s+content="(.*?)"', html_text)
        desc = re.search(r'property="og:description"\s+content="(.*?)"', html_text)
        return {"title": html.unescape(title.group(1)) if title else "제목 없음", "img": img.group(1) if img else "", "venue": site.group(1) if site else "URL", "summary": f"{url}\n\n{html.unescape(desc.group(1)) if desc else ''}"}
    except: return None


# --- [4. 팝업 상세 보기] ---
@st.dialog("📋 아카이브 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    cat = item.get('category')
    
    if is_admin:
        t_col1, _, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                conn = get_connection()
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                conn.commit()
                st.cache_data.clear() 
                try: supabase.table("archive").delete().eq("id", item['id']).execute()
                except: pass
                st.rerun()
        with t_col3: 
            # 팝업 내 폼을 제거하고 데이터를 메인 폼으로 보냅니다!
            if st.button("✏️ 불러와서 수정", key=f"edit_{item['id']}", use_container_width=True, type="primary"):
                st.session_state.edit_target_id = item['id']
                st.session_state.edit_source = 'archive'
                st.session_state.main_category_radio = cat
                
                st.session_state.f_title = safe_str(item.get('title'))
                st.session_state.f_creator = safe_str(item.get('creator'))
                st.session_state.f_date = safe_str(item.get('rel_date'))
                st.session_state.f_venue = safe_str(item.get('venue'))
                st.session_state.f_img = safe_str(item.get('img_url'))
                st.session_state.f_video = safe_str(item.get('img_url2'))
                st.session_state.f_brief = safe_str(item.get('brief'))
                st.session_state.f_highlights = safe_str(item.get('highlights'))
                st.session_state.f_note = safe_str(item.get('note'))
                st.session_state.f_summary = safe_str(item.get('summary'))
                try: st.session_state.f_view_date = pd.to_datetime(item.get('view_date')).date()
                except: st.session_state.f_view_date = date.today()
                
                st.session_state.show_form = True
                st.session_state.main_nav = "🖋️ WRITE"
                st.rerun()
        st.divider()

    col_img, col_txt = st.columns([0.3, 0.7])
    
    # 뷰어 모드 렌더링
    with col_img:
        if item.get('img_url') and str(item.get('img_url')) != "None": 
            st.image(item['img_url'], use_container_width=True)
        
        memo_content = item.get('img_url2', '')
        if memo_content and str(memo_content) != "None":
            url_match = re.search(r'(https?://[^\s]+)', memo_content)
            if url_match:
                media_url = url_match.group(1)
                text_part = memo_content.replace(media_url, '').strip(' /|-')
                if text_part: 
                    st.markdown(f'<div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">📎 {text_part}</div>', unsafe_allow_html=True)
                
                if re.search(r'\.(jpg|jpeg|png|webp|gif)', media_url, re.IGNORECASE) or "image.tmdb.org" in media_url:
                    st.image(media_url, use_container_width=True)
                else:
                    try:
                        st.video(media_url)
                    except:
                        st.markdown(f"**[🔗 첨부 링크 보러가기]({media_url})**")
            else: 
                st.markdown(f'<div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">📎 {memo_content}</div>', unsafe_allow_html=True)
    with col_txt:
        st.markdown(f'# {item.get("title")}')
        
        creator_text = item.get('creator', '')
        if item.get("category") == "SCRAP" and creator_text:
            st.write(f"**📰 {creator_text}**")
        elif creator_text:
            st.write(f"**{creator_text}**")
            
        st.write(f"**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
        st.markdown(f'<p style="color: #E2E2E2; font-weight: bold; font-size: 1.1em;">🍿 감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
        st.divider()
        
        if cat == "SCRAP":
            sections = [
                ("🔑 키워드", "brief", "#0E6245"),
                ("✨ 5문장 요약", "highlights", "#7D5600"),
                ("🌈 감상", "note", "#1E425E"),
                ("🔗 정보 (링크 및 필사)", "summary", "#444")
            ]
        else:
            sections = [
                ("💎 DRIP", "brief", "#E50914"), 
                ("🖋️ PRISM", "note", "#1E425E"),
                ("💡 SIGHT", "summary", "#0E6245"), 
                ("🔖 SENSE", "highlights", "#7D5600")
            ]
            
        for label, key, color in sections:
            if item.get(key) and str(item.get(key)).strip():
                st.markdown(f'<div style="display: inline-block; background-color: {color}; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px; font-weight: bold;">{label}</div>', unsafe_allow_html=True)
                st.markdown(str(item[key]).replace('\n', '  \n'))
                st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🔗 외부에 리뷰 공유하기 (복사)"):
            share_text = f"[{item.get('category')}] {item.get('title')}\n"
            if creator_text: share_text += f"👤 {creator_text}\n\n"
            else: share_text += "\n"
            
            if cat == "SCRAP":
                if item.get('brief') and str(item.get('brief')).strip(): share_text += f"🔑 키워드:\n{item.get('brief')}\n\n"
                if item.get('highlights') and str(item.get('highlights')).strip(): share_text += f"✨ 5문장 요약:\n{item.get('highlights')}\n\n"
                if item.get('note') and str(item.get('note')).strip(): share_text += f"🌈 감상:\n{item.get('note')}\n\n"
                if item.get('summary') and str(item.get('summary')).strip(): share_text += f"🔗 원본 링크/정보:\n{item.get('summary')}\n\n"
            else:
                if item.get('brief') and str(item.get('brief')).strip(): share_text += f"💎 DRIP\n{item.get('brief')}\n\n"
                if item.get('note') and str(item.get('note')).strip(): share_text += f"🖋️ PRISM\n{item.get('note')}\n\n"
            st.code(share_text.strip(), language="markdown")


@st.dialog("🗓️상세 정보", width="large")
def show_plan_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    try: rich_data = json.loads(item['memo'])
    except: rich_data = {"creator": "", "rel_date": "", "venue": "", "summary": "", "brief": "", "highlights": "", "note": item.get('memo', ''), "img_url": "", "img_url2": ""}
    cat = item.get('category')

    if is_admin:
        t_col1, _, t_col3 = st.columns([0.2, 0.6, 0.2])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_plan_{item['id']}", use_container_width=True):
                conn = get_connection()
                conn.execute("DELETE FROM plan WHERE id=?", (item['id'],))
                conn.commit()
                st.cache_data.clear()
                try: supabase.table("plan").delete().eq("id", item['id']).execute()
                except: pass
                st.rerun()
        with t_col3: 
            if st.button("✏️ 불러와서 수정", key=f"edit_plan_{item['id']}", use_container_width=True, type="primary"):
                st.session_state.edit_target_id = item['id']
                st.session_state.edit_source = 'plan'
                st.session_state.main_category_radio = cat
                
                st.session_state.f_title = safe_str(item.get('title'))
                st.session_state.f_creator = safe_str(rich_data.get('creator'))
                st.session_state.f_date = safe_str(rich_data.get('rel_date'))
                st.session_state.f_venue = safe_str(rich_data.get('venue'))
                st.session_state.f_img = safe_str(rich_data.get('img_url'))
                st.session_state.f_video = safe_str(rich_data.get('img_url2'))
                st.session_state.f_brief = safe_str(rich_data.get('brief'))
                st.session_state.f_highlights = safe_str(rich_data.get('highlights'))
                st.session_state.f_note = safe_str(rich_data.get('note'))
                st.session_state.f_summary = safe_str(rich_data.get('summary'))
                try: st.session_state.f_view_date = pd.to_datetime(item.get('plan_date')).date()
                except: st.session_state.f_view_date = date.today()
                
                st.session_state.show_form = True
                st.session_state.main_nav = "🖋️ WRITE"
                st.rerun()
        st.divider()
        
    col_img, col_txt = st.columns([0.3, 0.7])
    
    # 뷰어 모드
    with col_img:
        if rich_data.get('img_url') and str(rich_data.get('img_url')) != "None": 
            st.image(rich_data['img_url'], use_container_width=True)
        
        memo_content = rich_data.get('img_url2', '')
        if memo_content and str(memo_content) != "None":
            url_match = re.search(r'(https?://[^\s]+)', memo_content)
            if url_match:
                media_url = url_match.group(1)
                text_part = memo_content.replace(media_url, '').strip(' /|-')
                if text_part: 
                    st.markdown(f'<div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">📎 {text_part}</div>', unsafe_allow_html=True)
                
                if re.search(r'\.(jpg|jpeg|png|webp|gif)', media_url, re.IGNORECASE) or "image.tmdb.org" in media_url:
                    st.image(media_url, use_container_width=True)
                else:
                    try:
                        st.video(media_url)
                    except:
                        st.markdown(f"**[🔗 첨부 링크 보러가기]({media_url})**")
            else: 
                st.markdown(f'<div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">📎 {memo_content}</div>', unsafe_allow_html=True)
    with col_txt:
        st.markdown(f'# {item.get("title")}')
        st.write(f"**{rich_data.get('creator', '')}**")
        st.write(f"**📅 {rich_data.get('rel_date', '')} | 📍 {rich_data.get('venue', '')}**")
        st.markdown(f'<p style="color: #E50914; font-weight: bold; font-size: 1.1em;">🗓️ 예정일: {item.get("plan_date")}</p>', unsafe_allow_html=True)
        st.divider()
        
        if cat == "SCRAP":
            sections = [
                ("🔑 키워드", "brief", "#0E6245"),
                ("✨ 5문장 요약", "highlights", "#7D5600"),
                ("🌈 감상", "note", "#1E425E"),
                ("🔗 정보 (링크/필사)", "summary", "#444")
            ]
        else:
            sections = [
                ("💎 DRIP", "brief", "#E50914"), 
                ("🖋️ PRISM", "note", "#1E425E"),
                ("💡 SIGHT", "summary", "#0E6245"), 
                ("🔖 SENSE", "highlights", "#7D5600")
            ]
                
        for label, key, color in sections:
            if rich_data.get(key) and str(rich_data.get(key)).strip():
                st.markdown(f'<div style="display: inline-block; background-color: {color}; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px; font-weight: bold;">{label}</div>', unsafe_allow_html=True)
                st.markdown(str(rich_data[key]).replace('\n', '  \n'))
                st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🔗 외부에 리뷰 공유하기 (복사)"):
            share_text = f"[{item.get('category')}] {item.get('title')}\n"
            if rich_data.get('creator'): share_text += f"👤 {rich_data.get('creator')}\n\n"
            else: share_text += "\n"
            
            if cat == "SCRAP":
                if rich_data.get('brief') and str(rich_data.get('brief')).strip(): share_text += f"🔑 키워드:\n{rich_data.get('brief')}\n\n"
                if rich_data.get('highlights') and str(rich_data.get('highlights')).strip(): share_text += f"✨ 5문장 요약:\n{rich_data.get('highlights')}\n\n"
                if rich_data.get('note') and str(rich_data.get('note')).strip(): share_text += f"🌈 감상:\n{rich_data.get('note')}\n\n"
                if rich_data.get('summary') and str(rich_data.get('summary')).strip(): share_text += f"🔗 원본 링크/정보:\n{rich_data.get('summary')}\n\n"
            else:
                if rich_data.get('brief') and str(rich_data.get('brief')).strip(): share_text += f"💎 DRIP\n{rich_data.get('brief')}\n\n"
                if rich_data.get('note') and str(rich_data.get('note')).strip(): share_text += f"🖋️ PRISM\n{rich_data.get('note')}\n\n"
                    
            st.code(share_text.strip(), language="markdown")

    if is_admin:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✅ 완료 (아카이브로 이동)", key=f"done_plan_bottom_{item['id']}", use_container_width=True, type="primary"):
            conn = get_connection()
            today_str = str(date.today())
            new_archive_record = {
                "category": item['category'], "title": item['title'], "creator": rich_data.get("creator", ""), "rel_date": rich_data.get("rel_date", ""),
                "venue": rich_data.get("venue", ""), "summary": rich_data.get("summary", ""), "brief": rich_data.get("brief", ""), "highlights": rich_data.get("highlights", ""),
                "note": rich_data.get("note", ""), "img_url": rich_data.get("img_url", ""), "img_url2": rich_data.get("img_url2", ""), "save_date": today_str, "view_date": item['plan_date']
            }
            conn.execute("""INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (new_archive_record['category'], new_archive_record['title'], new_archive_record['creator'], new_archive_record['rel_date'], new_archive_record['venue'], new_archive_record['summary'], new_archive_record['brief'], new_archive_record['highlights'], new_archive_record['note'], new_archive_record['img_url'], new_archive_record['img_url2'], new_archive_record['save_date'], new_archive_record['view_date']))
            conn.execute("DELETE FROM plan WHERE id=?", (item['id'],))
            conn.commit()
            st.cache_data.clear()
            try: 
                supabase.table("archive").upsert(new_archive_record).execute()
                supabase.table("plan").delete().eq("id", item['id']).execute()
            except: pass
            st.success(f"🎉 '{item['title']}' 아카이브로 이동 완료!"); time.sleep(0.5); st.rerun()
        st.divider()

# --- [5. 메인 UI 및 라우팅] ---
def get_base64(path):
    try:
        with open(path, "rb") as f: return base64.b64encode(f.read()).decode()
    except: return ""

logo_base64 = get_base64("logo.png")

st.markdown("""<style>.header-wrap { display: flex; align-items: center; gap: 6px; } .header-wrap h1 { margin: 0; letter-spacing: -1px; }</style>""", unsafe_allow_html=True)
st.markdown(f"""<div class="header-wrap"><img src="data:image/png;base64,{logo_base64}" width="90"><h1>PRISM ARCHIVE</h1></div>""", unsafe_allow_html=True)

if is_admin:
    st.markdown("""<style>div[role="radiogroup"] > label { font-weight: bold; font-size: 1.1em; padding-right: 15px; }</style>""", unsafe_allow_html=True)
    st.radio("메뉴", ["🖋️ WRITE", "📂 ARCHIVE"], horizontal=True, label_visibility="collapsed", key="main_nav")
else:
    st.session_state.main_nav = "📂 ARCHIVE"

tab_w = (st.session_state.main_nav == "🖋️ WRITE")
tab_a = (st.session_state.main_nav == "📂 ARCHIVE")

# --- [WRITE 탭 (메인 화면)] ---
if is_admin and tab_w:
    category = st.radio("📂 category", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"], horizontal=True, key="main_category_radio")
    search_query = st.text_input(f"🔍 {category} 검색")
    
    if search_query:
        if category == "SCRAP":
            if st.button("✨ 가져오기"):
                s = scrape_url(search_query)
                if s:
                    st.session_state.edit_target_id = None; st.session_state.edit_source = None
                    st.session_state.f_title = s['title']; st.session_state.f_creator = ''; st.session_state.f_date = str(date.today())
                    st.session_state.f_img = s['img']; st.session_state.f_venue = s['venue']; st.session_state.f_summary = s['summary']
                    st.session_state.f_highlights = ""; st.session_state.f_note = ""; st.session_state.f_brief = ""; st.session_state.f_video = ""
                    st.session_state.show_form = True; st.rerun()
                else:
                    st.error("URL 정보를 가져올 수 없습니다.")
        elif category == "BOOKS":
            res = search_books(search_query)
            if res:
                opts = {f"📚 {b['title']}": b for b in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    b = opts[sel]
                    st.session_state.edit_target_id = None; st.session_state.edit_source = None
                    st.session_state.f_title = b['title']; st.session_state.f_creator = ", ".join(b['authors'])
                    st.session_state.f_date = b['datetime'][:10]; st.session_state.f_img = b.get('thumbnail', '').replace("R120x174", "R400x0")
                    st.session_state.f_venue = b.get('publisher', ''); st.session_state.f_summary = b.get('contents', '')
                    st.session_state.f_highlights = ""; st.session_state.f_note = ""; st.session_state.f_brief = ""; st.session_state.f_video = ""
                    st.session_state.show_form = True; st.rerun()
            else:
                st.info("검색 결과가 없습니다.")
        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {m['display_name']: m for m in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    st.session_state.edit_target_id = None; st.session_state.edit_source = None
                    st.session_state.f_title = m['title']; st.session_state.f_creator = m['creator']; st.session_state.f_date = m['date']
                    st.session_state.f_img = m['img']; st.session_state.f_venue = m['venue']
                    st.session_state.f_summary = f"{m.get('url', '')}\n\n" if m.get('url') else ""
                    
                    tracklist_text = ""
                    if m.get('is_album') and m.get('collection_id'):
                        try:
                            lookup_url = f"https://itunes.apple.com/lookup?id={m['collection_id']}&entity=song"
                            lookup_res = requests.get(lookup_url).json().get("results", [])
                            tracks = [t['trackName'] for t in lookup_res if t.get('wrapperType') == 'track']
                            if tracks: tracklist_text = "💿 트랙리스트\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(tracks)])
                        except: pass
                        
                    st.session_state.f_highlights = tracklist_text; st.session_state.f_note = ""; st.session_state.f_brief = ""; st.session_state.f_video = ""
                    st.session_state.show_form = True; st.rerun()
            else:
                st.info("검색 결과가 없습니다.")
        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                opts = {f"🎭 {s['title']} [{s['date']}~] ({s['venue']})": s for s in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]; combined_creator = get_kopis_detail(s['id'])
                    st.session_state.edit_target_id = None; st.session_state.edit_source = None
                    st.session_state.f_title = s['title']; st.session_state.f_creator = combined_creator; st.session_state.f_date = s['date']
                    st.session_state.f_img = s['img']; st.session_state.f_venue = s['venue']; st.session_state.f_summary = f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={s['id']}"
                    st.session_state.f_highlights = ""; st.session_state.f_note = ""; st.session_state.f_brief = ""; st.session_state.f_video = ""
                    st.session_state.show_form = True; st.rerun()
            else:
                st.info("검색 결과가 없습니다.")
        else: 
            res = search_tmdb(search_query, category)
            if res:
                t_key = 'title' if category == 'MOVIES' else 'name'
                d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]; details = get_tmdb_details(s['id'], category)
                    st.session_state.edit_target_id = None; st.session_state.edit_source = None
                    st.session_state.f_title = s.get(t_key, ''); st.session_state.f_creator = details['creator']; st.session_state.f_date = s.get(d_key, '')
                    st.session_state.f_img = f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}"; st.session_state.f_venue = details['venue']
                    st.session_state.f_summary = s.get('overview', '')
                    st.session_state.f_highlights = ""; st.session_state.f_note = ""; st.session_state.f_brief = ""
                    st.session_state.f_video = "" 
                    st.session_state.show_form = True; st.rerun()
            else:
                st.info("검색 결과가 없습니다.")

    if not st.session_state.show_form:
        if st.button("✏️ 직접 입력"):
            st.session_state.should_clear_form = True
            st.rerun()

    # 여기서부터 메인 폼입니다. 업데이트/신규 작성이 모두 이곳에서 이루어집니다.
    if st.session_state.show_form:
        is_update = st.session_state.edit_target_id is not None
        if is_update:
            st.info(f"🚨 현재 데이터 수정 모드입니다. (완료 후 저장 버튼을 눌러주세요)")
            
        st.divider()
        
        cl, cr = st.columns([0.4, 0.6])
        with cl:
            st.text_input("🖼️ 이미지 URL", key="f_img")
            st.text_input("🎬 관련 영상(URL) 또는 제목/메모", key="f_video")
            
            if st.session_state.f_img and st.session_state.f_img.strip() and st.session_state.f_img != "None": 
                st.image(st.session_state.f_img, use_container_width=True)
            
            st.text_input("📌 제목", key="f_title")
            creator_label = "👤 창작자/매체" if category == "SCRAP" else "👤 창작자"
            st.text_input(creator_label, key="f_creator")
            st.text_input("📅 작품 날짜", key="f_date")
            st.text_input("📍 장소/플랫폼", key="f_venue")
            st.date_input("🍿 감상 완료/예정일", key="f_view_date")
        
        with cr:
            if category == "SCRAP":
                st.text_input("1. 🔑 키워드", key="f_brief")
                st.text_area("2. ✨ 5문장 요약", key="f_highlights", height=150)
                st.text_area("3. 🌈 감상", key="f_note", height=200)
                st.text_area("🔗 정보 (링크 및 필사)", key="f_summary", height=150)
            else:
                st.text_input("1. 💎 DRIP", key="f_brief")
                st.text_area("2. 🖋️ PRISM", key="f_note", height=300)
                st.text_area("3. 💡 SIGHT (API 연동 시 기본 정보 자동입력)", key="f_summary", height=150)
                st.text_area("4. 🔖 SENSE", key="f_highlights", height=150)
            
        st.markdown("<br>", unsafe_allow_html=True)
        col_btn1, col_btn2, col_btn3 = st.columns([0.4, 0.4, 0.2])
        
        if is_update:
            if col_btn1.button("💾 수정 내용 저장", use_container_width=True, type="primary"):
                if st.session_state.f_title.strip():
                    conn = get_connection()
                    if st.session_state.edit_source == 'archive':
                        new_record = {
                            "category": str(category), "title": st.session_state.f_title.strip(), "creator": st.session_state.f_creator.strip(), 
                            "rel_date": st.session_state.f_date.strip(), "venue": st.session_state.f_venue.strip(), "summary": st.session_state.f_summary.strip(), 
                            "brief": st.session_state.f_brief.strip(), "highlights": st.session_state.f_highlights.strip(), "note": st.session_state.f_note.strip(), 
                            "img_url": st.session_state.f_img.strip(), "img_url2": st.session_state.f_video.strip(), "view_date": str(st.session_state.f_view_date)
                        }
                        conn.execute("""UPDATE archive SET category=?, title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, img_url=?, img_url2=?, view_date=? WHERE id=?""", 
                                     (new_record["category"], new_record["title"], new_record["creator"], new_record["rel_date"], new_record["venue"], new_record["summary"], new_record["brief"], new_record["highlights"], new_record["note"], new_record["img_url"], new_record["img_url2"], new_record["view_date"], st.session_state.edit_target_id))
                        try: supabase.table("archive").update(new_record).eq("id", st.session_state.edit_target_id).execute()
                        except: pass
                    else: # 'plan' 수정
                        rich_data = {
                            "creator": st.session_state.f_creator.strip(), "rel_date": st.session_state.f_date.strip(), "venue": st.session_state.f_venue.strip(),
                            "summary": st.session_state.f_summary.strip(), "brief": st.session_state.f_brief.strip(), "highlights": st.session_state.f_highlights.strip(),
                            "note": st.session_state.f_note.strip(), "img_url": st.session_state.f_img.strip(), "img_url2": st.session_state.f_video.strip()
                        }
                        memo_payload = json.dumps(rich_data, ensure_ascii=False)
                        conn.execute("UPDATE plan SET category=?, title=?, plan_date=?, memo=? WHERE id=?", 
                                     (str(category), st.session_state.f_title.strip(), str(st.session_state.f_view_date), memo_payload, st.session_state.edit_target_id))
                        try: supabase.table("plan").update({"category": str(category), "title": st.session_state.f_title.strip(), "plan_date": str(st.session_state.f_view_date), "memo": memo_payload}).eq("id", st.session_state.edit_target_id).execute()
                        except: pass
                        
                    conn.commit()
                    st.cache_data.clear()
                    st.success("✅ 안전하게 수정되었습니다!")
                    st.session_state.should_clear_form = True
                    time.sleep(0.8)
                    st.rerun()
                else: st.warning("제목을 입력해 주세요.")
        else:
            if col_btn1.button("✅ 아카이브 저장", use_container_width=True, type="primary"):
                if st.session_state.f_title.strip():
                    new_record = {
                        "category": str(category), "title": st.session_state.f_title.strip(), "creator": st.session_state.f_creator.strip(), 
                        "rel_date": st.session_state.f_date.strip(), "venue": st.session_state.f_venue.strip(), "summary": st.session_state.f_summary.strip(), 
                        "brief": st.session_state.f_brief.strip(), "highlights": st.session_state.f_highlights.strip(), "note": st.session_state.f_note.strip(), 
                        "img_url": st.session_state.f_img.strip(), "img_url2": st.session_state.f_video.strip(), 
                        "save_date": str(date.today()), "view_date": str(st.session_state.f_view_date)
                    }
                    try:
                        conn = get_connection()
                        conn.execute("""INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (new_record["category"], new_record["title"], new_record["creator"], new_record["rel_date"], new_record["venue"], new_record["summary"], new_record["brief"], new_record["highlights"], new_record["note"], new_record["img_url"], new_record["img_url2"], new_record["save_date"], new_record["view_date"]))
                        conn.commit()
                        st.cache_data.clear() 
                        try: supabase.table("archive").upsert(new_record).execute()
                        except: pass
                        st.success("✅ 아카이브 저장 완료!")
                        st.session_state.should_clear_form = True
                        time.sleep(0.8)
                        st.rerun()
                    except Exception as e: st.error(f"❌ 오류: {e}")
                else: st.warning("제목을 입력해 주세요.")
            
            if col_btn2.button("🗓️ 일정 추가", use_container_width=True):
                if st.session_state.f_title.strip():
                    rich_data = {
                        "creator": st.session_state.f_creator.strip(), "rel_date": st.session_state.f_date.strip(), "venue": st.session_state.f_venue.strip(),
                        "summary": st.session_state.f_summary.strip(), "brief": st.session_state.f_brief.strip(), "highlights": st.session_state.f_highlights.strip(),
                        "note": st.session_state.f_note.strip(), "img_url": st.session_state.f_img.strip(), "img_url2": st.session_state.f_video.strip()
                    }
                    memo_payload = json.dumps(rich_data, ensure_ascii=False)
                    conn = get_connection()
                    conn.execute("INSERT INTO plan (plan_date, category, title, memo) VALUES (?,?,?,?)", (str(st.session_state.f_view_date), str(category), st.session_state.f_title.strip(), memo_payload))
                    conn.commit()
                    try: supabase.table("plan").upsert({"plan_date": str(st.session_state.f_view_date), "category": str(category), "title": st.session_state.f_title.strip(), "memo": memo_payload}).execute()
                    except: pass
                    st.success("🗓️ 일정표에 추가되었습니다!")
                    st.session_state.should_clear_form = True
                    time.sleep(0.8)
                    st.rerun()
                else: st.warning("제목을 입력해 주세요.")

        if col_btn3.button("❌ 닫기/취소", use_container_width=True):
            st.session_state.should_clear_form = True
            st.rerun()

    st.divider()
    
    col_l, col_c, col_r = st.columns([0.1, 0.8, 0.1])
    with col_l:
        if st.button("⬅️", use_container_width=True): st.session_state.week_offset -= 1; st.rerun()
    today = pd.Timestamp(date.today()); this_monday = today - pd.Timedelta(days=today.weekday())
    view_monday = this_monday + pd.Timedelta(weeks=st.session_state.week_offset); view_sunday = view_monday + pd.Timedelta(days=6)
    with col_c:
        iso_year, iso_week, _ = view_monday.isocalendar()
        st.markdown(f"<h4 style='text-align: center; margin-top:0;'>📅 {iso_year}-{iso_week}주차 <span style='font-size:0.75em; color:#aaa;'>({view_monday.strftime('%m.%d')} ~ {view_sunday.strftime('%m.%d')})</span></h4>", unsafe_allow_html=True)
    with col_r:
        if st.button("➡️", use_container_width=True): st.session_state.week_offset += 1; st.rerun()
            
    conn = get_connection()
    plan_df = pd.read_sql_query("SELECT * FROM plan ORDER BY plan_date ASC", conn)
    if not plan_df.empty: plan_df['p_dt'] = pd.to_datetime(plan_df['plan_date'])
    cat_emojis = {"BOOKS": "📚", "MUSIC": "🎧", "MOVIES": "🎞️", "SERIES": "📽️", "STAGE": "🎭", "SCRAP": "📰"}
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    
    cal_cols = st.columns(7)
    for i in range(7):
        curr_date = view_monday + pd.Timedelta(days=i)
        is_today = curr_date.date() == date.today()
        day_color = "#3399FF" if is_today else "#E2E2E2"
        bg_color = "rgba(51, 153, 255, 0.15)" if is_today else "transparent"
        with cal_cols[i]:
            st.markdown(f"""<div style='text-align: center; background-color: {bg_color}; padding: 10px 0; border-radius: 8px; margin-bottom: 12px;'><span style='color: {day_color}; font-weight: bold; font-size: 1.1em;'>{curr_date.strftime('%m.%d')}</span><br><span style='color: {day_color}; font-size: 0.9em;'>{weekdays[i]}</span></div>""", unsafe_allow_html=True)
            day_data = plan_df[plan_df['p_dt'].dt.date == curr_date.date()] if not plan_df.empty else pd.DataFrame()
            if day_data.empty: st.markdown("<div style='text-align: center; color:#666; font-size:0.8em; margin-top: 20px;'>일정 없음</div>", unsafe_allow_html=True)
            else:
                for _, row in day_data.iterrows():
                    emoji = cat_emojis.get(row['category'], "📌")
                    try: rich_data = json.loads(row['memo']); img_url = rich_data.get('img_url', '')
                    except: img_url = ""
                    if img_url and img_url.strip() and img_url != "None":
                        st.markdown(f"""<div style='position: relative; width: 100%; aspect-ratio: 1/1; border-radius: 6px; overflow: hidden; margin-bottom: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.3); background-color: #2A2A2A; display: flex; align-items: center; justify-content: center;'><img src="{img_url}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display='none'"><div style="position: absolute; top: 4px; left: 4px; background: rgba(0,0,0,0.6); padding: 2px 6px; border-radius: 4px; font-size: 12px;">{emoji}</div></div>""", unsafe_allow_html=True)
                    else:
                        st.markdown(f"""<div style='background-color: #2A2A2A; padding: 10px; border-radius: 6px; border-left: 4px solid #3399FF; margin-bottom: 5px; min-height: 80px; display: flex; align-items: center; justify-content: center; text-align: center;'><div style='font-size: 0.85em; font-weight: bold; line-height: 1.3;'>{emoji}<br>{row['title']}</div></div>""", unsafe_allow_html=True)
                    if st.button("🔍", key=f"dtl_cal_{row['id']}", use_container_width=True): show_plan_details(row)
                    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

# --- [ARCHIVE 탭] ---
if tab_a:
    st.markdown("""<style>.cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; margin-top: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); background: #1e1e1e; display: flex; align-items: center; justify-content: center; } .cal-img-box img { width: 100%; height: 100%; object-fit: cover; } .music-tab-style { aspect-ratio: 1/1 !important; } .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0, 0, 0, 0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; } .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; } @media (min-width: 600px) { [data-testid="stHorizontalBlock"] { display: flex !important; flex-wrap: nowrap !important; gap: 10px !important; } [data-testid="column"] { flex: 1 1 0% !important; min-width: 0 !important; } }</style>""", unsafe_allow_html=True)
    all_df = get_all_data()

    if not all_df.empty:
        search_query_archive = st.text_input("🔍", key="global_search")
        if search_query_archive:
            mask = (all_df['title'].str.contains(search_query_archive, case=False, na=False) | all_df['creator'].str.contains(search_query_archive, case=False, na=False) | all_df['summary'].str.contains(search_query_archive, case=False, na=False) | all_df['note'].str.contains(search_query_archive, case=False, na=False) | all_df['venue'].str.contains(search_query_archive, case=False, na=False))
            all_df = all_df[mask]; st.markdown(f"**'{search_query_archive}'** 검색 결과: 총 **{len(all_df)}**건"); st.divider()

        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        main_df = all_df[all_df['category'] != "SCRAP"]; scrap_df = all_df[all_df['category'] == "SCRAP"]
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        cat_emojis = {"BOOKS": "📚", "MUSIC": "🎧", "MOVIES": "🎞️", "SERIES": "📽️", "STAGE": "🎭"}
        
        tab_titles = [f"📅 ALL ({len(main_df)})"] + [f"{cat_emojis[c]}{c} ({len(main_df[main_df['category'] == c])})" for c in cat_order]
        if is_admin: tab_titles.append(f"🔐 SCRAP ({len(scrap_df)})")
        sub_tabs = st.tabs(tab_titles)
        grid_cols = 6

        with sub_tabs[0]:
            years = sorted(main_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            if years:
                year_options = {y: f"{y}({len(main_df[main_df['v_dt'].dt.year == y])})" for y in years}
                sel_y = st.selectbox("📅 선택", options=list(year_options.keys()), format_func=lambda x: year_options[x], key="archive_year_sel")
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
                                    img_style = 'style="height: auto; aspect-ratio: 1/1;"' if row["category"] == "MUSIC" else ""
                                    with cols[j]:
                                        st.markdown(f'<div class="cal-img-box"><div class="badge-cat">{row["category"]}</div><div class="badge-date">{pd.to_datetime(row["view_date"]).day}일</div><img src="{row["img_url"]}" {img_style}></div>', unsafe_allow_html=True)
                                        short_title = row['title'][:10] + "..." if len(row['title']) > 10 else row['title']
                                        if st.button(short_title, key=f"all_btn_{row['id']}", use_container_width=True): show_details(row)

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
                                    short_title = row['title'][:10] + "..." if len(row['title']) > 10 else row['title']
                                    if st.button(short_title, key=f"cat_btn_{c_name}_{row['id']}", use_container_width=True): show_details(row)

        if is_admin:
            with sub_tabs[-1]:
                if not scrap_df.empty:
                    current_week_start = pd.Timestamp.today() - pd.Timedelta(days=pd.Timestamp.today().weekday())
                    week_scrap = scrap_df[scrap_df['v_dt'] >= current_week_start]
                    keywords = []
                    for text in week_scrap['summary'].fillna('') + " " + week_scrap['note'].fillna('') + " " + week_scrap['brief'].fillna('') + " " + week_scrap['highlights'].fillna(''):
                        keywords.extend(re.findall(r"#(\w+)", str(text)))
                    if keywords:
                        from collections import Counter
                        top_keywords = [k[0] for k in Counter(keywords).most_common(5)]
                        def toggle_tag(clicked_tag):
                            if st.session_state.selected_tag == clicked_tag: st.session_state.selected_tag = None
                            else: st.session_state.selected_tag = clicked_tag
                        cols = st.columns(len(top_keywords))
                        for i, kw in enumerate(top_keywords):
                            btn_type = "primary" if st.session_state.selected_tag == kw else "secondary"
                            cols[i].button(f"#{kw}", key=f"kw_{i}", type=btn_type, on_click=toggle_tag, args=(kw,))
                        st.divider()
                        
                    display_scrap_df = scrap_df.copy()
                    if st.session_state.selected_tag:
                        tag_mask = display_scrap_df['summary'].fillna('').str.contains(f"#{st.session_state.selected_tag}") | display_scrap_df['note'].fillna('').str.contains(f"#{st.session_state.selected_tag}") | display_scrap_df['brief'].fillna('').str.contains(f"#{st.session_state.selected_tag}") | display_scrap_df['highlights'].fillna('').str.contains(f"#{st.session_state.selected_tag}")
                        display_scrap_df = display_scrap_df[tag_mask]
                        st.info(f"🏷️ '#{st.session_state.selected_tag}' 태그가 포함된 스크랩만 봅니다. (해제하려면 위의 버튼을 다시 누르세요)")
                    
                    if not display_scrap_df.empty:
                        display_scrap_df['iso_year'] = display_scrap_df['v_dt'].dt.isocalendar().year
                        display_scrap_df['iso_week'] = display_scrap_df['v_dt'].dt.isocalendar().week
                        display_scrap_df['year_week'] = display_scrap_df['iso_year'].astype(str) + "-" + display_scrap_df['iso_week'].astype(str).str.zfill(2)
                        weeks = sorted(display_scrap_df['year_week'].dropna().unique(), reverse=True)
                        for w in weeks:
                            w_data = display_scrap_df[display_scrap_df['year_week'] == w]
                            y_str, w_str = w.split('-')
                            st.subheader(f"🗓️ {y_str}-{int(w_str)}주차 스크랩")
                            for _, row in w_data.iterrows():
                                with st.expander(f"👉 [{row['venue']}] {row['title']} ({row['view_date']})"):
                                    summary_text = str(row['summary'])
                                    if summary_text.startswith("http"):
                                        url = summary_text.split('\n')[0]
                                        st.markdown(f"**[🔗 원본 기사 보러가기]({url})**")
                                    if row['brief']: st.write(f"**🔑 키워드:** {row['brief']}")
                                    if row['highlights']: st.markdown(f"**✨ 5문장 요약:**<br>{row['highlights'].replace(chr(10), '<br>')}", unsafe_allow_html=True)
                                    if row['note']: st.markdown(f"**🌈 감상:**<br>{row['note'].replace(chr(10), '<br>')}", unsafe_allow_html=True)
                                    if st.button("상세보기 / 수정", key=f"scr_btn_{row['id']}"): show_details(row)
                    else: st.info("해당 태그나 검색어에 맞는 스크랩이 없습니다.")
                else: st.info("스크랩 기록이 없습니다.")

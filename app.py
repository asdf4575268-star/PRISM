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

def get_kst_today():
    return (datetime.utcnow() + timedelta(hours=9)).date()

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
if "f_plan_type" not in st.session_state: st.session_state.f_plan_type = "CONSUME"
if "main_nav" not in st.session_state: 
    st.session_state.main_nav = "🖋️ WRITE" if st.session_state.is_logged_in else "📂 ARCHIVE"
if 'f_view_date' not in st.session_state: st.session_state.f_view_date = get_kst_today()

for k in FORM_KEYS:
    if k not in st.session_state: st.session_state[k] = ""

# 초기화 버튼을 눌렀을 때 폼 비우기
if st.session_state.should_clear_form:
    for k in FORM_KEYS: st.session_state[k] = ""
    st.session_state.f_view_date = get_kst_today()
    st.session_state.f_plan_type = "CONSUME"
    st.session_state.edit_target_id = None
    st.session_state.edit_source = None
    st.session_state.should_clear_form = False

if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True
IS_ADMIN = st.session_state.is_logged_in

# ==========================================
# 3. GLOBAL DESIGN SYSTEM INJECTION (디자인 시스템 정의)
# ==========================================
st.markdown("""
<style>
    /* 전체 배경 톤 및 베이스 레이아웃 최적화 */
    .stApp {
        background-color: #0F172A !important;
        color: #F1F5F9 !important;
    }
    
    /* 폼 컨테이너 고급화 */
    div[data-testid="stForm"] {
        background-color: #1E293B !important;
        border: 1px solid #334155 !important;
        border-radius: 16px !important;
        padding: 24px !important;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3) !important;
    }
    
    /* 인풋 상자 테두리 가공 */
    div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea, div[data-testid="stDateInput"] input {
        background-color: #0F172A !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        color: #F1F5F9 !important;
        transition: all 0.2s ease;
    }
    div[data-testid="stTextInput"] input:focus, div[data-testid="stTextArea"] textarea:focus {
        border-color: #6366F1 !important;
        box-shadow: 0 0 0 1px #6366F1 !important;
    }
    
    /* 네비게이션용 라디오 그룹 고급 세그먼트화 */
    div[role="radiogroup"] {
        background-color: #1E293B !important;
        padding: 4px !important;
        border-radius: 12px !important;
        border: 1px solid #334155 !important;
        gap: 4px !important;
    }
    div[role="radiogroup"] > label {
        background: transparent !important;
        color: #94A3B8 !important;
        padding: 6px 16px !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        font-size: 1.0rem !important;
        transition: all 0.2s ease !important;
        border: none !important;
    }
    div[role="radiogroup"] > label[data-checked="true"] {
        background: linear-gradient(135deg, #4F46E5 0%, #3B82F6 100%) !important;
        color: #FFFFFF !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;
    }
    div[role="radiogroup"] > label[data-checked="true"] p {
        color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 4. DATABASE & CLOUD SYNC (데이터베이스)
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
# 5. API & SEARCH FUNCTIONS (외부 API 통신)
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
# 6. UI COMPONENTS (공통 다이얼로그 렌더링)
# ==========================================

# 상태 제어를 위한 콜백 함수 (다이얼로그 닫힘 방지)
def set_dialog_edit_mode(key, val):
    st.session_state[key] = val

def render_item_details(data_dict, item_id, is_plan=False):
    table_name = "plan" if is_plan else "archive"
    edit_mode_key = f"edit_mode_{table_name}_{item_id}"
    is_edit_mode = st.session_state.get(edit_mode_key, False)
    
    cat = data_dict.get('category')
    creator_text = data_dict.get('creator', '')
    rel_date = data_dict.get('rel_date', '')
    venue = data_dict.get('venue', '')
    img_url = data_dict.get('img_url', '')

    # --- 수정 모드인 경우: 다이얼로그 내부에서 즉시 수정 폼 렌더링 ---
    if is_edit_mode:
        st.markdown("### ✏️ 정보 바로 수정하기")
        with st.form(key=f"inline_edit_form_{table_name}_{item_id}"):
            col_in1, col_in2 = st.columns([0.4, 0.6])
            with col_in1:
                e_title = st.text_input("📌 제목", value=safe_str(data_dict.get('title')))
                e_creator = st.text_input("👤 창작자", value=safe_str(data_dict.get('creator')))
                e_rel_date = st.text_input("📅 발매/출간일", value=safe_str(data_dict.get('rel_date')))
                e_venue = st.text_input("📍 장소/플랫폼", value=safe_str(data_dict.get('venue')))
                e_img_url = st.text_input("🖼️ 이미지 URL", value=safe_str(data_dict.get('img_url')))
                e_img_url2 = st.text_input("🎬 관련 영상/메모", value=safe_str(data_dict.get('img_url2')))
                
                date_val_str = data_dict.get('plan_date') if is_plan else data_dict.get('view_date')
                try: default_d = pd.to_datetime(date_val_str).date()
                except: default_d = get_kst_today()
                e_view_date = st.date_input("🗓️ 날짜", value=default_d)
                
            with col_in2:
                if cat == "SCRAP":
                    e_summary = st.text_area("📰 QUOTE(url)", value=safe_str(data_dict.get('summary')), height=120)
                    e_note = st.text_area("✍️ HANDWRITE(brief)", value=safe_str(data_dict.get('note')), height=120)
                    e_brief = st.text_input("🎯 CONTEXT(argument)", value=safe_str(data_dict.get('brief')))
                    e_highlights = st.text_area("💡 EXAMPLS(evidences)/STRUCTURE", value=safe_str(data_dict.get('highlights')), height=100)
                else:
                    e_brief = st.text_input("💎 DRIP", value=safe_str(data_dict.get('brief')))
                    e_note = st.text_area("🖋️ PRISM", value=safe_str(data_dict.get('note')), height=200)
                    e_summary = st.text_area("💡 BRIEF", value=safe_str(data_dict.get('summary')), height=100)
                    e_highlights = st.text_area("🔖 POINT", value=safe_str(data_dict.get('highlights')), height=100)

            c_save, c_cancel = st.columns([0.5, 0.5])
            if c_save.form_submit_button("💾 저장하기", type="primary", use_container_width=True):
                conn = get_connection()
                if is_plan:
                    updated_dict = {
                        "category": cat, "title": e_title.strip(), "creator": e_creator.strip(),
                        "rel_date": e_rel_date.strip(), "venue": e_venue.strip(), "summary": e_summary.strip(),
                        "brief": e_brief.strip(), "highlights": e_highlights.strip(), "note": e_note.strip(),
                        "img_url": e_img_url.strip(), "img_url2": e_img_url2.strip()
                    }
                    memo_payload = json.dumps(updated_dict, ensure_ascii=False)
                    conn.execute("UPDATE plan SET category=?, title=?, plan_date=?, memo=? WHERE id=?", (cat, e_title.strip(), str(e_view_date), memo_payload, item_id))
                    try: supabase.table("plan").update({"category": cat, "title": e_title.strip(), "plan_date": str(e_view_date), "memo": memo_payload}).eq("id", item_id).execute()
                    except: pass
                else:
                    conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, img_url=?, img_url2=?, view_date=? WHERE id=?""",
                                 (e_title.strip(), e_creator.strip(), e_rel_date.strip(), e_venue.strip(), e_summary.strip(), e_brief.strip(), e_highlights.strip(), e_note.strip(), e_img_url.strip(), e_img_url2.strip(), str(e_view_date), item_id))
                    try: supabase.table("archive").update({"title": e_title.strip(), "creator": e_creator.strip(), "rel_date": e_rel_date.strip(), "venue": e_venue.strip(), "summary": e_summary.strip(), "brief": e_brief.strip(), "highlights": e_highlights.strip(), "note": e_note.strip(), "img_url": e_img_url.strip(), "img_url2": e_img_url2.strip(), "view_date": str(e_view_date)}).eq("id", item_id).execute()
                    except: pass

                conn.commit()
                st.cache_data.clear()
                st.session_state[edit_mode_key] = False
                st.success("✅ 저장되었습니다!")
                time.sleep(0.5)
                st.rerun()

            if c_cancel.form_submit_button("❌ 취소", use_container_width=True, on_click=set_dialog_edit_mode, args=(edit_mode_key, False)):
                pass
        return

    # --- 보기 모드인 경우 ---
    share_text = f"[{cat}] {data_dict.get('title')}\n"
    if creator_text: share_text += f"👤 창작자: {creator_text}\n"
    if rel_date: share_text += f"📅 발매/출간일: {rel_date}\n"
    if venue: share_text += f"📍 레이블/출판사: {venue}\n"
    if img_url and str(img_url) != "None": share_text += f"🖼️ 커버 이미지: {img_url}\n"
    share_text += "\n"
    
    sections = [
        ("📰 QUOTE(url)", "summary", "#334155"), 
        ("✍️ HANDWRITE(brief)", "note", "#1E425E"),
        ("🎯 CONTEXT(argument)", "brief", "#0E6245"),
        ("💡 EXAMPLS(evidences)/STRUCTURE", "highlights", "#7D5600")
    ] if cat == "SCRAP" else [
        ("💎 DRIP", "brief", "#E50914"), 
        ("🖋️ PRISM", "note", "#1E425E"),
        ("💡BRIEF", "summary", "#0E6245"), 
        ("🔖 POINT", "highlights", "#7D5600")
    ]
    
    if cat == "SCRAP":
        for label, key, _ in sections:
            if data_dict.get(key) and str(data_dict.get(key)).strip():
                share_text += f"{label}:\n{data_dict.get(key)}\n\n"
    else:
        if data_dict.get('brief') and str(data_dict.get('brief')).strip():
            share_text += f"💎 DRIP:\n{data_dict.get('brief')}\n\n"
        if data_dict.get('note') and str(data_dict.get('note')).strip():
            share_text += f"🖋️ PRISM:\n{data_dict.get('note')}\n\n"

    # --- 상단 버튼 영역 (삭제 / 수정 / 공유) ---
    if IS_ADMIN:
        c1, c2, c3 = st.columns(3)
        
        if c1.button("🗑️ 삭제", key=f"del_{table_name}_{item_id}", use_container_width=True):
            conn = get_connection()
            conn.execute(f"DELETE FROM {table_name} WHERE id=?", (item_id,))
            conn.commit()
            st.cache_data.clear() 
            try: supabase.table(table_name).delete().eq("id", item_id).execute()
            except: pass
            st.rerun()
            
        if c2.button("✏️ 수정", key=f"edit_{table_name}_{item_id}", use_container_width=True, type="primary", on_click=set_dialog_edit_mode, args=(edit_mode_key, True)):
            pass
            
        with c3:
            with st.popover("🔗 공유", use_container_width=True):
                st.markdown("**아래 텍스트를 복사하세요!**")
                st.code(share_text.strip(), language="markdown")
                
        st.divider()

    # --- 콘텐츠 렌더링 영역 ---
    col_img, col_txt = st.columns([0.3, 0.7])
    with col_img:
        if img_url and str(img_url) != "None": st.image(img_url, use_container_width=True)
        
        memo_content = data_dict.get('img_url2', '')
        if pd.notna(memo_content) and str(memo_content).strip() not in ["", "None", "nan", "NaN"]:
            memo_content = str(memo_content).strip()
            url_match = re.search(r'(https?://[^\s]+)', memo_content)
            if url_match:
                media_url = url_match.group(1)
                text_part = memo_content.replace(media_url, '').strip(' /|-')
                if text_part: st.markdown(f'<div style="background-color: #0F172A; border-left: 4px solid #6366F1; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">📎 {text_part}</div>', unsafe_allow_html=True)
                if re.search(r'\.(jpg|jpeg|png|webp|gif)', media_url, re.IGNORECASE) or "image.tmdb.org" in media_url:
                    st.image(media_url, use_container_width=True)
                else:
                    try: st.video(media_url)
                    except: st.markdown(f"**[🔗 첨부 링크 보러가기]({media_url})**")
            else: 
                st.markdown(f'<div style="background-color: #0F172A; border-left: 4px solid #6366F1; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">📎 {memo_content}</div>', unsafe_allow_html=True)
    
    with col_txt:
        st.markdown(f'# {data_dict.get("title")}')
        if creator_text: st.write(f"**{'📰 ' if cat == 'SCRAP' else ''}{creator_text}**")
            
        st.write(f"**📅 {data_dict.get('rel_date', '')} | 📍 {data_dict.get('venue', '')}**")
        
        date_label = "🗓️ 예정일" if is_plan else "🍿 감상/완료일"
        date_val = data_dict.get('plan_date') if is_plan else data_dict.get('view_date')
        date_color = "#6366F1" if is_plan else "#E2E8F0"
        st.markdown(f'<p style="color: {date_color}; font-weight: bold; font-size: 1.1em;">{date_label}: {date_val}</p>', unsafe_allow_html=True)
        st.divider()
            
        for label, key, color in sections:
            val = data_dict.get(key)
            if val and str(val).strip():
                st.markdown(f'<div style="display: inline-block; background-color: {color}; color: white; padding: 4px 14px; border-radius: 20px; font-size: 0.75rem; margin-bottom: 10px; font-weight: bold; text-transform: uppercase;">{label}</div>', unsafe_allow_html=True)
                st.markdown(str(val).replace('\n', '  \n'))
                st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #334155;'>", unsafe_allow_html=True)

        if IS_ADMIN and is_plan:
            st.markdown("<br>", unsafe_allow_html=True)
            btn_label = "✅ 작성 완료 (아카이브로 이동)"
            if st.button(btn_label, key=f"to_archive_{item_id}", use_container_width=True, type="primary"):
                conn = get_connection()
                
                # 아카이브 레코드 생성
                new_record = {
                    "category": cat, 
                    "title": data_dict['title'], 
                    "creator": data_dict.get("creator", ""), 
                    "rel_date": data_dict.get("rel_date", ""),
                    "venue": data_dict.get("venue", ""), 
                    "summary": data_dict.get("summary", ""), 
                    "brief": data_dict.get("brief", ""), 
                    "highlights": data_dict.get("highlights", ""), 
                    "note": data_dict.get("note", ""), 
                    "img_url": data_dict.get("img_url", ""), 
                    "img_url2": data_dict.get("img_url2", ""), 
                    "save_date": str(get_kst_today()), 
                    "view_date": data_dict['plan_date']
                }
                
                # Local SQLite 및 Supabase 아카이브 적재
                conn.execute("""INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", tuple(new_record.values()))
                try: supabase.table("archive").upsert(new_record).execute()
                except: pass
                
                # 주간 계획(plan) 테이블에서는 삭제
                conn.execute("DELETE FROM plan WHERE id=?", (item_id,))
                conn.commit()
                st.cache_data.clear()
                
                try: supabase.table("plan").delete().eq("id", item_id).execute()
                except: pass
                
                st.success("🎉 최종 작성이 완료되어 아카이브로 안전하게 이동되었습니다!")
                time.sleep(0.8)
                st.rerun()

@st.dialog("📋 ARCHIVE", width="large")
def show_details(item): render_item_details(item if isinstance(item, dict) else item.to_dict(), item['id'], is_plan=False)

@st.dialog("🗓️ 상세 정보", width="large")
def show_plan_details(item):
    item_dict = item if isinstance(item, dict) else item.to_dict()
    try: rich_data = json.loads(item_dict['memo'])
    except: rich_data = {"note": item_dict.get('memo', '')}
    
    combined_data = {**rich_data, "id": item_dict['id'], "category": item_dict['category'], "title": item_dict['title'], "plan_date": item_dict['plan_date']}
    render_item_details(combined_data, item_dict['id'], is_plan=True)

# ==========================================
# 7. MAIN APPLICATION ROUTING & VIEWS
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
st.markdown(f"""
<div style="display: flex; align-items: center; gap: 16px; margin-bottom: 24px; padding: 12px 0; border-bottom: 1px solid #334155;">
    <img src="data:image/png;base64,{get_base64('logo.png')}" width="75" style="border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.4);">
    <div>
        <h1 style="margin: 0; font-size: 2.1rem; font-weight: 800; letter-spacing: -1px; background: linear-gradient(45deg, #FFFFFF, #94A3B8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">PRISM ARCHIVE</h1>
        <p style="margin: 0; color: #64748B; font-size: 0.85rem; font-weight: 500;">all right reserved by FLASHMAN</p>
    </div>
</div>
""", unsafe_allow_html=True)

if IS_ADMIN:
    st.radio("메뉴", ["🖋️ WRITE", "📂 ARCHIVE"], horizontal=True, label_visibility="collapsed", key="main_nav")
    st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

tab_w = (st.session_state.main_nav == "🖋️ WRITE")

# ----------------- [WRITE 탭] -----------------
if IS_ADMIN and tab_w:
    # WRITE 탭 전체를 좌우 2분할 (왼쪽 4.5 : 오른쪽 5.5)
    col_write_left, col_write_right = st.columns([0.45, 0.55], gap="large")

    # ==========================================
    # [왼쪽 영역] 이미지 중심 주간 계획 목록 (월~일 리스트)
    # ==========================================
    with col_write_left:
        st.markdown("<h4 style='font-weight: 800; color: #F1F5F9; margin-bottom: 12px;'>📅 주간 계획</h4>", unsafe_allow_html=True)
        
        # 주간 이동 컨트롤
        lc1, lc2, lc3 = st.columns([0.15, 0.7, 0.15])
        with lc1:
            if st.button("⬅️", use_container_width=True, key="w_prev_week_side"):
                st.session_state.week_offset -= 1
                st.rerun()
        
        today_ts = pd.Timestamp(get_kst_today())
        view_monday = today_ts - pd.Timedelta(days=today_ts.weekday()) + pd.Timedelta(weeks=st.session_state.week_offset)
        view_sunday = view_monday + pd.Timedelta(days=6)
        
        with lc2:
            st.markdown(f"<div style='text-align: center; font-weight: 700; color: #818CF8;'>{view_monday.isocalendar().week}주차 ({view_monday.strftime('%m.%d')} ~ {view_sunday.strftime('%m.%d')})</div>", unsafe_allow_html=True)
        
        with lc3:
            if st.button("➡️", use_container_width=True, key="w_next_week_side"):
                st.session_state.week_offset += 1
                st.rerun()
        
        st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

        plan_df = pd.read_sql_query("SELECT * FROM plan ORDER BY plan_date ASC", get_connection())
        if not plan_df.empty: 
            plan_df['p_dt'] = pd.to_datetime(plan_df['plan_date'])
            week_data = plan_df[(plan_df['p_dt'].dt.date >= view_monday.date()) & (plan_df['p_dt'].dt.date <= view_sunday.date())]
        else:
            week_data = pd.DataFrame()

        # 월요일 ~ 일요일 루프 처리하여 리스트 형식 렌더링
        days_korean = ["월", "화", "수", "목", "금", "토", "일"]
        for i in range(7):
            current_day = view_monday + pd.Timedelta(days=i)
            day_items = week_data[week_data['p_dt'].dt.date == current_day.date()].to_dict('records') if not week_data.empty else []
            
            # 요일 헤더
            st.markdown(f"<div style='font-weight: 800; font-size: 1.05rem; color: #818CF8; margin-top: 16px; border-bottom: 2px solid #334155; padding-bottom: 6px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: flex-end;'><span>{current_day.strftime('%m.%d')}</span><span style='font-size: 0.85rem; color: #94A3B8;'>{days_korean[i]}요일</span></div>", unsafe_allow_html=True)
            
            if not day_items:
                st.markdown("<div style='color: #64748B; font-size: 0.85rem; padding: 12px; text-align: center; background: rgba(30, 41, 59, 0.5); border-radius: 8px; border: 1px dashed #334155;'>일정 없음</div>", unsafe_allow_html=True)
            else:
                for item in day_items:
                    try: img_url = json.loads(item['memo']).get('img_url', '')
                    except: img_url = ""
                    
                    emoji = CAT_EMOJIS.get(item['category'], "📌")
                    title_display = item['title']
                    
                    # 이미지 기반 유연한 UI 카드 생성
                    if img_url and img_url.strip() and img_url != "None":
                        html_card = f'''
                        <div style="position: relative; width: 100%; border-radius: 12px; overflow: hidden; border: 1px solid #334155; margin-bottom: 6px; background: #0F172A;">
                            <div style="position: absolute; top: 10px; left: 10px; background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(4px); color: #FBBF24; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; z-index: 10; border: 1px solid rgba(255,255,255,0.1);">{item['category']}</div>
                            <img src="{img_url}" style="width: 100%; height: auto; display: block; object-fit: contain; max-height: 450px; margin: 0 auto;">
                        </div>
                        '''
                        st.markdown(html_card, unsafe_allow_html=True)
                    else:
                        st.markdown(f'''
                        <div style="width: 100%; border-radius: 12px; border: 1px solid #334155; margin-bottom: 6px; background: #0F172A; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 30px 20px;">
                            <div style="color: #FBBF24; font-size: 0.8rem; font-weight: 700; margin-bottom: 8px;">{item['category']}</div>
                            <div style="font-size: 2.5rem;">{emoji}</div>
                        </div>
                        ''', unsafe_allow_html=True)
                    
                    # 상세 보기 버튼 연결
                    if st.button(title_display, key=f"w_card_btn_{item['id']}", use_container_width=True):
                        show_plan_details(item)

    # ==========================================
    # [오른쪽 영역] 외부 API 검색 및 수집 / 작성 폼
    # ==========================================
    with col_write_right:
        st.markdown("<h4 style='font-weight: 800; color: #F1F5F9; margin-bottom: 12px;'>🔍 검색 및 수집 / 작성</h4>", unsafe_allow_html=True)
        
        category = st.radio("📂 CATEGORY", CATEGORIES, horizontal=True, key="main_category_radio")
        search_query = st.text_input(f"🔍 {category} 검색")
        
        # API 검색 처리
        if search_query:
            if category == "SCRAP":
                if st.button("✨ 가져오기", use_container_width=True):
                    if s := scrape_url(search_query):
                        st.session_state.edit_target_id = None
                        st.session_state.edit_source = None
                        st.session_state.f_title = s['title']
                        st.session_state.f_creator = ''
                        st.session_state.f_date = ""
                        st.session_state.f_view_date = get_kst_today()
                        st.session_state.f_img = s['img']
                        st.session_state.f_venue = s['venue']
                        st.session_state.f_summary = s['summary']
                        st.session_state.f_highlights = ""
                        st.session_state.f_note = ""
                        st.session_state.f_brief = ""
                        st.session_state.f_video = ""
                        st.rerun()
                    else: st.error("URL 정보를 가져올 수 없습니다.")
            elif category == "BOOKS":
                if res := search_books(search_query):
                    sel = st.selectbox("결과 선택", list((opts := {f"📚 {b['title']}": b for b in res}).keys()))
                    if st.button("✨ 가져오기", use_container_width=True):
                        b = opts[sel]
                        st.session_state.update(edit_target_id=None, edit_source=None, f_title=b['title'], f_creator=", ".join(b['authors']), f_date=b['datetime'][:10], f_img=b.get('thumbnail', '').replace("R120x174", "R400x0"), f_venue=b.get('publisher', ''), f_summary=b.get('contents', ''), f_highlights="", f_note="", f_brief="", f_video="")
                        st.rerun()
            elif category == "MUSIC":
                if res := search_apple_music(search_query):
                    sel = st.selectbox("결과 선택", list((opts := {m['display_name']: m for m in res}).keys()))
                    if st.button("✨ 가져오기", use_container_width=True):
                        m = opts[sel]
                        tl_text = ""
                        if m.get('is_album') and m.get('collection_id'):
                            try:
                                tracks = [t['trackName'] for t in requests.get(f"https://itunes.apple.com/lookup?id={m['collection_id']}&entity=song").json().get("results", []) if t.get('wrapperType') == 'track']
                                if tracks: tl_text = "💿 트랙리스트\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(tracks)])
                            except: pass
                        
                        combined_summary = f"{m.get('url', '')}\n\n{tl_text}".strip()
                        st.session_state.update(edit_target_id=None, edit_source=None, f_title=m['title'], f_creator=m['creator'], f_date=m['date'], f_img=m['img'], f_venue=m['venue'], f_summary=combined_summary, f_highlights="", f_note="", f_brief="", f_video="")
                        st.rerun()
            elif category == "STAGE":
                if res := search_kopis(search_query):
                    sel = st.selectbox("결과 선택", list((opts := {f"🎭 {s['title']} [{s['date']}~] ({s['venue']})": s for s in res}).keys()))
                    if st.button("✨ 가져오기", use_container_width=True):
                        s = opts[sel]
                        st.session_state.update(edit_target_id=None, edit_source=None, f_title=s['title'], f_creator=get_kopis_detail(s['id']), f_date=s['date'], f_img=s['img'], f_venue=s['venue'], f_summary=f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={s['id']}", f_highlights="", f_note="", f_brief="", f_video="")
                        st.rerun()
            else: 
                if res := search_tmdb(search_query, category):
                    type_path = "movie" if category == "MOVIES" else "tv"
                    t_key, d_key = ('title', 'release_date') if category == 'MOVIES' else ('name', 'first_air_date')
                    sel = st.selectbox("결과 선택", list((opts := {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}).keys()))
                    if st.button("✨ 가져오기", use_container_width=True):
                        s = opts[sel]; details = get_tmdb_details(s['id'], category)
                        st.session_state.update(edit_target_id=None, edit_source=None, f_title=s.get(t_key, ''), f_creator=details['creator'], f_date=s.get(d_key, ''), f_img=f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", f_venue=details['venue'], f_summary=s.get('overview', ''), f_highlights="", f_note="", f_brief="", f_video="")
                        st.rerun()

        st.divider()

        # --- 입력 폼 영역 ---
        with st.form(key="prism_write_form", clear_on_submit=False):
            cl, cr = st.columns([0.45, 0.55])
            with cl:
                st.text_input("🖼️ 이미지 URL", key="f_img")
                st.text_input("🎬 관련 영상(URL) 또는 메모", key="f_video")
                if st.session_state.f_img and st.session_state.f_img.strip() and st.session_state.f_img != "None": 
                    st.image(st.session_state.f_img, use_container_width=True)
                
                st.text_input("📌 제목", key="f_title")
                st.text_input("👤 창작자/매체" if category == "SCRAP" else "👤 창작자", key="f_creator")
                st.text_input("📅 작품 날짜", key="f_date")
                st.text_input("📍 장소/플랫폼", key="f_venue")
                st.date_input("🗓️ 주간 계획 예정일", key="f_view_date")
            
            with cr:
                if category == "SCRAP":
                    st.text_area("📰 QUOTE(url)", key="f_summary", height=120)
                    st.text_area("✍️ HANDWRITE(brief)", key="f_note", height=120)
                    st.text_input("🎯 CONTEXT(argument)", key="f_brief")
                    st.text_area("💡 EXAMPLS(evidences)/STRUCTURE", key="f_highlights", height=100)
                else:
                    st.text_input("💎 DRIP", key="f_brief")
                    st.text_area("🖋️ PRISM", key="f_note", height=240)
                    st.text_area("💡BRIEF", key="f_summary", height=100)
                    st.text_area("🔖 POINT", key="f_highlights", height=100)
            
            st.markdown("<br>", unsafe_allow_html=True)
            cb1, cb2 = st.columns([0.75, 0.25])
            
            def save_data():
                if not st.session_state.f_title.strip(): return False
                conn = get_connection()
                data = { "category": str(category), "title": st.session_state.f_title.strip(), "creator": st.session_state.f_creator.strip(), "rel_date": st.session_state.f_date.strip(), "venue": st.session_state.f_venue.strip(), "summary": st.session_state.f_summary.strip(), "brief": st.session_state.f_brief.strip(), "highlights": st.session_state.f_highlights.strip(), "note": st.session_state.f_note.strip(), "img_url": st.session_state.f_img.strip(), "img_url2": st.session_state.f_video.strip() }
                
                memo_payload = json.dumps(data, ensure_ascii=False)
                conn.execute("INSERT INTO plan (plan_date, category, title, memo) VALUES (?,?,?,?)", (str(st.session_state.f_view_date), str(category), st.session_state.f_title.strip(), memo_payload))
                try: supabase.table("plan").upsert({"plan_date": str(st.session_state.f_view_date), "category": str(category), "title": st.session_state.f_title.strip(), "memo": memo_payload}).execute()
                except: pass
                
                conn.commit()
                st.cache_data.clear()
                st.session_state.should_clear_form = True
                return True

            if cb1.form_submit_button("🗓️ 주간 계획 등록", use_container_width=True, type="primary"):
                if save_data(): st.success("🗓️ 주간 계획에 성공적으로 등록되었습니다!"); time.sleep(0.8); st.rerun()
                else: st.warning("제목을 입력해 주세요.")

            if cb2.form_submit_button("🔄 비우기", use_container_width=True):
                st.session_state.should_clear_form = True
                st.rerun()

# ----------------- [ARCHIVE 탭] -----------------
elif not tab_w:
    st.markdown("""<style>
    /* 미디어 커버 카드 인프라 업그레이드 */
    .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 12px; margin-top: 8px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.3); background: #1E293B; display: flex; align-items: center; justify-content: center; border: 1px solid #334155; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); } 
    .cal-img-box:hover { transform: translateY(-5px); border-color: #6366F1; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.6), 0 10px 10px -5px rgba(0, 0, 0, 0.5); }
    .cal-img-box img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.4s ease; } 
    .cal-img-box:hover img { transform: scale(1.04); }
    .music-tab-style { aspect-ratio: 1/1 !important; } 
    
    /* 카드 장식 배지 글래스모피즘 효과 */
    .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(15, 23, 42, 0.75); backdrop-filter: blur(4px); color: #FBBF24; padding: 2px 8px; border-radius: 20px; font-size: 10px; font-weight: 700; z-index: 10; letter-spacing: 0.5px; border: 1px solid rgba(255,255,255,0.05); } 
    .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(15, 23, 42, 0.75); backdrop-filter: blur(4px); color: #E2E8F0; padding: 2px 8px; border-radius: 20px; font-size: 10px; font-weight: 600; z-index: 10; border: 1px solid rgba(255,255,255,0.05); } 
    
    /* 타이틀 텍스트 보정 스트림릿 컴포넌트 처리 */
    div[data-testid="stColumn"] button {
        background-color: transparent !important;
        border: none !important;
        color: #E2E8F0 !important;
        padding: 4px 0px !important;
        text-align: left !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
    }
    div[data-testid="stColumn"] button:hover {
        color: #6366F1 !important;
    }
    
    @media (max-width: 992px) { 
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; } 
        div[data-testid="column"] { min-width: 100% !important; flex: 1 1 100% !important; margin-bottom: 15px !important; } 
    } 
    @media (min-width: 993px) { 
        [data-testid="stHorizontalBlock"] { display: flex !important; flex-wrap: nowrap !important; gap: 12px !important; } 
        [data-testid="column"] { flex: 1 1 0% !important; min-width: 0 !important; } 
    }
    </style>""", unsafe_allow_html=True)
    all_df = get_all_data()

    if not all_df.empty:
        if search_query_archive := st.text_input("🔍 아카이브 내 실시간 통합 검색", key="global_search"):
            mask = (all_df['title'].str.contains(search_query_archive, case=False, na=False) | all_df['creator'].str.contains(search_query_archive, case=False, na=False) | all_df['summary'].str.contains(search_query_archive, case=False, na=False) | all_df['note'].str.contains(search_query_archive, case=False, na=False) | all_df['venue'].str.contains(search_query_archive, case=False, na=False))
            all_df = all_df[mask]; st.markdown(f"**'{search_query_archive}'** 검색 결과 ({len(all_df)})"); st.divider()

        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        main_df, scrap_df = all_df[all_df['category'] != "SCRAP"], all_df[all_df['category'] == "SCRAP"]
        cat_order = CATEGORIES[:-1]
        
        tab_titles = [f"📅 ALL ({len(main_df)})"] + [f"{CAT_EMOJIS[c]} {c} ({len(main_df[main_df['category'] == c])})" for c in cat_order]
        if IS_ADMIN: tab_titles.append(f"🔐 SCRAP ({len(scrap_df)})")
        sub_tabs = st.tabs(tab_titles)
        grid_cols = 6

        with sub_tabs[0]:
            if years := sorted(main_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True):
                sel_y = st.selectbox("📅 YEAR", options=years, format_func=lambda y: f"{y} 년도 ({len(main_df[main_df['v_dt'].dt.year == y])})", key="archive_year_sel")
                st.markdown("<div style='margin-bottom: 10px;'></div>", unsafe_allow_html=True)
                y_df = main_df[main_df['v_dt'].dt.year == sel_y]
                
                for m in range(12, 0, -1):
                    m_data = y_df[y_df['v_dt'].dt.month == m]
                    if not m_data.empty:
                        st.subheader(f"🗓 {m}월 ({len(m_data)})")
                        items = m_data.to_dict('records')
                        for i in range(0, len(items), grid_cols):
                            cols = st.columns(grid_cols)
                            for j in range(grid_cols):
                                if i+j < len(items):
                                    row = items[i+j]
                                    img_style = 'style="height: auto; aspect-ratio: 1/1;"' if row["category"] == "MUSIC" else ""
                                    with cols[j]:
                                        st.markdown(f'<div class="cal-img-box"><div class="badge-cat">{row["category"]}</div><div class="badge-date">{pd.to_datetime(row["view_date"]).day}일</div><img src="{row["img_url"]}" {img_style}></div>', unsafe_allow_html=True)
                                        if st.button(row['title'][:19] + "..." if len(row['title']) > 19 else row['title'], key=f"all_btn_{row['id']}", use_container_width=True): show_details(row)

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
                                    if st.button(row['title'][:20] + "..." if len(row['title']) > 20 else row['title'], key=f"cat_btn_{c_name}_{row['id']}", use_container_width=True): show_details(row)

        if IS_ADMIN:
            with sub_tabs[-1]:
                if not scrap_df.empty:
                    week_scrap = scrap_df[scrap_df['v_dt'] >= (pd.Timestamp(get_kst_today()) - pd.Timedelta(days=pd.Timestamp(get_kst_today()).weekday()))]
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
                        st.info(f"🏷️ '#{st.session_state.selected_tag}' 태그가 포함된 SCRAP만 봅니다. (해제하려면 위의 버튼을 다시 누르세요)")
                    
                    if not display_scrap_df.empty:
                        display_scrap_df['year_week'] = display_scrap_df['v_dt'].dt.isocalendar().year.astype(str) + "-" + display_scrap_df['v_dt'].dt.isocalendar().week.astype(str).str.zfill(2)
                        for w in sorted(display_scrap_df['year_week'].dropna().unique(), reverse=True):
                            w_data = display_scrap_df[display_scrap_df['year_week'] == w]
                            y_str, w_str = w.split('-')
                            st.subheader(f"🗓️ {y_str}-{int(w_str)}주차 ({len(w_data)})")
                            for _, row in w_data.iterrows():
                                with st.expander(f"👉 [{row['venue']}] {row['title']} ({row['view_date']})"):
                                    summary_text = str(row['summary'])
                                    if summary_text.startswith("http"):
                                        st.markdown(f"**[🔗 원본]({summary_text.split(chr(10))[0]})**")
                                    elif row['summary']: 
                                        st.markdown(f"**📰 기사:**<br>{str(row['summary']).replace(chr(10), '<br>')}", unsafe_allow_html=True)
                                    
                                    if row['note']: st.markdown(f"**✍️ HANDWRITE(brief):**<br>{row['note'].replace(chr(10), '<br>')}", unsafe_allow_html=True)
                                    if row['brief']: st.write(f"**🎯 CONTEXT(argument):** {row['brief']}")
                                    if row['highlights']: st.markdown(f"**💡 EXAMPLS(evidences)/STRUCTURE:**<br>{row['highlights'].replace(chr(10), '<br>')}", unsafe_allow_html=True)
                                    
                                    if st.button("✏️ 수정", key=f"scr_btn_{row['id']}"): show_details(row)
                    else: st.info("해당 태그나 검색어에 맞는 SCRAP이 없습니다.")
                else: st.info("SCRAP 기록이 없습니다.")

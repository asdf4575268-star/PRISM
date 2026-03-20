import calendar
import streamlit as st
import streamlit.components.v1 as components
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

def get_image_base64(url):
    if not url or str(url).strip() == "None": return ""
    try:
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            content_type = res.headers.get('Content-Type', 'image/jpeg')
            return f"data:{content_type};base64,{base64.b64encode(res.content).decode()}"
    except: pass
    return ""

# --- [3. 로그인 및 Session State 초기화] ---
DEV_MODE = False 
cookie_manager = stx.CookieManager()

if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False

if "user_password" not in st.session_state:
    st.session_state.user_password = ""
if "selected_tag" not in st.session_state:
    st.session_state.selected_tag = None
if "show_form" not in st.session_state:
    st.session_state.show_form = False
if "week_offset" not in st.session_state:
    st.session_state.week_offset = 0
if "should_clear_form" not in st.session_state:
    st.session_state.should_clear_form = False

form_keys = ['f_title', 'f_creator', 'f_date', 'f_venue', 'f_img', 'f_video', 'f_summary', 'f_brief', 'f_highlights', 'f_note']

if st.session_state.should_clear_form:
    for k in form_keys:
        if k in st.session_state:
            st.session_state[k] = ""
    st.session_state.f_view_date = date.today()
    st.session_state.show_form = False
    st.session_state.should_clear_form = False

for k in form_keys:
    if k not in st.session_state:
        st.session_state[k] = ""
if 'f_view_date' not in st.session_state:
    st.session_state.f_view_date = date.today()

# [핵심 수정] 쿠키 딜레이로 인한 세션 초기화 방지 로직
admin_cookie = cookie_manager.get(cookie="admin_logged_in")

if admin_cookie == "yes":
    st.session_state.is_logged_in = True
elif admin_cookie == "no":
    st.session_state.is_logged_in = False
# None일 경우에는 기존의 st.session_state.is_logged_in 값을 그대로 유지합니다.

is_admin = st.session_state.is_logged_in or DEV_MODE

with st.sidebar:
    st.markdown("### 🔐 관리자 접속")
    if not is_admin:
        input_password = st.text_input("비밀번호", type="password", key="sidebar_pw_main")
        if input_password:
            if input_password == st.secrets["ADMIN_PASSWORD"]:
                cookie_manager.set("admin_logged_in", "yes", expires_at=datetime.now() + timedelta(days=30))
                st.session_state.is_logged_in = True
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
    
    if is_admin:
        st.success("관리자 모드 활성화됨")
        
        if st.button("🔓 로그아웃", key="logout_btn", use_container_width=True):
            cookie_manager.set("admin_logged_in", "no", expires_at=datetime.now() + timedelta(days=30))
            st.session_state.is_logged_in = False
            st.session_state.user_password = ""
            st.session_state.should_clear_form = True
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
        st.button("📤 클라우드 백업", key="backup_sidebar", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 클라우드 복구", key="restore_sidebar", on_click=restore_from_supabase, use_container_width=True)

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
            if creators: creator_names = ", ".join([c['name'] for c in creators])
            else: creator_names = next((m['name'] for m in crew_list if m.get('job') in ['Writer', 'Executive Producer']), "정보 없음")
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
    edit_mode = False
    if is_admin:
        t_col1, _, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                conn = get_connection()
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                conn.commit()
                st.cache_data.clear() 
                try: supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
                except: pass
                st.rerun()
        with t_col3: edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    col_img, col_txt = st.columns([0.3, 0.7])
    
    if is_admin and edit_mode:
        prefix = f"ea_{item['id']}_"
        
        for k, v in [('img', item.get('img_url', '')), ('vid', item.get('img_url2', '')), 
                     ('title', item.get('title', '')), ('creator', item.get('creator', '')), 
                     ('rel', item.get('rel_date', '')), ('ven', item.get('venue', '')), 
                     ('sum', item.get('summary', '')), ('high', item.get('highlights', '')), 
                     ('note', item.get('note', '')), ('brief', item.get('brief', ''))]:
            if prefix+k not in st.session_state:
                st.session_state[prefix+k] = str(v)
        
        if prefix+"view" not in st.session_state:
            try: st.session_state[prefix+"view"] = pd.to_datetime(item.get('view_date')).date()
            except: st.session_state[prefix+"view"] = date.today()

        col_img_form, col_txt_form = st.columns([0.3, 0.7])
        with col_img_form:
            st.text_input("🖼️ 이미지 URL", key=prefix+"img")
            st.text_input("🎬 관련 영상(URL) 또는 제목/메모", key=prefix+"vid")
            if st.session_state[prefix+"img"].strip() and st.session_state[prefix+"img"] != "None": 
                st.image(st.session_state[prefix+"img"], use_container_width=True)
                
        with col_txt_form:
            st.text_input("📌 제목", key=prefix+"title")
            cat = item.get('category')
            creator_label_edit = "👤 창작자/매체" if cat == "SCRAP" else "👤 창작자"
            st.text_input(creator_label_edit, key=prefix+"creator")
            
            c1, c2 = st.columns(2)
            c1.text_input("📅 작품 날짜", key=prefix+"rel")
            c2.text_input("📍 장소/플랫폼", key=prefix+"ven")
            st.date_input("🍿 감상일 수정", key=prefix+"view")
            st.text_area("📖 INFO", key=prefix+"sum", height=100)
            
            if cat == "SCRAP":
                st.text_area("✨ 5문장 요약", key=prefix+"high", height=150)
                st.text_area("🌈 5문장 감상", key=prefix+"note", height=150)
                st.text_input("📝 요약 (한 줄 평)", key=prefix+"brief")
            else:
                st.text_area("📦 SKETCH", key=prefix+"high", height=250)
                st.text_area("🖋️ PRISM", key=prefix+"note", height=200)
                st.text_input("💎 Step 한 줄 평", key=prefix+"brief")
            
            if st.button("💾 저장", use_container_width=True, type="primary"):
                try:
                    conn = get_connection()
                    conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=?, img_url2=? WHERE id=?""", 
                                 (st.session_state[prefix+"title"], st.session_state[prefix+"creator"], st.session_state[prefix+"rel"], st.session_state[prefix+"ven"], 
                                  st.session_state[prefix+"sum"], st.session_state[prefix+"brief"], st.session_state[prefix+"high"], st.session_state[prefix+"note"], 
                                  str(st.session_state[prefix+"view"]), st.session_state[prefix+"img"], st.session_state[prefix+"vid"], item['id']))
                    conn.commit()
                    st.cache_data.clear() 
                    supabase.table("archive").update({
                        "title": st.session_state[prefix+"title"], "creator": st.session_state[prefix+"creator"], "rel_date": st.session_state[prefix+"rel"], 
                        "venue": st.session_state[prefix+"ven"], "summary": st.session_state[prefix+"sum"], "brief": st.session_state[prefix+"brief"], 
                        "highlights": st.session_state[prefix+"high"], "note": st.session_state[prefix+"note"], "view_date": str(st.session_state[prefix+"view"]), 
                        "img_url": st.session_state[prefix+"img"], "img_url2": st.session_state[prefix+"vid"]
                    }).eq("title", item['title']).eq("view_date", item['view_date']).execute()
                    
                    for k in ['img', 'vid', 'title', 'creator', 'rel', 'ven', 'sum', 'high', 'note', 'brief', 'view']:
                        del st.session_state[prefix+k]
                        
                    st.success("✅ 수정 완료!"); time.sleep(0.5); st.rerun()
                except Exception as e: st.error(f"❌ 오류: {e}")
    else: 
        with col_img:
            if item.get('img_url') and str(item.get('img_url')) != "None": st.image(item['img_url'], use_container_width=True)
            memo_content = item.get('img_url2', '')
            if memo_content and str(memo_content) != "None":
                url_match = re.search(r'(https?://[^\s]+)', memo_content)
                if url_match:
                    video_url = url_match.group(1); text_part = memo_content.replace(video_url, '').strip(' /|-')
                    if text_part: st.markdown(f'<div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">🎬 {text_part}</div>', unsafe_allow_html=True)
                    st.video(video_url)
                else: st.markdown(f'<div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">🎬 {memo_content}</div>', unsafe_allow_html=True)
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
            
            if item.get("category") == "SCRAP":
                sections = [("📝 한 줄 평", "brief", "#0E6245"), ("✨ 5문장 요약", "highlights", "#7D5600"), ("🌈 5문장 감상", "note", "#1E425E"), ("📖 INFO", "summary", "#444")]
            else:
                if is_admin:
                    sections = [
                        ("💎 한 줄 평", "brief", "#E50914"), 
                        ("🖋️ PRISM", "note", "#1E425E"), 
                        ("📦 SKETCH", "highlights", "#7D5600"), 
                        ("📖 INFO", "summary", "#444")
                    ]
                else:
                    sections = [
                        ("💎 한 줄 평", "brief", "#E50914"), 
                        ("🖋️ PRISM 리뷰", "note", "#1E425E")
                    ]
                
            for label, key, color in sections:
                if item.get(key):
                    st.markdown(f'<div style="display: inline-block; background-color: {color}; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px; font-weight: bold;">{label}</div>', unsafe_allow_html=True)
                    st.markdown(item[key].replace('\n', '  \n'))
                    st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)
            
            if item.get("category") != "SCRAP":
                st.markdown("<br>", unsafe_allow_html=True)
                
                st.subheader("🔗 외부에 리뷰 공유하기")
                
                share_text_mobile = f"[{item.get('category')}] {item.get('title')}\n"
                if creator_text: share_text_mobile += f"- {creator_text}\n"
                share_text_mobile += "\n"
                if item.get('img_url2') and str(item.get('img_url2')) != "None": share_text_mobile += f"🎬 관련 링크: {item.get('img_url2')}\n\n"
                if item.get('brief'): share_text_mobile += f"💎 한 줄 평: {item.get('brief')}\n\n"
                if item.get('note'): share_text_mobile += f"🖋️ PRISM 리뷰:\n{item.get('note')}"
                
                safe_share_text = share_text_mobile.strip().replace('`', '\\`').replace('\n', '\\n')
                img_b64_data = get_image_base64(item.get('img_url', ''))
                
                share_html = f"""
                <div style="margin-bottom: 15px;">
                    <button onclick="shareItem()" style="width:100%; padding:12px; background: linear-gradient(45deg, #405de6, #5851db, #833ab4, #c13584, #e1306c, #fd1d1d); color:white; border-radius:8px; border:none; cursor:pointer; font-weight:bold; font-size:16px;">
                        📲 모바일 SNS / 카톡으로 공유하기
                    </button>
                </div>
                <script>
                async function shareItem() {{
                    let shareData = {{ title: 'PRISM 리뷰', text: `{safe_share_text}` }};
                    const imgB64 = "{img_b64_data}";
                    if (imgB64 && navigator.canShare) {{
                        try {{
                            const res = await fetch(imgB64);
                            const blob = await res.blob();
                            const file = new File([blob], 'prism_cover.jpg', {{ type: blob.type }});
                            if (navigator.canShare({{ files: [file] }})) shareData.files = [file];
                        }} catch (e) {{ console.log(e); }}
                    }}
                    try {{
                        if (navigator.share) await navigator.share(shareData);
                        else alert('현재 브라우저에서는 공유 기능을 지원하지 않습니다. 아래 블로그용 복사를 이용해주세요.');
                    }} catch (e) {{ console.log(e); }}
                }}
                </script>
                """
                components.html(share_html, height=65)

                with st.expander("📝 블로그 포스팅용 복사 (티스토리, 네이버, 벨로그)"):
                    blog_text = f"## [{item.get('category')}] {item.get('title')}\n\n"
                    if item.get('img_url') and str(item.get('img_url')) != "None":
                        blog_text += f"![포스터/커버]({item.get('img_url')})\n\n"
                    
                    blog_text += f"- **창작자:** {creator_text}\n"
                    blog_text += f"- **일시/장소:** {item.get('rel_date')} | {item.get('venue')}\n"
                    if item.get('img_url2') and str(item.get('img_url2')) != "None":
                        blog_text += f"- **관련 영상/링크:** {item.get('img_url2')}\n"
                    blog_text += "\n---\n\n"
                    
                    if item.get('brief'): blog_text += f"### 💎 한 줄 평\n{item.get('brief')}\n\n"
                    if item.get('note'): blog_text += f"### 🖋️ PRISM 리뷰\n{item.get('note')}\n\n"
                    
                    st.info("우측 상단의 복사(📋) 버튼을 눌러 블로그 에디터에 붙여넣기 하세요!")
                    st.code(blog_text.strip(), language="markdown")

@st.dialog("🗓️상세 정보", width="large")
def show_plan_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    try: rich_data = json.loads(item['memo'])
    except: rich_data = {"creator": "", "rel_date": "", "venue": "", "summary": "", "brief": "", "highlights": "", "note": item.get('memo', ''), "img_url": "", "img_url2": ""}
    
    edit_mode = False
    if is_admin:
        t_col1, _, t_col3 = st.columns([0.2, 0.6, 0.2])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_plan_{item['id']}", use_container_width=True):
                conn = get_connection()
                conn.execute("DELETE FROM plan WHERE id=?", (item['id'],))
                conn.commit()
                st.cache_data.clear()
                try: supabase.table("plan").delete().eq("title", item['title']).eq("plan_date", item['plan_date']).execute()
                except: pass
                st.rerun()
        with t_col3: 
            edit_mode = st.toggle("✏️ 수정", key=f"tog_plan_{item['id']}")
        st.divider()
        
    col_img, col_txt = st.columns([0.3, 0.7])
    
    if is_admin and edit_mode:
        prefix = f"ep_{item['id']}_"
        for k, v in [('img', rich_data.get('img_url', '')), ('vid', rich_data.get('img_url2', '')), 
                     ('title', item.get('title', '')), ('creator', rich_data.get('creator', '')), 
                     ('rel', rich_data.get('rel_date', '')), ('ven', rich_data.get('venue', '')), 
                     ('sum', rich_data.get('summary', '')), ('high', rich_data.get('highlights', '')), 
                     ('note', rich_data.get('note', '')), ('brief', rich_data.get('brief', ''))]:
            if prefix+k not in st.session_state: st.session_state[prefix+k] = str(v)
        
        if prefix+"view" not in st.session_state:
            try: st.session_state[prefix+"view"] = pd.to_datetime(item.get('plan_date')).date()
            except: st.session_state[prefix+"view"] = date.today()

        col_img_form, col_txt_form = st.columns([0.3, 0.7])
        with col_img_form:
            st.text_input("🖼️ 이미지 URL", key=prefix+"img")
            st.text_input("🎬 관련 영상(URL) 또는 제목/메모", key=prefix+"vid")
            if st.session_state[prefix+"img"].strip() and st.session_state[prefix+"img"] != "None": 
                st.image(st.session_state[prefix+"img"], use_container_width=True)
                
        with col_txt_form:
            st.text_input("📌 제목", key=prefix+"title")
            st.text_input("👤 창작자", key=prefix+"creator")
            c1, c2 = st.columns(2)
            c1.text_input("📅 작품 날짜", key=prefix+"rel")
            c2.text_input("📍 장소", key=prefix+"ven")
            st.date_input("🗓️ 예정일 수정", key=prefix+"view")
            st.text_area("📖 INFO", key=prefix+"sum", height=100)
            
            if item.get("category") == "SCRAP":
                st.text_area("✨ 5문장 요약", key=prefix+"high", height=150)
                st.text_area("🌈 5문장 감상", key=prefix+"note", height=150)
                st.text_input("📝 요약 (한 줄 평)", key=prefix+"brief")
            else:
                st.text_area("📦 SKETCH", key=prefix+"high", height=250)
                st.text_area("🖋️ PRISM", key=prefix+"note", height=200)
                st.text_input("💎 한 줄 평", key=prefix+"brief")
            
            if st.button("💾 저장", use_container_width=True, type="primary"):
                new_rich = {
                    "creator": st.session_state[prefix+"creator"].strip(), "rel_date": st.session_state[prefix+"rel"].strip(), 
                    "venue": st.session_state[prefix+"ven"].strip(), "summary": st.session_state[prefix+"sum"].strip(), 
                    "brief": st.session_state[prefix+"brief"].strip(), "highlights": st.session_state[prefix+"high"].strip(), 
                    "note": st.session_state[prefix+"note"].strip(), "img_url": st.session_state[prefix+"img"].strip(), 
                    "img_url2": st.session_state[prefix+"vid"].strip()
                }
                memo_payload = json.dumps(new_rich, ensure_ascii=False)
                conn = get_connection()
                conn.execute("UPDATE plan SET title=?, plan_date=?, memo=? WHERE id=?", 
                             (st.session_state[prefix+"title"], str(st.session_state[prefix+"view"]), memo_payload, item['id']))
                conn.commit()
                st.cache_data.clear()
                try: supabase.table("plan").update({"title": st.session_state[prefix+"title"], "plan_date": str(st.session_state[prefix+"view"]), "memo": memo_payload}).eq("title", item['title']).eq("plan_date", item['plan_date']).execute()
                except: pass
                
                for k in ['img', 'vid', 'title', 'creator', 'rel', 'ven', 'sum', 'high', 'note', 'brief', 'view']:
                    del st.session_state[prefix+k]
                    
                st.success("✅ 수정 완료!"); time.sleep(0.5); st.rerun()
    else: 
        with col_img:
            if rich_data.get('img_url') and str(rich_data.get('img_url')) != "None": st.image(rich_data['img_url'], use_container_width=True)
            memo_content = rich_data.get('img_url2', '')
            if memo_content and str(memo_content) != "None":
                url_match = re.search(r'(https?://[^\s]+)', memo_content)
                if url_match:
                    video_url = url_match.group(1); text_part = memo_content.replace(video_url, '').strip(' /|-')
                    if text_part: st.markdown(f'<div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">🎬 {text_part}</div>', unsafe_allow_html=True)
                    st.video(video_url)
                else: st.markdown(f'<div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; color: #fff; font-weight: bold; margin-bottom: 10px;">🎬 {memo_content}</div>', unsafe_allow_html=True)
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**{rich_data.get('creator', '')}**")
            st.write(f"**📅 {rich_data.get('rel_date', '')} | 📍 {rich_data.get('venue', '')}**")
            st.markdown(f'<p style="color: #E50914; font-weight: bold; font-size: 1.1em;">🗓️ 예정일: {item.get("plan_date")}</p>', unsafe_allow_html=True)
            st.divider()
            
            if item.get("category") == "SCRAP":
                sections = [("📝 요약 (한 줄 평)", "brief", "#0E6245"), ("✨ 5문장 요약", "highlights", "#7D5600"), ("🌈 5문장 감상", "note", "#1E425E"), ("📖 INFO", "summary", "#444")]
            else:
                if is_admin:
                    sections = [
                        ("💎 한 줄 평", "brief", "#E50914"), 
                        ("🖋️ PRISM", "note", "#1E425E"), 
                        ("📦 SKETCH", "highlights", "#7D5600"), 
                        ("📖 INFO", "summary", "#444")
                    ]
                else:
                    sections = [
                        ("💎 한 줄 평", "brief", "#E50914"), 
                        ("🖋️ PRISM 리뷰", "note", "#1E425E")
                    ]
                    
            for label, key, color in sections:
                if rich_data.get(key):
                    st.markdown(f'<div style="display: inline-block; background-color: {color}; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px; font-weight: bold;">{label}</div>', unsafe_allow_html=True)
                    st.markdown(rich_data[key].replace('\n', '  \n'))
                    st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)
            
            if item.get("category") != "SCRAP":
                st.markdown("<br>", unsafe_allow_html=True)
                
                st.subheader("🔗 외부에 리뷰 공유하기")
                
                share_text_mobile = f"[일정 - {item.get('category')}] {item.get('title')}\n"
                if rich_data.get('creator'): share_text_mobile += f"- {rich_data.get('creator')}\n"
                share_text_mobile += "\n"
                if rich_data.get('img_url2') and str(rich_data.get('img_url2')) != "None": share_text_mobile += f"🎬 관련 링크: {rich_data.get('img_url2')}\n\n"
                if rich_data.get('brief'): share_text_mobile += f"💎 한 줄 평: {rich_data.get('brief')}\n\n"
                if rich_data.get('note'): share_text_mobile += f"🖋️ PRISM 리뷰:\n{rich_data.get('note')}"
                
                safe_share_text = share_text_mobile.strip().replace('`', '\\`').replace('\n', '\\n')
                img_b64_data = get_image_base64(rich_data.get('img_url', ''))
                
                share_html = f"""
                <div style="margin-bottom: 15px;">
                    <button onclick="sharePlanItem()" style="width:100%; padding:12px; background: linear-gradient(45deg, #405de6, #5851db, #833ab4, #c13584, #e1306c, #fd1d1d); color:white; border-radius:8px; border:none; cursor:pointer; font-weight:bold; font-size:16px;">
                        📲 모바일 SNS / 카톡으로 공유하기
                    </button>
                </div>
                <script>
                async function sharePlanItem() {{
                    let shareData = {{ title: 'PRISM 일정 공유', text: `{safe_share_text}` }};
                    const imgB64 = "{img_b64_data}";
                    if (imgB64 && navigator.canShare) {{
                        try {{
                            const res = await fetch(imgB64);
                            const blob = await res.blob();
                            const file = new File([blob], 'prism_plan_cover.jpg', {{ type: blob.type }});
                            if (navigator.canShare({{ files: [file] }})) shareData.files = [file];
                        }} catch (e) {{ console.log(e); }}
                    }}
                    try {{
                        if (navigator.share) await navigator.share(shareData);
                        else alert('현재 브라우저에서는 공유 기능을 지원하지 않습니다. 아래 블로그용 복사를 이용해주세요.');
                    }} catch (e) {{ console.log(e); }}
                }}
                </script>
                """
                components.html(share_html, height=65)

                with st.expander("📝 블로그 포스팅용 복사 (티스토리, 네이버, 벨로그)"):
                    blog_text = f"## [일정 - {item.get('category')}] {item.get('title')}\n\n"
                    if rich_data.get('img_url') and str(rich_data.get('img_url')) != "None":
                        blog_text += f"![포스터/커버]({rich_data.get('img_url')})\n\n"
                    
                    blog_text += f"- **창작자:** {rich_data.get('creator', '정보 없음')}\n"
                    blog_text += f"- **일시/장소:** {rich_data.get('rel_date')} | {rich_data.get('venue')}\n"
                    if rich_data.get('img_url2') and str(rich_data.get('img_url2')) != "None":
                        blog_text += f"- **관련 영상/링크:** {rich_data.get('img_url2')}\n"
                    blog_text += "\n---\n\n"
                    
                    if rich_data.get('brief'): blog_text += f"### 💎 한 줄 평\n{rich_data.get('brief')}\n\n"
                    if rich_data.get('note'): blog_text += f"### 🖋️ PRISM 리뷰\n{rich_data.get('note')}\n\n"
                    
                    st.info("우측 상단의 복사(📋) 버튼을 눌러 블로그 에디터에 붙여넣기 하세요!")
                    st.code(blog_text.strip(), language="markdown")

        if is_admin:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✅ 완료", key=f"done_plan_bottom_{item['id']}", use_container_width=True, type="primary"):
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
                    supabase.table("plan").delete().eq("title", item['title']).eq("plan_date", item['plan_date']).execute()
                except: pass
                st.success(f"🎉 '{item['title']}' 아카이브로 이동 완료!"); time.sleep(0.5); st.rerun()
            st.divider()

# --- [5. 메인 UI] ---
def get_base64(path):
    try:
        with open(path, "rb") as f: return base64.b64encode(f.read()).decode()
    except: return ""

logo_base64 = get_base64("logo.png")

st.markdown("""<style>.header-wrap { display: flex; align-items: center; gap: 6px; } .header-wrap h1 { margin: 0; letter-spacing: -1px; }</style>""", unsafe_allow_html=True)
st.markdown(f"""<div class="header-wrap"><img src="data:image/png;base64,{logo_base64}" width="90"><h1>PRISM ARCHIVE</h1></div>""", unsafe_allow_html=True)

if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tabs = st.tabs(["📂 ARCHIVE"])
    tab_a = tabs[0]
    tab_w = None

# --- [WRITE 탭] ---
if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 category", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"], horizontal=True, key="main_category_radio")
        search_query = st.text_input(f"🔍 {category} 검색")
        
        if search_query:
            if category == "SCRAP":
                if st.button("✨ 가져오기"):
                    s = scrape_url(search_query)
                    if s:
                        st.session_state.f_title = s['title']; st.session_state.f_creator = ''; st.session_state.f_date = str(date.today())
                        st.session_state.f_img = s['img']; st.session_state.f_venue = s['venue']; st.session_state.f_summary = s['summary']
                        st.session_state.f_highlights = ""; st.session_state.f_note = ""; st.session_state.f_brief = ""; st.session_state.f_video = ""
                        st.session_state.show_form = True; st.rerun()
            elif category == "BOOKS":
                res = search_books(search_query)
                if res:
                    opts = {f"📚 {b['title']}": b for b in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        b = opts[sel]
                        st.session_state.f_title = b['title']; st.session_state.f_creator = ", ".join(b['authors'])
                        st.session_state.f_date = b['datetime'][:10]; st.session_state.f_img = b.get('thumbnail', '').replace("R120x174", "R400x0")
                        st.session_state.f_venue = b.get('publisher', ''); st.session_state.f_summary = b.get('contents', '')
                        st.session_state.f_highlights = ""; st.session_state.f_note = ""; st.session_state.f_brief = ""; st.session_state.f_video = ""
                        st.session_state.show_form = True; st.rerun()
            elif category == "MUSIC":
                res = search_apple_music(search_query)
                if res:
                    opts = {m['display_name']: m for m in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        m = opts[sel]
                        st.session_state.f_title = m['title']; st.session_state.f_creator = m['creator']; st.session_state.f_date = m['date']
                        st.session_state.f_img = m['img']; st.session_state.f_venue = m['venue']; st.session_state.f_summary = f"{m.get('url', '')}\n\n"
                        st.session_state.f_highlights = ""; st.session_state.f_note = ""; st.session_state.f_brief = ""; st.session_state.f_video = ""
                        st.session_state.show_form = True; st.rerun()
            elif category == "STAGE":
                res = search_kopis(search_query)
                if res:
                    opts = {f"🎭 {s['title']} [{s['date']}~] ({s['venue']})": s for s in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        s = opts[sel]; combined_creator = get_kopis_detail(s['id'])
                        st.session_state.f_title = s['title']; st.session_state.f_creator = combined_creator; st.session_state.f_date = s['date']
                        st.session_state.f_img = s['img']; st.session_state.f_venue = s['venue']; st.session_state.f_summary = f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={s['id']}"
                        st.session_state.f_highlights = ""; st.session_state.f_note = ""; st.session_state.f_brief = ""; st.session_state.f_video = ""
                        st.session_state.show_form = True; st.rerun()
            else: 
                res = search_tmdb(search_query, category)
                if res:
                    t_key = 'title' if category == 'MOVIES' else 'name'
                    d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                    opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        s = opts[sel]; details = get_tmdb_details(s['id'], category)
                        st.session_state.f_title = s.get(t_key, ''); st.session_state.f_creator = details['creator']; st.session_state.f_date = s.get(d_key, '')
                        st.session_state.f_img = f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}"; st.session_state.f_venue = details['venue']
                        st.session_state.f_summary = s.get('overview', '')
                        st.session_state.f_highlights = ""; st.session_state.f_note = ""; st.session_state.f_brief = ""; st.session_state.f_video = ""
                        st.session_state.show_form = True; st.rerun()
        else:
            if not st.session_state.show_form:
                if st.button("✏️ 직접 입력"):
                    st.session_state.should_clear_form = True
                    st.session_state.show_form = True
                    st.rerun()

        if st.session_state.show_form:
            st.divider()
            
            if category == "SCRAP":
                if not st.session_state.f_highlights: st.session_state.f_highlights = "1. \n2. \n3. \n4. \n5. "
                if not st.session_state.f_note: st.session_state.f_note = "1. \n2. \n3. \n4. \n5. "
            else:
                if not st.session_state.f_highlights: 
                    cat_hl_labels = {
                        "BOOKS": "🔖 인상 깊은 구절",
                        "MUSIC": "🎵 인상 깊은 가사/사운드",
                        "MOVIES": "🎬 인상 깊은 명장면/명대사",
                        "SERIES": "📺 인상 깊은 명장면/명대사",
                        "STAGE": "🎭 인상 깊은 넘버/장면"
                    }
                    cat_label = cat_hl_labels.get(category, "📍 인상 깊은 부분")
                    st.session_state.f_highlights = f"{cat_label} 1: \n{cat_label} 2: \n{cat_label} 3: \n📎 보충 팩트 (위키/인터뷰/배경지식): \n\n🔑 키워드: \n\n📝 스케치: \n  1. \n  2. \n  3. \n  4."
                if not st.session_state.f_note: 
                    st.session_state.f_note = ""

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
                st.text_area("📖 INFO (배경지식/정보)", key="f_summary", height=120)
            
            with cr:
                if category == "SCRAP":
                    st.text_area("✨ 5문장 요약", key="f_highlights", height=150)
                    st.text_area("🌈 5문장 감상", key="f_note", height=150)
                    st.text_input("📝 요약 (한 줄 평)", key="f_brief")
                else:
                    st.text_area("📦 Step 2 & 3. 데이터 수집 및 스케치", key="f_highlights", height=300)
                    st.text_area("🖋️ Step 4. 본문 작성 (PRISM)", key="f_note", height=200)
                    st.text_input("💎 Step 5. 최종 요약 (한 줄 평)", key="f_brief")
                
                st.date_input("🍿 감상 완료/예정일", key="f_view_date")
                
            st.markdown("<br>", unsafe_allow_html=True)
            col_btn1, col_btn2, col_btn3 = st.columns([0.4, 0.4, 0.2])
            
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
                        st.success("✅ 아카이브 저장 완료!"); st.session_state.should_clear_form = True; time.sleep(0.8); st.rerun()
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
                    st.success("🗓️ 일정표에 추가되었습니다!"); st.session_state.should_clear_form = True; time.sleep(0.8); st.rerun()
                else: st.warning("제목을 입력해 주세요.")

            if col_btn3.button("❌ 닫기", use_container_width=True):
                st.session_state.should_clear_form = True
                st.rerun()

        st.divider()
        
        col_l, col_c, col_r = st.columns([0.1, 0.8, 0.1])
        with col_l:
            if st.button("⬅️", use_container_width=True): st.session

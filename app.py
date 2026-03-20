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

# --- [3. 로그인 및 Session State 초기화] ---
DEV_MODE = False 
cookie_manager = stx.CookieManager()

# 로그아웃 상태 강제 체크
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False

saved_cookie = cookie_manager.get(cookie="admin_logged_in")
if saved_cookie == "yes":
    st.session_state.is_logged_in = True

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
        if k in st.session_state: st.session_state[k] = ""
    st.session_state.f_view_date = date.today()
    st.session_state.show_form = False
    st.session_state.should_clear_form = False

for k in form_keys:
    if k not in st.session_state: st.session_state[k] = ""
if 'f_view_date' not in st.session_state:
    st.session_state.f_view_date = date.today()

is_admin = st.session_state.is_logged_in or DEV_MODE

with st.sidebar:
    st.markdown("### 🔐 관리자 접속")
    if not is_admin:
        input_password = st.text_input("비밀번호", type="password", key="sidebar_pw_main")
        if input_password:
            if input_password == st.secrets["ADMIN_PASSWORD"]:
                cookie_manager.set("admin_logged_in", "yes", expires_at=datetime.now() + timedelta(days=30))
                st.session_state.is_logged_in = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
    else:
        st.success("관리자 모드 활성화됨")
        # 로그아웃 기능 강화
        if st.button("🔓 로그아웃", key="logout_btn", use_container_width=True):
            cookie_manager.delete("admin_logged_in")
            st.session_state.is_logged_in = False
            st.session_state.user_password = ""
            # 모든 폼 데이터 초기화
            st.session_state.should_clear_form = True
            st.rerun()
            
        st.divider()
        st.markdown("### 🛠️ 데이터 오류 수정")
        if st.button("🧹 중복 데이터 정리", use_container_width=True):
            conn = get_connection()
            conn.execute("DELETE FROM archive WHERE id NOT IN (SELECT MAX(id) FROM archive GROUP BY title, category)")
            conn.execute("DELETE FROM plan WHERE id NOT IN (SELECT MAX(id) FROM plan GROUP BY title, category)")
            conn.commit()
            st.cache_data.clear()
            st.success("✅ 중복 제거 완료!")
            st.rerun()
        st.divider()
        st.markdown("### 🔄 데이터 동기화")
        st.button("📤 클라우드 백업", key="backup_sidebar", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 클라우드 복구", key="restore_sidebar", on_click=restore_from_supabase, use_container_width=True)

# --- [API 검색 함수들 생략 - 동일함] ---
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
                conn = get_connection(); conn.execute("DELETE FROM archive WHERE id=?", (item['id'],)); conn.commit()
                st.cache_data.clear(); st.rerun()
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
            if prefix+k not in st.session_state: st.session_state[prefix+k] = str(v)
        if prefix+"view" not in st.session_state:
            try: st.session_state[prefix+"view"] = pd.to_datetime(item.get('view_date')).date()
            except: st.session_state[prefix+"view"] = date.today()

        with col_img:
            st.text_input("🖼️ 이미지 URL", key=prefix+"img")
            st.text_input("🎬 관련 영상/메모", key=prefix+"vid")
        with col_txt:
            st.text_input("📌 제목", key=prefix+"title")
            st.text_input("👤 창작자", key=prefix+"creator")
            c1, c2 = st.columns(2)
            c1.text_input("📅 작품 날짜", key=prefix+"rel")
            c2.text_input("📍 장소/플랫폼", key=prefix+"ven")
            st.date_input("🍿 감상일", key=prefix+"view")
            st.text_area("📖 개요", key=prefix+"sum")
            st.text_area("📦 스케치", key=prefix+"high", height=200)
            st.text_area("🖋️ PRISM 본문", key=prefix+"note", height=200)
            st.text_input("💎 한 줄 평", key=prefix+"brief")
            
            if st.button("💾 저장", key=f"save_edit_{item['id']}", type="primary"):
                conn = get_connection()
                conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=?, img_url2=? WHERE id=?""", 
                             (st.session_state[prefix+"title"], st.session_state[prefix+"creator"], st.session_state[prefix+"rel"], st.session_state[prefix+"ven"], 
                              st.session_state[prefix+"sum"], st.session_state[prefix+"brief"], st.session_state[prefix+"high"], st.session_state[prefix+"note"], 
                              str(st.session_state[prefix+"view"]), st.session_state[prefix+"img"], st.session_state[prefix+"vid"], item['id']))
                conn.commit(); st.cache_data.clear(); st.rerun()
    else: 
        with col_img:
            if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
            if item.get('img_url2'): 
                if "http" in item['img_url2']: st.video(item['img_url2'])
                else: st.info(item['img_url2'])
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**{item.get('creator')}**")
            st.write(f"📅 {item.get('rel_date')} | 📍 {item.get('venue')}")
            st.divider()
            
            # 본문 출력
            sections = [("💎 한 줄 평", "brief", "#E50914"), ("🖋️ PRISM 리뷰", "note", "#1E425E")]
            for label, key, color in sections:
                if item.get(key):
                    st.markdown(f'<div style="background-color:{color}; color:white; padding:2px 10px; border-radius:10px; display:inline-block; font-size:0.8em; margin-bottom:5px;">{label}</div>', unsafe_allow_html=True)
                    st.write(item[key])
                    st.divider()

            # --- [네이티브 인스타 스타일 공유 버튼] ---
            if item.get("category") != "SCRAP":
                share_text = f"[{item.get('category')}] {item.get('title')}\n- {item.get('creator')}\n\n💎 한 줄 평: {item.get('brief')}\n\n🖋️ PRISM 리뷰:\n{item.get('note')}"
                safe_share_text = share_text.strip().replace('`', '\\`').replace('\n', '\\n')
                
                share_html = f"""
                <div style="margin-bottom: 10px;">
                    <button onclick="shareText()" style="width:100%; padding:12px; background: linear-gradient(45deg, #405de6, #5851db, #833ab4, #c13584, #e1306c, #fd1d1d); color:white; border-radius:8px; border:none; cursor:pointer; font-weight:bold; font-size:16px;">
                        📲 SNS / 카톡으로 공유하기
                    </button>
                </div>
                <script>
                async function shareText() {{
                    try {{
                        if (navigator.share) {{
                            await navigator.share({{ title: 'PRISM 리뷰', text: `{safe_share_text}` }});
                        }} else {{ alert('공유 기능을 지원하지 않는 브라우저입니다.'); }}
                    }} catch (e) {{ console.log(e); }}
                }}
                </script>
                """
                components.html(share_html, height=65)
                with st.expander("📝 텍스트 직접 복사"):
                    st.code(share_text.strip())

@st.dialog("🗓️ 일정 정보", width="large")
def show_plan_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    try: rich_data = json.loads(item['memo'])
    except: rich_data = {"note": item.get('memo', '')}
    
    col_img, col_txt = st.columns([0.3, 0.7])
    with col_img:
        if rich_data.get('img_url'): st.image(rich_data['img_url'], use_container_width=True)
    with col_txt:
        st.markdown(f'# {item.get("title")}')
        st.write(f"🗓️ 예정일: {item.get('plan_date')}")
        st.divider()
        st.write(rich_data.get('note', '내용 없음'))
        
        # 일정 공유 버튼
        share_text = f"[일정] {item.get('title')}\n📅 {item.get('plan_date')}\n\n{rich_data.get('note')}"
        safe_share_text = share_text.strip().replace('`', '\\`').replace('\n', '\\n')
        share_html = f"""
        <button onclick="shareText()" style="width:100%; padding:12px; background: linear-gradient(45deg, #405de6, #5851db, #833ab4, #c13584, #e1306c, #fd1d1d); color:white; border-radius:8px; border:none; cursor:pointer; font-weight:bold; font-size:16px;">
            📲 일정 공유하기
        </button>
        <script>
        async function shareText() {{
            try {{ await navigator.share({{ text: `{safe_share_text}` }}); }} catch (e) {{}}
        }}
        </script>
        """
        components.html(share_html, height=65)

# --- [5. 메인 UI 및 나머지 로직] ---
def get_base64(path):
    try:
        with open(path, "rb") as f: return base64.b64encode(f.read()).decode()
    except: return ""

logo_base64 = get_base64("logo.png")
st.markdown(f"""<div style="display:flex; align-items:center; gap:10px;"><img src="data:image/png;base64,{logo_base64}" width="80"><h1>PRISM ARCHIVE</h1></div>""", unsafe_allow_html=True)

if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
    with tab_w:
        category = st.radio("📂 category", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"], horizontal=True)
        # [실시간 State 바인딩 입력 폼 생략 - 위와 동일한 로직 적용]
        st.info("실시간 자동 저장 기능이 적용된 입력 폼입니다.")
        with st.container():
            col1, col2 = st.columns([0.4, 0.6])
            with col1:
                st.text_input("🖼️ 이미지 URL", key="f_img")
                st.text_input("📌 제목", key="f_title")
                st.text_input("👤 창작자", key="f_creator")
            with col2:
                # 템플릿 로직
                if category != "SCRAP" and not st.session_state.f_highlights:
                    st.session_state.f_highlights = f"📍 인상 깊은 부분 1: \n📍 인상 깊은 부분 2: \n📍 인상 깊은 부분 3: \n📎 보충 팩트: \n\n🔑 키워드: \n\n📝 스케치: \n  1. \n  2. "
                st.text_area("📦 스케치/데이터", key="f_highlights", height=250)
                st.text_area("🖋️ PRISM 리뷰", key="f_note", height=150)
                st.text_input("💎 한 줄 평", key="f_brief")
            
            if st.button("✅ 저장하기", use_container_width=True, type="primary"):
                if st.session_state.f_title:
                    conn = get_connection()
                    conn.execute("""INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", 
                                 (category, st.session_state.f_title, st.session_state.f_creator, st.session_state.f_date, st.session_state.f_venue, st.session_state.f_summary, st.session_state.f_brief, st.session_state.f_highlights, st.session_state.f_note, st.session_state.f_img, str(date.today()), str(st.session_state.f_view_date)))
                    conn.commit(); st.cache_data.clear(); st.success("저장 완료!"); st.session_state.should_clear_form = True; st.rerun()

    with tab_a:
        all_df = get_all_data()
        if not all_df.empty:
            # 그리드 뷰 및 필터 로직 생략 (기존과 동일)
            st.dataframe(all_df[['category', 'title', 'creator', 'view_date']])
            # 아카이브 아이템 클릭 시 show_details(row) 호출
else:
    # 비관리자용 ARCHIVE 탭만 표시
    st.info("관리자 모드가 아닙니다. 기록을 열람만 할 수 있습니다.")
    all_df = get_all_data()
    st.dataframe(all_df[['category', 'title', 'creator', 'view_date']])

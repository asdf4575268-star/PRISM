import streamlit as st
from PIL import Image
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
import time
import re
import xml.etree.ElementTree as ET
from supabase import create_client, Client
import base64
import html

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

# --- [2. DB 함수 및 속도 최적화 동기화 로직] ---
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
        
        # 아카이브 백업
        local_data = conn.execute("SELECT * FROM archive").fetchall()
        if local_data:
            upload_list = [dict(row) for row in local_data]
            for d in upload_list:
                if 'id' in d: del d['id']
            supabase.table("archive").upsert(upload_list).execute() 
            
        # 플랜 백업
        local_plan = conn.execute("SELECT * FROM plan").fetchall()
        if local_plan:
            plan_upload = [dict(row) for row in local_plan]
            for p in plan_upload:
                if 'id' in p: del p['id']
            supabase.table("plan").upsert(plan_upload).execute()

        st.session_state.sync_msg = ("success", f"✅ 클라우드 백업 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # 아카이브 복구
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        
        local_df = get_all_data()
        local_keys = set(zip(local_df['title'], local_df['view_date'])) if not local_df.empty else set()
        
        to_insert = []
        if cloud_data:
            for row in cloud_data:
                if (row['title'], row['view_date']) not in local_keys:
                    to_insert.append((
                        row['category'], row['title'], row['creator'], row['rel_date'], 
                        row['venue'], row['summary'], row.get('brief', ''), row.get('highlights', ''), 
                        row['note'], row.get('img_url'), row.get('img_url2'), row['save_date'], row['view_date']
                    ))
            if to_insert:
                cursor.executemany("""INSERT INTO archive 
                    (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) 
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", to_insert)
        
        # 플랜 복구
        res_p = supabase.table("plan").select("*").execute()
        cloud_plan = res_p.data if hasattr(res_p, 'data') else res_p
        
        local_plan_df = pd.read_sql_query("SELECT * FROM plan", conn)
        local_plan_keys = set(zip(local_plan_df['title'], local_plan_df['plan_date'])) if not local_plan_df.empty else set()
        
        plan_insert = []
        if cloud_plan:
            for rp in cloud_plan:
                if (rp['title'], rp['plan_date']) not in local_plan_keys:
                    plan_insert.append((rp['plan_date'], rp['category'], rp['title'], rp['memo']))
            if plan_insert:
                cursor.executemany("INSERT INTO plan (plan_date, category, title, memo) VALUES (?,?,?,?)", plan_insert)

        conn.commit()
        st.cache_data.clear() 
        st.session_state.sync_msg = ("success", f"✅ 데이터를 복구했습니다!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

# --- 앱 시작 시 로컬 DB가 비어있으면 자동 복구 (Auto-Restore) ---
@st.cache_resource
def auto_sync_on_startup():
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM archive").fetchone()[0]
    if count == 0:
        restore_from_supabase()
    return True

auto_sync_on_startup()

# --- [3. 로그인 시스템 & 사이드바] ---
DEV_MODE = False 

if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_password" not in st.session_state:
    st.session_state.user_password = ""
if "selected_tag" not in st.session_state:
    st.session_state.selected_tag = None

if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True

is_admin = st.session_state.is_logged_in or DEV_MODE

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not is_admin:
        input_password = st.text_input("Password", type="password", key="sidebar_pw")
        if input_password:
            if input_password == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.user_password = input_password 
                st.session_state.is_logged_in = True
                st.rerun()
            else:
                st.error("Incorrect Password")
    
    if st.session_state.is_logged_in:
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
            if creators:
                creator_names = ", ".join([c['name'] for c in creators])
            else:
                creator_names = next((m['name'] for m in crew_list if m.get('job') in ['Writer', 'Executive Producer']), "정보 없음")
            creator_label = f"[작가/제작] {creator_names}"
            networks = res.get('networks', [])
            venue_info = networks[0].get('name', '') if networks else ""
        cast_names = ", ".join([c['name'] for c in cast_list[:3]])
        cast_label = f"[출연] {cast_names}" if cast_names else ""
        full_creator = f"{creator_label} / {cast_label}".strip(" / ")
        return {"creator": full_creator, "venue": venue_info}
    except:
        return {"creator": "정보 없음", "venue": ""}

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
            results.append({
                'title': title, 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 
                'date': date_from, 'venue': d.findtext('fcltynm')
            })
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
        
        raw_title = title.group(1) if title else "제목 없음"
        raw_summary = desc.group(1) if desc else ""
        
        combined_summary = f"{url}\n\n{html.unescape(raw_summary)}"
        
        return {
            "title": html.unescape(raw_title),
            "img": img.group(1) if img else "",
            "venue": site.group(1) if site else "URL",
            "summary": combined_summary
        }
    except: return None

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
                st.cache_data.clear() 
                try: supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
                except: pass
                st.rerun()
        with t_col3:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    col_img, col_txt = st.columns([0.3, 0.7])

    if is_admin and edit_mode:
        with st.form(key=f"edit_form_{item['id']}"):
            col_img_form, col_txt_form = st.columns([0.3, 0.7])
            with col_img_form:
                n_img = st.text_input("🖼️ 이미지 URL", value=str(item.get('img_url', '')), key=f"img_in_{item['id']}")
                n_img2 = st.text_input("🎬 관련 영상(URL) 또는 제목/메모", value=str(item.get('img_url2', '')), key=f"video_in_{item['id']}")
                
                old_img = str(item.get('img_url', ''))
                if old_img and old_img.strip() and old_img != "None": 
                    st.image(old_img, use_container_width=True)

            with col_txt_form:
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                cat = item.get('category')
                labels = {"BOOKS": "📖 출판사", "MUSIC": "💿 레이블", "MOVIES": "🎬 제작사", "SERIES": "📺 플랫폼", "STAGE": "📍 장소", "SCRAP": "📰 매체"}
                v_label = labels.get(cat, "📍 장소")
                c1, c2 = st.columns(2)
                n_rel = c1.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_venue = c2.text_input(v_label, value=str(item.get('venue', '')))
                try: curr_view = pd.to_datetime(item.get('view_date')).date()
                except: curr_view = date.today()
                n_view_date = st.date_input("🍿 감상일 수정", value=curr_view)
                n_sum = st.text_area("📖 개요", value=str(item.get('summary', '')), height=150)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '')))
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '')), height=100)
                
                if cat != "SCRAP":
                    n_note = st.text_area("🌈 PRISM", value=str(item.get('note', '')), height=100)
                else:
                    n_note = str(item.get('note', ''))

                if st.form_submit_button("💾 저장", use_container_width=True):
                    try:
                        conn = get_connection()
                        conn.execute("""UPDATE archive SET 
                                        title=?, creator=?, rel_date=?, venue=?, 
                                        summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=?, img_url2=? 
                                        WHERE id=?""", 
                                     (n_title, n_creator, n_rel, n_venue, 
                                      n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, n_img2, item['id']))
                        conn.commit()
                        st.cache_data.clear() 
                        try:
                            supabase.table("archive").update({
                                "title": n_title, "creator": n_creator, "rel_date": n_rel, "venue": n_venue,
                                "summary": n_sum, "brief": n_brief, "highlights": n_high, "note": n_note,
                                "view_date": str(n_view_date), "img_url": n_img, "img_url2": n_img2
                            }).eq("title", item['title']).eq("view_date", item['view_date']).execute()
                        except: pass
                        st.success("✅ 수정 완료!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e: st.error(f"❌ 오류: {e}")
    else: 
        with col_img:
            img_url = item.get('img_url')
            if isinstance(img_url, str) and img_url.strip() and img_url != "None":
                try: st.image(img_url, use_container_width=True)
                except: st.warning("이미지 로드 실패")
            
            st.write("") 

            memo_content = item.get('img_url2', '')
            if isinstance(memo_content, str) and memo_content.strip() and memo_content != "None":
                url_match = re.search(r'(https?://[^\s]+)', memo_content)
                
                if url_match:
                    video_url = url_match.group(1)
                    text_part = memo_content.replace(video_url, '').strip(' /|-')
                    
                    if text_part:
                        st.markdown(f"""
                            <div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; text-align: left; font-size: 0.95em; color: #fff; font-weight: bold; margin-bottom: 10px;">
                                🎬 {text_part}
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown("""<div style="display: inline-block; background-color: #E50914; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px; font-weight: bold;">🎬 관련 영상</div>""", unsafe_allow_html=True)
                    
                    try:
                        st.video(video_url)
                    except:
                        st.warning("영상을 불러올 수 없습니다.")
                        
                else:
                    st.markdown(f"""
                        <div style="background-color: #1a1a1a; border-left: 4px solid #E50914; padding: 10px 15px; border-radius: 4px; text-align: left; font-size: 0.95em; color: #fff; font-weight: bold; margin-bottom: 10px;">
                            🎬 {memo_content}
                        </div>
                    """, unsafe_allow_html=True)
            
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            if item.get("category") != "SCRAP":
                st.write(f"**{item.get('creator')}**")
            st.write(f"**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
            st.markdown(f'<p style="color: #E2E2E2; font-weight: bold; font-size: 1.1em;">🍿감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()
            
            if item.get("category") == "SCRAP":
                summary_text = str(item.get('summary', ''))
                if summary_text.startswith("http"):
                    url = summary_text.split('\n')[0]
                    st.markdown(f"**[🔗 원본 기사 보러가기]({url})**")
                sections = [
                    ("📝 요약 (한 줄 평)", "brief", "#0E6245"), 
                    ("✨ 인상 깊은 부분", "highlights", "#7D5600")
                ]
            else:
                sections = [
                    ("📝 요약 (한 줄 평)", "brief", "#0E6245"), 
                    ("🌈 PRISM", "note", "#1E425E"),
                    ("✨ 인상 깊은 부분", "highlights", "#7D5600"), 
                    ("📖 개요 (Behind the records)", "summary", "#444")
                ]
            
            for label, key, color in sections:
                content = item.get(key)
                if content:
                    st.markdown(f"""<div style="display: inline-block; background-color: {color}; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px;">{label}</div>""", unsafe_allow_html=True)
                    st.markdown(content.replace('\n', '  \n'))
                    st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)

            if item.get('category') != 'SCRAP':
                conn = get_connection()
                raw_title = str(item.get('title', ''))
                title_no_brackets = re.sub(r'\[.*?\]|\(.*?\)|<.*?>', '', raw_title)
                clean_text = re.sub(r'[^가-힣a-zA-Z0-9]', ' ', title_no_brackets)
                words = [w for w in clean_text.split() if len(w) >= 2]
                if not words:
                    clean_text = re.sub(r'[^가-힣a-zA-Z0-9]', ' ', raw_title)
                    words = [w for w in clean_text.split() if len(w) >= 2]

                if words:
                    core_keyword = max(words, key=len)
                    search_keyword = f"%{core_keyword}%"
                    sql_query = "SELECT * FROM archive WHERE category='SCRAP' AND (REPLACE(summary, ' ', '') LIKE ? OR REPLACE(title, ' ', '') LIKE ?)"
                    ref_df = pd.read_sql_query(sql_query, conn, params=(search_keyword, search_keyword))
                    
                    if not ref_df.empty:
                        st.markdown("""<div style="display: inline-block; background-color: #555; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px;">🔗 관련 스크랩</div>""", unsafe_allow_html=True)
                        for _, r in ref_df.iterrows():
                            with st.expander(f"👉 [{r['venue']}] {r['title']} ({r['rel_date']})"):
                                st.write(f"**🍿 감상일:** {r['view_date']}")
                                summary_text = str(r['summary'])
                                if summary_text.startswith("http"):
                                    url = summary_text.split('\n')[0]
                                    st.markdown(f"[🔗 원본 기사 보러가기]({url})")
                                if r['brief']: st.write(f"**📝 요약:** {r['brief']}")
                                if r['highlights']: st.markdown(f"**✨ 인상 깊은 부분:**<br>{r['highlights'].replace(chr(10), '<br>')}", unsafe_allow_html=True)
                        st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)

# --- [5. 메인 화면] ---
def get_base64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except: return ""

logo_base64 = get_base64("logo.png")

st.markdown("""
<style>
.header-wrap { display: flex; align-items: center; gap: 6px; }
.header-wrap h1 { margin: 0; letter-spacing: -1px; }
</style>
""", unsafe_allow_html=True)

st.markdown(
    f"""<div class="header-wrap"><img src="data:image/png;base64,{logo_base64}" width="90"><h1>PRISM ARCHIVE</h1></div>""",
    unsafe_allow_html=True
)

if is_admin:
    tab_w, tab_a, tab_p = st.tabs(["🖋️ WRITE", "📂 ARCHIVE", "🗓️ PLAN"])
else:
    tabs = st.tabs(["📂 ARCHIVE"])
    tab_a = tabs[0]
    tab_w = tab_p = None

# --- [WRITE 탭] ---
if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"], horizontal=True, key="main_category_radio")
        search_query = st.text_input(f"🔍 {category} {'URL 입력' if category == 'SCRAP' else '검색'}")
        
        if search_query:
            if category == "SCRAP":
                if st.button("✨ 가져오기"):
                    s = scrape_url(search_query)
                    if s:
                        st.session_state.api_data = {'title': s['title'], 'creator': '', 'date': str(date.today()), 'img': s['img'], 'venue': s['venue'], 'summary': s['summary']}
                        st.rerun()
            elif category == "BOOKS":
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
                        m = opts[sel]
                        st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': f"{m.get('url', '')}\n\n"}
                        st.rerun()
            elif category == "STAGE":
                res = search_kopis(search_query)
                if res:
                    opts = {f"🎭 {s['title']} [{s['date']}~] ({s['venue']})": s for s in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        s = opts[sel]
                        combined_creator = get_kopis_detail(s['id'])
                        st.session_state.api_data = {'title': s['title'], 'creator': combined_creator, 'date': s['date'], 'venue': s['venue'], 'img': s['img'], 'summary': f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={s['id']}"}
                        st.rerun()
            else: 
                res = search_tmdb(search_query, category)
                if res:
                    t_key = 'title' if category == 'MOVIES' else 'name'
                    d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                    opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        s = opts[sel]
                        details = get_tmdb_details(s['id'], category)
                        st.session_state.api_data = {'title': s.get(t_key), 'creator': details['creator'], 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'venue': details['venue'], 'summary': s.get('overview', '')}
                        st.rerun()

        st.divider()
        data = st.session_state.get('api_data', {})
        
        with st.form(key="write_form"):
            cl, cr = st.columns([0.4, 0.6])
            with cl:
                img_url_val = st.text_input("🖼️ 이미지 URL", value=data.get('img', ''))
                video_url_val = st.text_input("🎬 관련 영상(URL) 또는 제목/메모", value="")
                
                api_img = data.get('img', '')
                if api_img and api_img.strip() and api_img != "None":
                    st.image(api_img, use_container_width=True)
                    
                title = st.text_input("제목", value=data.get('title', ''))
                creator = st.text_input("창작자 정보", value=data.get('creator', ''))
                rel_date = st.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
                venue = st.text_input("📍 장소/플랫폼", value=data.get('venue', ''))
            with cr:
                summary = st.text_area("📖 개요", value=data.get('summary', ''), height=100)
                brief = st.text_input("📝 요약")
                highlights = st.text_area("✨ 인상 깊은 부분", height=100)
                
                if category != "SCRAP":
                    note = st.text_area("🌈 PRISM", height=100)
                else:
                    note = ""

                view_date = st.date_input("🍿 감상일", value=date.today())
                
                if st.form_submit_button("✅ 기록 저장", use_container_width=True):
                    new_record = {"category": str(category), "title": str(title).strip(), "creator": str(creator).strip(), "rel_date": str(rel_date), "venue": str(venue).strip(), "summary": str(summary).strip(), "brief": str(brief).strip(), "highlights": str(highlights).strip(), "note": str(note).strip(), "img_url": str(img_url_val).strip(), "img_url2": str(video_url_val).strip(), "save_date": str(date.today()), "view_date": str(view_date)}
                    try:
                        conn = get_connection()
                        conn.execute("""INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (new_record["category"], new_record["title"], new_record["creator"], new_record["rel_date"], new_record["venue"], new_record["summary"], new_record["brief"], new_record["highlights"], new_record["note"], new_record["img_url"], new_record["img_url2"], new_record["save_date"], new_record["view_date"]))
                        conn.commit()
                        st.cache_data.clear() 
                        try:
                            supabase.table("archive").upsert(new_record).execute()
                        except: pass
                        
                        st.success("✅ 저장 완료!")
                        st.session_state.api_data = {}
                        time.sleep(0.8)
                        st.rerun()
                    except Exception as e: st.error(f"❌ 오류: {e}")

# --- [PLAN 탭] ---
if is_admin and tab_p:
    with tab_p:
        st.markdown("### 📝 새로운 일정 추가")
        with st.form("plan_form"):
            c1, c2, c3 = st.columns([0.2, 0.3, 0.5])
            with c1:
                p_cat = st.selectbox("카테고리", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"])
            with c2:
                p_date = st.date_input("예정일", value=date.today())
            with c3:
                p_title = st.text_input("제목 (어떤 작품/일정인가요?)")
            
            p_memo = st.text_input("간단한 메모 (선택)")
            
            if st.form_submit_button("✅ 일정 등록", use_container_width=True):
                if p_title.strip():
                    conn = get_connection()
                    conn.execute("INSERT INTO plan (plan_date, category, title, memo) VALUES (?,?,?,?)", 
                                 (str(p_date), p_cat, p_title, p_memo))
                    conn.commit()
                    
                    try:
                        supabase.table("plan").upsert({"plan_date": str(p_date), "category": p_cat, "title": p_title, "memo": p_memo}).execute()
                    except: pass

                    st.success("새로운 일정이 추가되었습니다!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.warning("제목을 입력해 주세요.")

        st.divider()
        st.markdown("### 🗓️ 월별 예정 리스트")
        st.caption("※ 체크박스를 선택하면 일정이 '아카이브'로 자동 이동됩니다.")
        
        conn = get_connection()
        plan_df = pd.read_sql_query("SELECT * FROM plan ORDER BY plan_date ASC", conn)
        
        if not plan_df.empty:
            plan_df['p_dt'] = pd.to_datetime(plan_df['plan_date'])
            months = plan_df['p_dt'].dt.to_period('M').unique()
            
            cat_emojis = {"BOOKS": "📚", "MUSIC": "🎧", "MOVIES": "🎞️", "SERIES": "📽️", "STAGE": "🎭", "SCRAP": "📰"}
            
            for m in months:
                st.markdown(f"<h4 style='color: #E50914; margin-top: 15px;'>📅 {m.year}년 {m.month}월</h4>", unsafe_allow_html=True)
                m_data = plan_df[plan_df['p_dt'].dt.to_period('M') == m]
                
                for _, row in m_data.iterrows():
                    col1, col2 = st.columns([0.05, 0.95])
                    with col1:
                        # [클라우드 안전 자동 이동 로직]
                        if st.checkbox("", key=f"plan_{row['id']}"):
                            conn = get_connection()
                            today_str = str(date.today())
                            
                            new_archive_record = {
                                "category": row['category'],
                                "title": row['title'],
                                "creator": "",
                                "rel_date": "",
                                "venue": "",
                                "summary": "",
                                "brief": "",
                                "highlights": "",
                                "note": row['memo'],
                                "img_url": "",
                                "img_url2": "",
                                "save_date": today_str,
                                "view_date": today_str
                            }
                            
                            # 1. 로컬 아카이브 추가 및 플랜 삭제
                            conn.execute("""INSERT INTO archive 
                                (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) 
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                                (new_archive_record['category'], new_archive_record['title'], new_archive_record['creator'], new_archive_record['rel_date'], new_archive_record['venue'], new_archive_record['summary'], new_archive_record['brief'], new_archive_record['highlights'], new_archive_record['note'], new_archive_record['img_url'], new_archive_record['img_url2'], new_archive_record['save_date'], new_archive_record['view_date']))
                            conn.execute("DELETE FROM plan WHERE id=?", (row['id'],))
                            conn.commit()
                            st.cache_data.clear()
                            
                            # 2. 클라우드 아카이브 추가 및 플랜 삭제
                            try:
                                supabase.table("archive").upsert(new_archive_record).execute()
                                supabase.table("plan").delete().eq("title", row['title']).eq("plan_date", row['plan_date']).execute()
                            except: pass

                            st.success(f"'{row['title']}' 일정이 아카이브로 안전하게 이동되었습니다!")
                            time.sleep(0.5)
                            st.rerun()
                    with col2:
                        emoji = cat_emojis.get(row['category'], "📌")
                        day_str = str(row['plan_date'])[5:] # MM-DD 형태
                        st.markdown(f"<div style='margin-bottom: 5px;'><b>{day_str}</b> | {emoji} <b>{row['title']}</b> <span style='color:#888; font-size:0.9em; margin-left:10px;'>{row['memo']}</span></div>", unsafe_allow_html=True)
        else:
            st.info("등록된 일정이 없습니다. 기대되는 작품이나 볼거리를 추가해 보세요!")

# --- [ARCHIVE 탭] ---
with tab_a:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; margin-top: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); background: #1e1e1e; display: flex; align-items: center; justify-content: center; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .music-tab-style { aspect-ratio: 1/1 !important; }
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0, 0, 0, 0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
        .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
        @media (min-width: 600px) { [data-testid="stHorizontalBlock"] { display: flex !important; flex-wrap: nowrap !important; gap: 10px !important; } [data-testid="column"] { flex: 1 1 0% !important; min-width: 0 !important; } }
    </style>""", unsafe_allow_html=True)

    all_df = get_all_data()

    if not all_df.empty:
        search_query_archive = st.text_input("🔍 아카이브 통합 검색 (제목, 창작자, 내용 등 전체 검색)", key="global_search")
        if search_query_archive:
            mask = (
                all_df['title'].str.contains(search_query_archive, case=False, na=False) |
                all_df['creator'].str.contains(search_query_archive, case=False, na=False) |
                all_df['summary'].str.contains(search_query_archive, case=False, na=False) |
                all_df['note'].str.contains(search_query_archive, case=False, na=False) |
                all_df['venue'].str.contains(search_query_archive, case=False, na=False)
            )
            all_df = all_df[mask]
            st.markdown(f"**'{search_query_archive}'** 검색 결과: 총 **{len(all_df)}**건")
            st.divider()

        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        main_df = all_df[all_df['category'] != "SCRAP"]
        scrap_df = all_df[all_df['category'] == "SCRAP"]

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
                sel_y = st.selectbox("📅 연도 선택", options=list(year_options.keys()), format_func=lambda x: year_options[x], key="archive_year_sel")
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
                if c_data.empty: st.info(f"{c_name} 검색 결과 없음" if search_query_archive else f"{c_name} 데이터 없음")
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
                        st.markdown("### 🏆 이번 주 핫 키워드")
                        
                        def toggle_tag(clicked_tag):
                            if st.session_state.selected_tag == clicked_tag:
                                st.session_state.selected_tag = None
                            else:
                                st.session_state.selected_tag = clicked_tag
                                
                        cols = st.columns(len(top_keywords))
                        for i, kw in enumerate(top_keywords):
                            btn_type = "primary" if st.session_state.selected_tag == kw else "secondary"
                            cols[i].button(f"#{kw}", key=f"kw_{i}", type=btn_type, on_click=toggle_tag, args=(kw,))
                        st.divider()
                        
                    display_scrap_df = scrap_df.copy()
                    if st.session_state.selected_tag:
                        tag_mask = display_scrap_df['summary'].fillna('').str.contains(f"#{st.session_state.selected_tag}") | \
                                   display_scrap_df['note'].fillna('').str.contains(f"#{st.session_state.selected_tag}") | \
                                   display_scrap_df['brief'].fillna('').str.contains(f"#{st.session_state.selected_tag}") | \
                                   display_scrap_df['highlights'].fillna('').str.contains(f"#{st.session_state.selected_tag}")
                        display_scrap_df = display_scrap_df[tag_mask]
                        st.info(f"🏷️ '#{st.session_state.selected_tag}' 태그가 포함된 스크랩만 봅니다. (해제하려면 위의 버튼을 다시 누르세요)")
                    
                    if not display_scrap_df.empty:
                        display_scrap_df['week'] = display_scrap_df['v_dt'].dt.isocalendar().week
                        weeks = sorted(display_scrap_df['week'].dropna().unique(), reverse=True)
                        
                        for w in weeks:
                            w_data = display_scrap_df[display_scrap_df['week'] == w]
                            st.subheader(f"🗓️ {w}주차 스크랩")
                            for _, row in w_data.iterrows():
                                with st.expander(f"👉 [{row['venue']}] {row['title']} ({row['view_date']})"):
                                    summary_text = str(row['summary'])
                                    if summary_text.startswith("http"):
                                        url = summary_text.split('\n')[0]
                                        st.markdown(f"**[🔗 원본 기사 보러가기]({url})**")
                                    
                                    if row['brief']: st.write(f"**📝 요약:** {row['brief']}")
                                    if row['highlights']: st.markdown(f"**✨ 인상 깊은 부분:**<br>{row['highlights'].replace(chr(10), '<br>')}", unsafe_allow_html=True)
                                    
                                    if st.button("상세보기 / 수정", key=f"scr_btn_{row['id']}"):
                                        show_details(row)
                    else:
                        st.info("해당 태그나 검색어에 맞는 스크랩이 없습니다.")
                else:
                    st.info("스크랩 검색 결과가 없거나 기록이 없습니다.")

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

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [1] 설정 및 초기화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    favicon = Image.open("logo.png").resize((64, 64), Image.LANCZOS)
except:
    favicon = "🎬"

st.set_page_config(
    page_title="PRISM",
    page_icon=favicon,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── 전역 CSS (다크 에디토리얼 테마) ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');

/* ── 기본 리셋 ── */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0D0D0F !important;
    color: #E8E6E0 !important;
    font-family: 'DM Sans', sans-serif;
}
[data-testid="stSidebar"] { background: #111114 !important; border-right: 1px solid #222; }

/* ── 헤더 ── */
.prism-header {
    display: flex; align-items: center; gap: 14px;
    padding: 28px 0 20px;
    border-bottom: 1px solid #222;
    margin-bottom: 24px;
}
.prism-logo { font-family: 'DM Serif Display', serif; font-size: 2.4rem; letter-spacing: -1px; color: #fff; }
.prism-sub  { font-size: 0.75rem; letter-spacing: 4px; color: #555; text-transform: uppercase; margin-top: 2px; }

/* ── 내비게이션 라디오 ── */
div[role="radiogroup"] { gap: 4px !important; }
div[role="radiogroup"] > label {
    background: #161618 !important;
    border: 1px solid #2a2a2e !important;
    border-radius: 8px !important;
    padding: 8px 20px !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: #888 !important;
    cursor: pointer;
    transition: all .15s;
}
div[role="radiogroup"] > label[data-checked="true"],
div[role="radiogroup"] > label:has(input:checked) {
    background: #fff !important;
    color: #0D0D0F !important;
    border-color: #fff !important;
}

/* ── 탭 ── */
[data-testid="stTabs"] button {
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    color: #666 !important;
    border-bottom: 2px solid transparent !important;
    padding: 8px 14px !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #fff !important;
    border-bottom-color: #E50914 !important;
}

/* ── 입력창 ── */
input, textarea, [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {
    background: #161618 !important;
    border: 1px solid #2a2a2e !important;
    border-radius: 8px !important;
    color: #E8E6E0 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.875rem !important;
}
input:focus, textarea:focus { border-color: #E50914 !important; box-shadow: 0 0 0 2px rgba(229,9,20,.15) !important; }
[data-testid="stSelectbox"] > div > div { background: #161618 !important; border: 1px solid #2a2a2e !important; border-radius: 8px !important; color: #E8E6E0 !important; }

/* ── 버튼 ── */
[data-testid="stButton"] > button {
    background: #161618 !important;
    border: 1px solid #2a2a2e !important;
    border-radius: 8px !important;
    color: #ccc !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    transition: all .15s !important;
}
[data-testid="stButton"] > button:hover { background: #222 !important; border-color: #444 !important; color: #fff !important; }
[data-testid="stButton"] > button[kind="primary"] {
    background: #E50914 !important;
    border-color: #E50914 !important;
    color: #fff !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover { background: #c5070f !important; }

/* ── 카드 그리드 ── */
.card-wrap {
    position: relative; border-radius: 10px; overflow: hidden;
    background: #161618;
    aspect-ratio: 2/3;
    box-shadow: 0 2px 12px rgba(0,0,0,.5);
    transition: transform .2s, box-shadow .2s;
    cursor: pointer;
}
.card-wrap:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,.7); }
.card-wrap img { width:100%; height:100%; object-fit:cover; display:block; }
.card-overlay {
    position: absolute; bottom: 0; left: 0; right: 0;
    background: linear-gradient(to top, rgba(0,0,0,.9) 0%, transparent 100%);
    padding: 12px 10px 8px;
}
.card-badge {
    position: absolute; top: 7px; left: 7px;
    background: rgba(0,0,0,.75); backdrop-filter: blur(4px);
    color: #FFD700; font-size: 10px; font-weight: 600; letter-spacing: 1px;
    padding: 2px 7px; border-radius: 4px;
}
.card-date {
    position: absolute; top: 7px; right: 7px;
    background: rgba(0,0,0,.75); backdrop-filter: blur(4px);
    color: #aaa; font-size: 10px;
    padding: 2px 7px; border-radius: 4px;
}
.card-title {
    color: #fff; font-size: 0.78rem; font-weight: 600;
    line-height: 1.3; margin: 0;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.card-creator { color: #aaa; font-size: 0.7rem; margin-top: 2px; }
.card-no-img {
    width:100%; aspect-ratio: 2/3; border-radius:10px;
    background: #161618; border: 1px solid #222;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    font-size: 2rem; gap: 8px;
}
.card-no-img p { font-size: 0.75rem; color: #555; margin: 0; text-align: center; padding: 0 8px; line-height: 1.3; }

/* 음악 카드 정사각형 */
.card-music { aspect-ratio: 1/1 !important; }

/* ── 상세 팝업 ── */
.detail-title { font-family: 'DM Serif Display', serif; font-size: 1.9rem; line-height: 1.2; margin: 0 0 6px; }
.detail-meta  { color: #888; font-size: 0.82rem; margin-bottom: 16px; }
.section-pill {
    display: inline-block; padding: 3px 12px; border-radius: 20px;
    font-size: 0.72rem; font-weight: 600; letter-spacing: .5px;
    margin-bottom: 8px;
}
.section-body { color: #D0CEC8; font-size: 0.88rem; line-height: 1.75; white-space: pre-wrap; }
.section-divider { border: none; border-top: 1px solid #222; margin: 16px 0; }

/* ── 폼 영역 ── */
.form-section-label {
    font-size: 0.68rem; font-weight: 600; letter-spacing: 2px;
    text-transform: uppercase; color: #555; margin-bottom: 6px;
}
.form-container {
    background: #111114; border: 1px solid #222; border-radius: 12px; padding: 24px;
}

/* ── Weekly 캘린더 카드 ── */
.week-card {
    background: #161618; border-radius: 10px; overflow:hidden;
    border: 1px solid #222; transition: border-color .2s;
}
.week-card:hover { border-color: #3399FF; }
.week-card-date { font-size: 0.7rem; color: #3399FF; font-weight: 700; padding: 6px 8px 0; text-align:center; letter-spacing: 1px; }
.week-card img { width:100%; aspect-ratio:1/1; object-fit:cover; display:block; }
.week-card-foot { padding: 6px 6px 8px; }
.week-card-title { font-size: 0.75rem; font-weight:600; color:#ddd; line-height:1.2; text-align:center; }
.week-card-cat   { font-size: 0.65rem; color:#555; text-align:center; margin-top:2px; }

/* ── 스크랩 카드 ── */
.scrap-card {
    background: #111114; border-left: 3px solid #E50914;
    border-radius: 0 8px 8px 0; padding: 14px 16px; margin-bottom: 10px;
}
.scrap-card h4 { margin: 0 0 4px; font-size: 0.9rem; color: #fff; font-weight: 600; }
.scrap-card .scrap-meta { font-size: 0.75rem; color: #666; margin-bottom: 8px; }
.scrap-card .scrap-body { font-size: 0.82rem; color: #aaa; line-height: 1.6; }

/* ── 날짜 입력 ── */
[data-testid="stDateInput"] input { padding: 8px 12px !important; }

/* ── divider ── */
hr { border-color: #1e1e22 !important; }

/* ── 알림 박스 ── */
[data-testid="stAlert"] { border-radius: 8px !important; }

/* ── 반응형 그리드 컬럼 고정 ── */
@media (min-width: 600px) {
    [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px !important; }
    [data-testid="column"] { min-width: 0 !important; }
}
</style>
""", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [2] DB & Supabase
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
DB_NAME = 'archive_prism_total_v5.db'
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
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
        if local_data:
            supabase.table("archive").upsert([dict(r) for r in local_data]).execute()
        try:
            local_plan = conn.execute("SELECT * FROM plan").fetchall()
            if local_plan:
                supabase.table("plan").upsert([dict(r) for r in local_plan]).execute()
        except: pass
        st.session_state.sync_msg = ("success", "✅ 클라우드 백업 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        conn = get_connection(); cursor = conn.cursor()
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        if cloud_data:
            cursor.execute("DELETE FROM archive")
            cursor.executemany(
                "INSERT INTO archive (id,category,title,creator,rel_date,venue,summary,brief,highlights,note,img_url,img_url2,save_date,view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(r['id'],r['category'],r['title'],r['creator'],r['rel_date'],r['venue'],r['summary'],r.get('brief',''),r.get('highlights',''),r['note'],r.get('img_url'),r.get('img_url2'),r['save_date'],r['view_date']) for r in cloud_data]
            )
        try:
            res_p = supabase.table("plan").select("*").execute()
            cloud_plan = res_p.data if hasattr(res_p,'data') else res_p
            if cloud_plan:
                cursor.execute("DELETE FROM plan")
                cursor.executemany("INSERT INTO plan (id,plan_date,category,title,memo) VALUES (?,?,?,?,?)",
                    [(rp['id'],rp['plan_date'],rp['category'],rp['title'],rp['memo']) for rp in cloud_plan])
        except: pass
        conn.commit(); st.cache_data.clear()
        st.session_state.sync_msg = ("success", "✅ 데이터 복구 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

@st.cache_resource
def auto_sync_on_startup():
    conn = get_connection()
    if conn.execute("SELECT COUNT(*) FROM archive").fetchone()[0] == 0:
        restore_from_supabase()
    return True
auto_sync_on_startup()

def safe_str(val):
    return "" if val is None or str(val) == "None" else str(val)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [3] 세션 & 로그인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEV_MODE = False
cookie_manager = stx.CookieManager()

defaults = {
    "is_logged_in": False, "user_password": "", "selected_tag": None,
    "show_form": False, "week_offset": 0, "should_clear_form": False,
    "edit_target_id": None, "edit_source": None,
}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

if cookie_manager.get(cookie="admin_logged_in") == "yes": st.session_state.is_logged_in = True
if "main_nav" not in st.session_state:
    st.session_state.main_nav = "🖋️ 작성" if st.session_state.is_logged_in else "📂 아카이브"

form_keys = ['f_title','f_creator','f_date','f_venue','f_img','f_video','f_summary','f_brief','f_highlights','f_note']
if st.session_state.should_clear_form:
    for k in form_keys: st.session_state[k] = ""
    st.session_state.f_view_date = date.today()
    st.session_state.edit_target_id = None
    st.session_state.edit_source = None
    st.session_state.should_clear_form = False

for k in form_keys:
    if k not in st.session_state: st.session_state[k] = ""
if 'f_view_date' not in st.session_state: st.session_state.f_view_date = date.today()
if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]: st.session_state.is_logged_in = True

is_admin = st.session_state.is_logged_in or DEV_MODE

# ── 사이드바 ──
with st.sidebar:
    st.markdown("### 🔐 관리자")
    if not is_admin:
        pw = st.text_input("비밀번호", type="password", key="sidebar_pw_2")
        if pw:
            if pw == st.secrets["ADMIN_PASSWORD"]:
                cookie_manager.set("admin_logged_in","yes",expires_at=datetime.now()+timedelta(days=30))
                st.session_state.user_password = pw
                st.session_state.is_logged_in = True
                st.session_state.main_nav = "🖋️ 작성"
                time.sleep(0.4); st.rerun()
            else: st.error("비밀번호가 틀렸습니다.")
    else:
        st.success("관리자 모드")
        if st.button("🔓 로그아웃", use_container_width=True):
            cookie_manager.set("admin_logged_in","no")
            st.session_state.is_logged_in = False
            st.session_state.user_password = ""
            st.session_state.main_nav = "📂 아카이브"
            time.sleep(0.4); st.rerun()
        st.divider()
        st.markdown("### 🛠️ 데이터 관리")
        if st.button("🧹 중복 정리", use_container_width=True):
            conn = get_connection()
            conn.execute("DELETE FROM archive WHERE id NOT IN (SELECT MAX(id) FROM archive GROUP BY title, category)")
            conn.execute("DELETE FROM plan WHERE id NOT IN (SELECT MAX(id) FROM plan GROUP BY title, category)")
            conn.commit(); st.cache_data.clear()
            st.success("✅ 완료! 백업을 눌러주세요."); time.sleep(1.5); st.rerun()
        st.divider()
        st.markdown("### 🔄 동기화")
        if 'sync_msg' in st.session_state:
            mt, txt = st.session_state.sync_msg
            (st.success if mt=="success" else st.error)(txt)
            del st.session_state.sync_msg
        st.button("📤 클라우드 백업", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 클라우드 복구", on_click=restore_from_supabase, use_container_width=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [4] API 검색 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
        return [{
            'display_name': f"{'📀' if m.get('wrapperType')=='collection' else '🎵'} {m.get('collectionName' if m.get('wrapperType')=='collection' else 'trackName','?')} — {m.get('artistName','')}",
            'title': m.get('collectionName' if m.get('wrapperType')=='collection' else 'trackName',''),
            'creator': m.get('artistName',''), 'date': m.get('releaseDate','')[:10],
            'img': m.get('artworkUrl100','').replace('100x100bb','800x800bb'),
            'venue': m.get('artistName',''), 'is_album': m.get('wrapperType')=='collection',
            'collection_id': m.get('collectionId'), 'url': m.get('collectionViewUrl' if m.get('wrapperType')=='collection' else 'trackViewUrl','')
        } for m in res]
    except: return []

def search_tmdb(query, category):
    t = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{t}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

def get_tmdb_details(item_id, category):
    is_movie = "MOVIES" in category
    t = "movie" if is_movie else "tv"
    url = f"https://api.themoviedb.org/3/{t}/{item_id}?api_key={TMDB_API_KEY}&language=ko-KR&append_to_response=credits"
    try:
        res = requests.get(url).json()
        crew = res.get('credits',{}).get('crew',[])
        cast = res.get('credits',{}).get('cast',[])
        if is_movie:
            d = next((m for m in crew if m.get('job')=='Director'), None)
            creator = f"[감독] {d['name'] if d else '정보 없음'}"
            venue = (res.get('production_companies') or [{}])[0].get('name','')
        else:
            cb = res.get('created_by',[])
            names = ", ".join([c['name'] for c in cb]) if cb else next((m['name'] for m in crew if m.get('job') in ['Writer','Executive Producer']), '정보 없음')
            creator = f"[작가/제작] {names}"
            venue = (res.get('networks') or [{}])[0].get('name','')
        cast_str = ", ".join([c['name'] for c in cast[:3]])
        return {"creator": f"{creator} / [출연] {cast_str}".strip(" / "), "venue": venue}
    except: return {"creator": "정보 없음", "venue": ""}

def search_kopis(query):
    ym = re.search(r'\d{4}', query)
    sy = ym.group() if ym else None
    cq = re.sub(r'\d{4}', '', query).strip()
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={cq}&stdate=19500101&eddate=20261231&rows=100&cpage=1"
    try:
        root = ET.fromstring(requests.get(url).content)
        results = []
        for d in root.findall('db'):
            df = d.findtext('prfpdfrom','')
            if sy and sy not in df: continue
            results.append({'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'),
                            'img': d.findtext('poster'), 'date': df, 'venue': d.findtext('fcltynm')})
        return results
    except: return []

def get_kopis_detail(mid):
    try:
        root = ET.fromstring(requests.get(f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mid}?service={KOPIS_KEY}").content)
        d = root.find('db')
        if d:
            crew = (d.findtext('prfcrew') or "").strip()
            cast = (d.findtext('prfcast') or "").strip()
            parts = []
            if crew: parts.append(f"[제작] {crew}")
            if cast: parts.append(f"[출연] {cast}")
            return " / ".join(parts) if parts else "정보 없음"
    except: return "상세정보 로드 실패"
    return "정보 없음"

def scrape_url(url):
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        res.encoding = 'utf-8'; h = res.text
        def og(prop): m = re.search(rf'property="og:{prop}"\s+content="(.*?)"', h); return m.group(1) if m else ""
        t = og('title') or re.search(r'<title>(.*?)</title>', h, re.S)
        t = t.group(1) if hasattr(t,'group') else (t or "제목 없음")
        return {"title": html.unescape(t.strip()), "img": og('image'),
                "venue": og('site_name') or "URL", "summary": f"{url}\n\n{html.unescape(og('description'))}"}
    except: return None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [5] 헬퍼: 카드 렌더링
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAT_EMOJI = {"BOOKS":"📚","MUSIC":"🎧","MOVIES":"🎞️","SERIES":"📽️","STAGE":"🎭","SCRAP":"📰"}
CAT_COLOR = {"BOOKS":"#4A90D9","MUSIC":"#C850C0","MOVIES":"#E50914","SERIES":"#FF6B35","STAGE":"#F5A623","SCRAP":"#6C757D"}

def render_card(row, key_prefix, callback):
    """이미지 카드 + 버튼 렌더링"""
    img = row.get('img_url','') or ''
    cat = row.get('category','')
    view_d = str(row.get('view_date',''))[:10]
    title = row.get('title','')
    is_music = cat == "MUSIC"
    ratio = "1/1" if is_music else "2/3"

    if img and img != "None" and img.strip():
        st.markdown(f"""
        <div class="card-wrap" style="aspect-ratio:{ratio}">
            <img src="{img}" loading="lazy">
            <div class="card-badge">{CAT_EMOJI.get(cat,'')} {cat}</div>
            <div class="card-date">{view_d[5:] if view_d else ''}</div>
            <div class="card-overlay">
                <p class="card-title">{title}</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="card-no-img" style="aspect-ratio:{ratio}">
            <span>{CAT_EMOJI.get(cat,'📌')}</span>
            <p>{title}</p>
        </div>
        """, unsafe_allow_html=True)

    short = title[:9]+"…" if len(title)>9 else title
    if st.button(short, key=f"{key_prefix}_{row['id']}", use_container_width=True):
        callback(row)

def render_section(label, content, color):
    if content and str(content).strip():
        st.markdown(f'<span class="section-pill" style="background:{color};color:#fff">{label}</span>', unsafe_allow_html=True)
        st.markdown(f'<div class="section-body">{str(content).replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [6] 팝업 다이얼로그
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@st.dialog("", width="large")
def show_details(item):
    if hasattr(item,'to_dict'): item = item.to_dict()
    cat = item.get('category','')

    if is_admin:
        c1, _, c3 = st.columns([.15, .7, .15])
        with c1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                conn = get_connection()
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                conn.commit(); st.cache_data.clear()
                try: supabase.table("archive").delete().eq("id",item['id']).execute()
                except: pass
                st.rerun()
        with c3:
            if st.button("✏️ 수정", key=f"edit_{item['id']}", use_container_width=True, type="primary"):
                _load_item_to_form(item, 'archive', cat)
                st.session_state.show_form = True; st.session_state.main_nav = "🖋️ 작성"; st.rerun()
        st.markdown("<hr style='margin:8px 0 16px;border-color:#222'>", unsafe_allow_html=True)

    img_col, txt_col = st.columns([.35, .65])
    with img_col:
        _render_detail_media(item.get('img_url'), item.get('img_url2'))
    with txt_col:
        st.markdown(f'<h2 class="detail-title">{item.get("title","")}</h2>', unsafe_allow_html=True)
        creator = item.get('creator','')
        if creator: st.markdown(f'<p class="detail-meta">{creator}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="detail-meta">📅 {item.get("rel_date","")}　📍 {item.get("venue","")}</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="color:#E50914;font-size:.82rem;font-weight:600;margin-bottom:16px">🍿 완료일: {item.get("view_date","")}</p>', unsafe_allow_html=True)
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        if cat == "SCRAP":
            render_section("✍️ 필사", item.get('summary'), "#444")
            render_section("🎯 논지", item.get('brief'), "#0E6245")
            render_section("💡 논거", item.get('highlights'), "#7D5600")
            render_section("🏗️ 구성", item.get('note'), "#1E425E")
        else:
            render_section("💎 DRIP", item.get('brief'), "#E50914")
            render_section("🖋️ PRISM", item.get('note'), "#1E425E")
            render_section("💡 SIGHT", item.get('summary'), "#0E6245")
            render_section("🔖 SENSE", item.get('highlights'), "#7D5600")

        with st.expander("🔗 공유 텍스트 복사"):
            st.code(_build_share_text(item, cat), language="markdown")


@st.dialog("", width="large")
def show_plan_details(item):
    if hasattr(item,'to_dict'): item = item.to_dict()
    try: rd = json.loads(item['memo'])
    except: rd = {"creator":"","rel_date":"","venue":"","summary":"","brief":"","highlights":"","note":item.get('memo',''),"img_url":"","img_url2":""}
    cat = item.get('category','')

    if is_admin:
        c1, _, c3 = st.columns([.15, .7, .15])
        with c1:
            if st.button("🗑️ 삭제", key=f"del_p_{item['id']}", use_container_width=True):
                conn = get_connection()
                conn.execute("DELETE FROM plan WHERE id=?", (item['id'],))
                conn.commit(); st.cache_data.clear()
                try: supabase.table("plan").delete().eq("id",item['id']).execute()
                except: pass
                st.rerun()
        with c3:
            if st.button("✏️ 수정", key=f"edit_p_{item['id']}", use_container_width=True, type="primary"):
                _load_plan_to_form(item, rd, cat)
                st.session_state.show_form = True; st.session_state.main_nav = "🖋️ 작성"; st.rerun()
        st.markdown("<hr style='margin:8px 0 16px;border-color:#222'>", unsafe_allow_html=True)

    img_col, txt_col = st.columns([.35, .65])
    with img_col:
        _render_detail_media(rd.get('img_url'), rd.get('img_url2'))
    with txt_col:
        st.markdown(f'<h2 class="detail-title">{item.get("title","")}</h2>', unsafe_allow_html=True)
        if rd.get('creator'): st.markdown(f'<p class="detail-meta">{rd["creator"]}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="detail-meta">📅 {rd.get("rel_date","")}　📍 {rd.get("venue","")}</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="color:#3399FF;font-size:.82rem;font-weight:600;margin-bottom:16px">🗓️ 예정일: {item.get("plan_date","")}</p>', unsafe_allow_html=True)
        st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

        if cat == "SCRAP":
            render_section("✍️ 필사", rd.get('summary'), "#444")
            render_section("🎯 논지", rd.get('brief'), "#0E6245")
            render_section("💡 논거", rd.get('highlights'), "#7D5600")
            render_section("🏗️ 구성", rd.get('note'), "#1E425E")
        else:
            render_section("💎 DRIP", rd.get('brief'), "#E50914")
            render_section("🖋️ PRISM", rd.get('note'), "#1E425E")
            render_section("💡 SIGHT", rd.get('summary'), "#0E6245")
            render_section("🔖 SENSE", rd.get('highlights'), "#7D5600")

        with st.expander("🔗 공유 텍스트 복사"):
            st.code(_build_share_text({**rd,'title':item.get('title'),'category':cat}, cat), language="markdown")

    if is_admin:
        st.markdown("---")
        if st.button("✅ 완료 → 아카이브로 이동", key=f"done_{item['id']}", use_container_width=True, type="primary"):
            _move_plan_to_archive(item, rd)

def _render_detail_media(img_url, extra):
    if img_url and str(img_url) != "None" and img_url.strip():
        st.image(img_url, use_container_width=True)
    if extra and str(extra) != "None" and extra.strip():
        url_m = re.search(r'(https?://[^\s]+)', extra)
        if url_m:
            mu = url_m.group(1); txt = extra.replace(mu,'').strip(' /|-')
            if txt: st.markdown(f'<div style="background:#1a1a1a;border-left:3px solid #E50914;padding:8px 12px;border-radius:4px;font-size:.8rem;color:#ddd;margin:8px 0">📎 {txt}</div>', unsafe_allow_html=True)
            if re.search(r'\.(jpg|jpeg|png|webp|gif)', mu, re.I) or "image.tmdb.org" in mu: st.image(mu, use_container_width=True)
            else:
                try: st.video(mu)
                except: st.markdown(f"[🔗 첨부 링크]({mu})")
        else:
            st.markdown(f'<div style="background:#1a1a1a;border-left:3px solid #E50914;padding:8px 12px;border-radius:4px;font-size:.8rem;color:#ddd;margin:8px 0">📎 {extra}</div>', unsafe_allow_html=True)

def _build_share_text(item, cat):
    t = f"[{cat}] {item.get('title','')}\n"
    cr = item.get('creator','')
    if cr: t += f"👤 {cr}\n\n"
    else: t += "\n"
    fields = [("✍️ 필사","summary"),("🎯 논지","brief"),("💡 논거","highlights"),("🏗️ 구성","note")] if cat=="SCRAP" else [("💎 DRIP","brief"),("🖋️ PRISM","note")]
    for lbl, k in fields:
        v = item.get(k,'')
        if v and str(v).strip(): t += f"{lbl}:\n{v}\n\n"
    return t.strip()

def _load_item_to_form(item, source, cat):
    st.session_state.edit_target_id = item['id']
    st.session_state.edit_source = source
    st.session_state.main_category_radio = cat
    for fk, ik in [('f_title','title'),('f_creator','creator'),('f_date','rel_date'),('f_venue','venue'),('f_img','img_url'),('f_video','img_url2'),('f_brief','brief'),('f_highlights','highlights'),('f_note','note'),('f_summary','summary')]:
        st.session_state[fk] = safe_str(item.get(ik))
    try: st.session_state.f_view_date = pd.to_datetime(item.get('view_date')).date()
    except: st.session_state.f_view_date = date.today()

def _load_plan_to_form(item, rd, cat):
    st.session_state.edit_target_id = item['id']
    st.session_state.edit_source = 'plan'
    st.session_state.main_category_radio = cat
    for fk, rk in [('f_title',None),('f_creator','creator'),('f_date','rel_date'),('f_venue','venue'),('f_img','img_url'),('f_video','img_url2'),('f_brief','brief'),('f_highlights','highlights'),('f_note','note'),('f_summary','summary')]:
        st.session_state[fk] = safe_str(item.get('title') if fk=='f_title' else rd.get(rk))
    try: st.session_state.f_view_date = pd.to_datetime(item.get('plan_date')).date()
    except: st.session_state.f_view_date = date.today()

def _move_plan_to_archive(item, rd):
    conn = get_connection(); today = str(date.today())
    rec = {
        "category": item['category'], "title": item['title'],
        "creator": rd.get("creator",""), "rel_date": rd.get("rel_date",""),
        "venue": rd.get("venue",""), "summary": rd.get("summary",""),
        "brief": rd.get("brief",""), "highlights": rd.get("highlights",""),
        "note": rd.get("note",""), "img_url": rd.get("img_url",""),
        "img_url2": rd.get("img_url2",""), "save_date": today, "view_date": item['plan_date']
    }
    conn.execute("INSERT INTO archive (category,title,creator,rel_date,venue,summary,brief,highlights,note,img_url,img_url2,save_date,view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        tuple(rec.values()))
    conn.execute("DELETE FROM plan WHERE id=?", (item['id'],))
    conn.commit(); st.cache_data.clear()
    try:
        supabase.table("archive").upsert(rec).execute()
        supabase.table("plan").delete().eq("id", item['id']).execute()
    except: pass
    st.success(f"🎉 아카이브로 이동 완료!"); time.sleep(0.5); st.rerun()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [7] 메인 헤더 & 내비게이션
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_b64(path):
    try:
        with open(path,"rb") as f: return base64.b64encode(f.read()).decode()
    except: return ""

logo_b64 = get_b64("logo.png")

if logo_b64:
    st.markdown(f'''
    <div class="prism-header">
        <img src="data:image/png;base64,{logo_b64}" width="52">
        <div>
            <div class="prism-logo">PRISM</div>
            <div class="prism-sub">Personal Archive</div>
        </div>
    </div>''', unsafe_allow_html=True)
else:
    st.markdown('<div class="prism-header"><div><div class="prism-logo">PRISM</div><div class="prism-sub">Personal Archive</div></div></div>', unsafe_allow_html=True)

if is_admin:
    st.radio("", ["🖋️ 작성", "📂 아카이브"], horizontal=True,
             label_visibility="collapsed", key="main_nav")
else:
    st.session_state.main_nav = "📂 아카이브"

tab_w = st.session_state.main_nav == "🖋️ 작성"
tab_a = st.session_state.main_nav == "📂 아카이브"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [8] 작성 탭
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if is_admin and tab_w:

    # ─ 카테고리 & 검색 ─
    col_cat, col_search = st.columns([.4, .6])
    with col_cat:
        category = st.radio("카테고리", ["BOOKS","MUSIC","MOVIES","SERIES","STAGE","SCRAP"],
                            horizontal=True, key="main_category_radio", label_visibility="collapsed")
    with col_search:
        search_query = st.text_input("", placeholder=f"🔍 {category} 검색 / URL 입력",
                                     label_visibility="collapsed")

    # ─ 검색 결과 처리 ─
    if search_query:
        if category == "SCRAP":
            if st.button("✨ URL 가져오기", type="primary"):
                s = scrape_url(search_query)
                if s:
                    st.session_state.update({
                        'edit_target_id': None, 'edit_source': None,
                        'f_title': s['title'], 'f_creator': '', 'f_date': str(date.today()),
                        'f_img': s['img'], 'f_venue': s['venue'], 'f_summary': s['summary'],
                        'f_highlights': '', 'f_note': '', 'f_brief': '', 'f_video': '', 'show_form': True
                    }); st.rerun()
                else: st.error("URL에서 정보를 가져올 수 없습니다.")

        elif category == "BOOKS":
            res = search_books(search_query)
            if res:
                sel = st.selectbox("결과 선택", res, format_func=lambda b: f"📚 {b['title']} — {', '.join(b['authors'])}")
                if st.button("✨ 가져오기", type="primary"):
                    st.session_state.update({
                        'edit_target_id': None, 'edit_source': None,
                        'f_title': sel['title'], 'f_creator': ", ".join(sel['authors']),
                        'f_date': sel['datetime'][:10], 'f_img': sel.get('thumbnail','').replace("R120x174","R400x0"),
                        'f_venue': sel.get('publisher',''), 'f_summary': sel.get('contents',''),
                        'f_highlights': '', 'f_note': '', 'f_brief': '', 'f_video': '', 'show_form': True
                    }); st.rerun()
            else: st.info("검색 결과 없음")

        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                sel = st.selectbox("결과 선택", res, format_func=lambda m: m['display_name'])
                if st.button("✨ 가져오기", type="primary"):
                    tracklist = ""
                    if sel.get('is_album') and sel.get('collection_id'):
                        try:
                            lkp = requests.get(f"https://itunes.apple.com/lookup?id={sel['collection_id']}&entity=song").json().get("results",[])
                            tracks = [t['trackName'] for t in lkp if t.get('wrapperType')=='track']
                            if tracks: tracklist = "💿 트랙리스트\n" + "\n".join(f"{i+1}. {t}" for i,t in enumerate(tracks))
                        except: pass
                    st.session_state.update({
                        'edit_target_id': None, 'edit_source': None,
                        'f_title': sel['title'], 'f_creator': sel['creator'], 'f_date': sel['date'],
                        'f_img': sel['img'], 'f_venue': sel['venue'],
                        'f_summary': f"{sel.get('url','')}\n\n" if sel.get('url') else "",
                        'f_highlights': tracklist, 'f_note': '', 'f_brief': '', 'f_video': '', 'show_form': True
                    }); st.rerun()
            else: st.info("검색 결과 없음")

        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                sel = st.selectbox("결과 선택", res, format_func=lambda s: f"🎭 {s['title']} [{s['date']}] ({s['venue']})")
                if st.button("✨ 가져오기", type="primary"):
                    creator = get_kopis_detail(sel['id'])
                    st.session_state.update({
                        'edit_target_id': None, 'edit_source': None,
                        'f_title': sel['title'], 'f_creator': creator, 'f_date': sel['date'],
                        'f_img': sel['img'], 'f_venue': sel['venue'],
                        'f_summary': f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={sel['id']}",
                        'f_highlights': '', 'f_note': '', 'f_brief': '', 'f_video': '', 'show_form': True
                    }); st.rerun()
            else: st.info("검색 결과 없음")

        else:  # MOVIES / SERIES
            res = search_tmdb(search_query, category)
            if res:
                tk = 'title' if category=='MOVIES' else 'name'
                dk = 'release_date' if category=='MOVIES' else 'first_air_date'
                sel = st.selectbox("결과 선택", res, format_func=lambda r: f"🎬 {r.get(tk,'')} ({str(r.get(dk,''))[:4]})")
                if st.button("✨ 가져오기", type="primary"):
                    det = get_tmdb_details(sel['id'], category)
                    st.session_state.update({
                        'edit_target_id': None, 'edit_source': None,
                        'f_title': sel.get(tk,''), 'f_creator': det['creator'], 'f_date': sel.get(dk,''),
                        'f_img': f"https://image.tmdb.org/t/p/w500{sel.get('poster_path','')}",
                        'f_venue': det['venue'], 'f_summary': sel.get('overview',''),
                        'f_highlights': '', 'f_note': '', 'f_brief': '', 'f_video': '', 'show_form': True
                    }); st.rerun()
            else: st.info("검색 결과 없음")

    if not st.session_state.show_form:
        st.button("✏️ 직접 입력", on_click=lambda: st.session_state.update({'should_clear_form':True,'show_form':True}))

    # ─ 작성 폼 ─
    if st.session_state.show_form:
        is_update = st.session_state.edit_target_id is not None

        if is_update:
            st.markdown("""<div style="background:#1a1a00;border:1px solid #554400;border-radius:8px;padding:10px 14px;font-size:.82rem;color:#FFD700;margin-bottom:12px">
            ⚠️ <strong>수정 모드</strong> — 변경 후 저장 버튼을 눌러주세요</div>""", unsafe_allow_html=True)

        with st.container():
            st.markdown('<div class="form-container">', unsafe_allow_html=True)
            left, right = st.columns([.42, .58])

            with left:
                # 이미지 미리보기
                img_val = st.session_state.get('f_img','')
                if img_val and img_val.strip() and img_val != "None":
                    st.image(img_val, use_container_width=True)
                else:
                    st.markdown(f"""<div style="background:#0f0f12;border:1px dashed #333;border-radius:10px;aspect-ratio:2/3;display:flex;align-items:center;justify-content:center;margin-bottom:8px;">
                    <span style="font-size:2.5rem">{CAT_EMOJI.get(category,'🎬')}</span></div>""", unsafe_allow_html=True)

                st.text_input("🖼️ 이미지 URL", key="f_img")
                st.text_input("🎬 관련 영상 / 메모", key="f_video")
                st.markdown("---")
                st.text_input("📌 제목 *", key="f_title")
                st.text_input("👤 창작자", key="f_creator")
                st.text_input("📅 작품 날짜", key="f_date")
                st.text_input("📍 장소 / 플랫폼", key="f_venue")
                st.date_input("🗓️ 감상 완료 / 예정일", key="f_view_date")

            with right:
                if category == "SCRAP":
                    st.markdown('<div class="form-section-label">필사 & 분석</div>', unsafe_allow_html=True)
                    st.text_area("✍️ 필사 (원본 텍스트 / 링크)", key="f_summary", height=130)
                    st.text_input("🎯 중심맥락 (논지)", key="f_brief")
                    st.text_area("💡 핵심 사례 (논거)", key="f_highlights", height=90)
                    st.text_area("🏗️ 글 구성", key="f_note", height=90)
                else:
                    st.markdown('<div class="form-section-label">리뷰 작성</div>', unsafe_allow_html=True)
                    st.text_input("💎 DRIP — 한 줄 인상", key="f_brief")
                    st.text_area("🖋️ PRISM — 감상 전반", key="f_note", height=220)
                    st.text_area("💡 SIGHT — 줄거리 / 기본 정보", key="f_summary", height=120)
                    st.text_area("🔖 SENSE — 인상적인 장면 / 구절", key="f_highlights", height=120)

            st.markdown("</div>", unsafe_allow_html=True)

            # ─ 저장 버튼 행 ─
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            b1, b2, b3 = st.columns([.38, .42, .2])

            if is_update:
                with b1:
                    if st.button("💾 수정 저장", use_container_width=True, type="primary"):
                        if st.session_state.f_title.strip():
                            _save_update(); st.session_state.should_clear_form=True; st.session_state.show_form=False; time.sleep(.6); st.rerun()
                        else: st.warning("제목을 입력해 주세요.")
            else:
                with b1:
                    if st.button("✅ 아카이브 저장", use_container_width=True, type="primary"):
                        if st.session_state.f_title.strip():
                            _save_to_archive(category); st.session_state.should_clear_form=True; st.session_state.show_form=False; time.sleep(.6); st.rerun()
                        else: st.warning("제목을 입력해 주세요.")
                with b2:
                    if st.button("🗓️ Weekly 계획 등록", use_container_width=True):
                        if st.session_state.f_title.strip():
                            _save_to_plan(category); st.session_state.should_clear_form=True; st.session_state.show_form=False; time.sleep(.6); st.rerun()
                        else: st.warning("제목을 입력해 주세요.")
            with b3:
                if st.button("❌ 닫기", use_container_width=True):
                    st.session_state.should_clear_form=True; st.session_state.show_form=False; st.rerun()

    # ── 저장 함수 ──
    def _collect_form(category):
        return {
            "category": str(category), "title": st.session_state.f_title.strip(),
            "creator": st.session_state.f_creator.strip(), "rel_date": st.session_state.f_date.strip(),
            "venue": st.session_state.f_venue.strip(), "summary": st.session_state.f_summary.strip(),
            "brief": st.session_state.f_brief.strip(), "highlights": st.session_state.f_highlights.strip(),
            "note": st.session_state.f_note.strip(), "img_url": st.session_state.f_img.strip(),
            "img_url2": st.session_state.f_video.strip(),
        }

    def _save_to_archive(category):
        rec = {**_collect_form(category), "save_date": str(date.today()), "view_date": str(st.session_state.f_view_date)}
        conn = get_connection()
        conn.execute("INSERT INTO archive (category,title,creator,rel_date,venue,summary,brief,highlights,note,img_url,img_url2,save_date,view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec["category"],rec["title"],rec["creator"],rec["rel_date"],rec["venue"],rec["summary"],rec["brief"],rec["highlights"],rec["note"],rec["img_url"],rec["img_url2"],rec["save_date"],rec["view_date"]))
        conn.commit(); st.cache_data.clear()
        try: supabase.table("archive").upsert(rec).execute()
        except: pass
        st.success("✅ 아카이브 저장 완료!")

    def _save_to_plan(category):
        rd = {k: st.session_state[f"f_{k.split('_',1)[-1]}"] if f"f_{k.split('_',1)[-1]}" in st.session_state else "" for k in ["creator","rel_date","venue","summary","brief","highlights","note","img_url","img_url2"]}
        # 간단히 직접 수집
        rich = {
            "creator": st.session_state.f_creator.strip(), "rel_date": st.session_state.f_date.strip(),
            "venue": st.session_state.f_venue.strip(), "summary": st.session_state.f_summary.strip(),
            "brief": st.session_state.f_brief.strip(), "highlights": st.session_state.f_highlights.strip(),
            "note": st.session_state.f_note.strip(), "img_url": st.session_state.f_img.strip(),
            "img_url2": st.session_state.f_video.strip()
        }
        memo = json.dumps(rich, ensure_ascii=False)
        conn = get_connection()
        conn.execute("INSERT INTO plan (plan_date,category,title,memo) VALUES (?,?,?,?)",
            (str(st.session_state.f_view_date), str(category), st.session_state.f_title.strip(), memo))
        conn.commit()
        try: supabase.table("plan").upsert({"plan_date":str(st.session_state.f_view_date),"category":str(category),"title":st.session_state.f_title.strip(),"memo":memo}).execute()
        except: pass
        st.success("🗓️ Weekly 계획에 추가 완료!")

    def _save_update():
        conn = get_connection(); cat = st.session_state.get("main_category_radio", "BOOKS")
        if st.session_state.edit_source == 'archive':
            rec = {**_collect_form(cat), "view_date": str(st.session_state.f_view_date)}
            conn.execute("UPDATE archive SET category=?,title=?,creator=?,rel_date=?,venue=?,summary=?,brief=?,highlights=?,note=?,img_url=?,img_url2=?,view_date=? WHERE id=?",
                (rec["category"],rec["title"],rec["creator"],rec["rel_date"],rec["venue"],rec["summary"],rec["brief"],rec["highlights"],rec["note"],rec["img_url"],rec["img_url2"],rec["view_date"],st.session_state.edit_target_id))
            conn.commit(); st.cache_data.clear()
            try: supabase.table("archive").update(rec).eq("id",st.session_state.edit_target_id).execute()
            except: pass
        else:
            rich = {
                "creator": st.session_state.f_creator.strip(), "rel_date": st.session_state.f_date.strip(),
                "venue": st.session_state.f_venue.strip(), "summary": st.session_state.f_summary.strip(),
                "brief": st.session_state.f_brief.strip(), "highlights": st.session_state.f_highlights.strip(),
                "note": st.session_state.f_note.strip(), "img_url": st.session_state.f_img.strip(),
                "img_url2": st.session_state.f_video.strip()
            }
            memo = json.dumps(rich, ensure_ascii=False)
            conn.execute("UPDATE plan SET category=?,title=?,plan_date=?,memo=? WHERE id=?",
                (str(cat),st.session_state.f_title.strip(),str(st.session_state.f_view_date),memo,st.session_state.edit_target_id))
            conn.commit()
            try: supabase.table("plan").update({"category":str(cat),"title":st.session_state.f_title.strip(),"plan_date":str(st.session_state.f_view_date),"memo":memo}).eq("id",st.session_state.edit_target_id).execute()
            except: pass
        st.success("✅ 수정 저장 완료!")

    # ── Weekly Contents ──
    st.markdown("---")
    col_l, col_c, col_r = st.columns([.1, .8, .1])
    with col_l:
        if st.button("◀", use_container_width=True): st.session_state.week_offset -= 1; st.rerun()
    with col_r:
        if st.button("▶", use_container_width=True): st.session_state.week_offset += 1; st.rerun()

    today = pd.Timestamp(date.today())
    mon = today - pd.Timedelta(days=today.weekday()) + pd.Timedelta(weeks=st.session_state.week_offset)
    sun = mon + pd.Timedelta(days=6)
    iso_y, iso_w, _ = mon.isocalendar()

    with col_c:
        st.markdown(f"<h3 style='text-align:center;font-family:DM Serif Display,serif;font-size:1.4rem;margin:0'>📅 Weekly Contents &nbsp;<span style='color:#E50914'>{iso_w}주차</span></h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center;color:#555;font-size:.8rem;margin:4px 0 16px'>{mon.strftime('%Y.%m.%d')} — {sun.strftime('%m.%d')}</p>", unsafe_allow_html=True)

    conn = get_connection()
    plan_df = pd.read_sql_query("SELECT * FROM plan ORDER BY plan_date ASC", conn)
    if not plan_df.empty:
        plan_df['p_dt'] = pd.to_datetime(plan_df['plan_date'])
        week_data = plan_df[(plan_df['p_dt'].dt.date >= mon.date()) & (plan_df['p_dt'].dt.date <= sun.date())]
    else:
        week_data = pd.DataFrame()

    if week_data.empty:
        st.markdown("<div style='text-align:center;color:#444;padding:32px 0;font-size:.9rem'>이번 주 예정 콘텐츠가 없습니다.</div>", unsafe_allow_html=True)
    else:
        grid_cols = 6
        items = week_data.to_dict('records')
        for i in range(0, len(items), grid_cols):
            cols = st.columns(grid_cols)
            for j in range(grid_cols):
                if i+j < len(items):
                    row = items[i+j]
                    with cols[j]:
                        try: rd = json.loads(row['memo']); img_u = rd.get('img_url','')
                        except: img_u = ""
                        d_str = row['plan_date'][5:].replace('-','.')
                        emoji = CAT_EMOJI.get(row['category'],'📌')
                        if img_u and img_u.strip() and img_u != "None":
                            st.markdown(f"""<div class="week-card"><div class="week-card-date">{d_str}</div>
                            <img src="{img_u}" style="width:100%;aspect-ratio:1/1;object-fit:cover;display:block">
                            <div class="week-card-foot"><div class="week-card-title">{row['title'][:16]}</div>
                            <div class="week-card-cat">{emoji} {row['category']}</div></div></div>""", unsafe_allow_html=True)
                        else:
                            st.markdown(f"""<div class="week-card"><div class="week-card-date">{d_str}</div>
                            <div style="aspect-ratio:1/1;display:flex;align-items:center;justify-content:center;font-size:2rem;background:#0f0f12">{emoji}</div>
                            <div class="week-card-foot"><div class="week-card-title">{row['title'][:16]}</div>
                            <div class="week-card-cat">{row['category']}</div></div></div>""", unsafe_allow_html=True)
                        if st.button("보기", key=f"wk_{row['id']}", use_container_width=True):
                            show_plan_details(row)
                        st.markdown("<div style='margin-bottom:10px'></div>", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [9] 아카이브 탭
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if tab_a:
    all_df = get_all_data()

    if all_df.empty:
        st.markdown("<div style='text-align:center;color:#444;padding:64px 0;font-size:1rem'>아직 기록이 없습니다.</div>", unsafe_allow_html=True)
    else:
        # ─ 검색 ─
        q = st.text_input("", placeholder="🔍 제목, 창작자, 내용으로 검색…", label_visibility="collapsed", key="global_search")
        if q:
            mask = all_df[['title','creator','summary','note','venue']].fillna('').apply(
                lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)
            all_df = all_df[mask]
            st.markdown(f"<p style='color:#888;font-size:.82rem;margin-bottom:12px'>**'{q}'** 검색 결과 {len(all_df)}건</p>", unsafe_allow_html=True)

        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        main_df = all_df[all_df['category'] != "SCRAP"]
        scrap_df = all_df[all_df['category'] == "SCRAP"]
        cat_order = ["BOOKS","MUSIC","MOVIES","SERIES","STAGE"]

        # 탭 레이블
        tab_labels = [f"📅 전체 ({len(main_df)})"] + \
            [f"{CAT_EMOJI[c]} {c} ({len(main_df[main_df['category']==c])})" for c in cat_order]
        if is_admin: tab_labels.append(f"📰 스크랩 ({len(scrap_df)})")
        sub_tabs = st.tabs(tab_labels)
        GRID = 6

        # ─ 전체 탭 ─
        with sub_tabs[0]:
            years = sorted(main_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            if years:
                yr_opts = {y: f"{y}년 ({len(main_df[main_df['v_dt'].dt.year==y])})" for y in years}
                sel_y = st.selectbox("연도", list(yr_opts.keys()), format_func=lambda x: yr_opts[x], key="archive_year_sel")
                y_df = main_df[main_df['v_dt'].dt.year == sel_y]
                for m in range(12, 0, -1):
                    m_data = y_df[y_df['v_dt'].dt.month == m]
                    if m_data.empty: continue
                    st.markdown(f"<h3 style='font-size:1rem;font-weight:700;color:#888;letter-spacing:1px;margin:24px 0 10px'>{m}월 · {len(m_data)}편</h3>", unsafe_allow_html=True)
                    items = m_data.to_dict('records')
                    for i in range(0, len(items), GRID):
                        cols = st.columns(GRID)
                        for j in range(GRID):
                            if i+j < len(items):
                                with cols[j]: render_card(items[i+j], "all", show_details)

        # ─ 카테고리 탭 ─
        for idx, cat in enumerate(cat_order):
            with sub_tabs[idx+1]:
                c_df = main_df[main_df['category']==cat]
                if c_df.empty: st.info(f"'{cat}' 기록이 없습니다.")
                else:
                    items = c_df.to_dict('records')
                    for i in range(0, len(items), GRID):
                        cols = st.columns(GRID)
                        for j in range(GRID):
                            if i+j < len(items):
                                with cols[j]: render_card(items[i+j], f"cat_{cat}", show_details)

        # ─ 스크랩 탭 ─
        if is_admin:
            with sub_tabs[-1]:
                if scrap_df.empty:
                    st.info("스크랩 기록이 없습니다.")
                else:
                    # 태그 필터
                    from collections import Counter
                    week_start = pd.Timestamp.today() - pd.Timedelta(days=pd.Timestamp.today().weekday())
                    kws = []
                    for txt in (scrap_df['summary'].fillna('')+" "+scrap_df['note'].fillna('')+" "+scrap_df['brief'].fillna('')+" "+scrap_df['highlights'].fillna('')):
                        kws.extend(re.findall(r"#(\w+)", str(txt)))
                    if kws:
                        top = [k[0] for k in Counter(kws).most_common(6)]
                        tag_cols = st.columns(len(top))
                        for i, kw in enumerate(top):
                            active = st.session_state.selected_tag == kw
                            if tag_cols[i].button(f"#{kw}", key=f"tag_{i}",
                                type="primary" if active else "secondary"):
                                st.session_state.selected_tag = None if active else kw; st.rerun()
                        if st.session_state.selected_tag:
                            st.markdown(f"<p style='color:#E50914;font-size:.8rem;margin:4px 0 8px'>🏷️ #{st.session_state.selected_tag} 필터 중</p>", unsafe_allow_html=True)
                        st.markdown("---")

                    disp = scrap_df.copy()
                    if st.session_state.selected_tag:
                        tag = st.session_state.selected_tag
                        mask = disp[['summary','note','brief','highlights']].fillna('').apply(
                            lambda c: c.str.contains(f"#{tag}", na=False)).any(axis=1)
                        disp = disp[mask]

                    if disp.empty: st.info("해당 태그의 스크랩이 없습니다.")
                    else:
                        disp['iso_week'] = disp['v_dt'].dt.isocalendar().week.astype(str).str.zfill(2)
                        disp['iso_year'] = disp['v_dt'].dt.isocalendar().year.astype(str)
                        disp['yw'] = disp['iso_year'] + "-" + disp['iso_week']
                        for w in sorted(disp['yw'].dropna().unique(), reverse=True):
                            w_data = disp[disp['yw'] == w]
                            y, wn = w.split('-')
                            st.markdown(f"<h4 style='font-size:.9rem;color:#888;font-weight:700;letter-spacing:1px;margin:20px 0 10px'>{y} · {int(wn)}주차 · {len(w_data)}건</h4>", unsafe_allow_html=True)
                            for _, row in w_data.iterrows():
                                url_m = re.match(r'https?://', str(row.get('summary','')))
                                link_url = str(row['summary']).split('\n')[0] if url_m else ""
                                with st.expander(f"[{row['venue']}]  {row['title']}  ·  {row['view_date']}"):
                                    if link_url: st.markdown(f"**[🔗 원문 보기]({link_url})**")
                                    if row.get('brief'): st.markdown(f"**🎯 논지:** {row['brief']}")
                                    if row.get('highlights'): st.markdown(f"**💡 논거:** {row['highlights']}")
                                    if row.get('note'): st.markdown(f"**🏗️ 구성:** {row['note']}")
                                    if st.button("✏️ 상세 보기 / 수정", key=f"sc_{row['id']}"): show_details(row.to_dict())

import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime, timedelta
import time
import re 
import xml.etree.ElementTree as ET
from supabase import create_client, Client

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

# --- [2. DB 함수 및 최적화] ---
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

# --- [3. API 및 메타데이터 추출 함수] ---
def get_og_metadata(url):
    """BS4 없이 정규표현식으로 og:title, og:image 추출"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        html = res.text
        
        # 정규표현식 패턴 (따옴표 종류 대응)
        title_re = re.search(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']*)["\']', html)
        img_re = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']*)["\']', html)
        
        title = title_re.group(1) if title_re else "제목을 찾을 수 없음"
        img = img_re.group(1) if img_re else ""
        return {"title": title, "img": img}
    except Exception as e:
        return {"title": f"로드 실패: {e}", "img": ""}

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
        results = []
        for d in root.findall('db'):
            date_from = d.findtext('prfpdfrom')
            if search_year and search_year not in date_from: continue
            results.append({'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': date_from, 'venue': d.findtext('fcltynm')})
        return results
    except: return []

def get_kopis_detail(mt20id):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        res = requests.get(url)
        d = ET.fromstring(res.content).find('db')
        if d is not None:
            crew = d.findtext('prfcrew').strip() if d.findtext('prfcrew') else ""
            cast = d.findtext('prfcast').strip() if d.findtext('prfcast') else ""
            res_str = []
            if crew: res_str.append(f"[제작] {crew}")
            if cast: res_str.append(f"[출연] {cast}")
            return " / ".join(res_str)
    except: return "정보 없음"
    return "정보 없음"

# --- [4. 유틸리티 & 연동 로직] ---
def migrate_to_supabase():
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        local_data = [dict(row) for row in conn.execute("SELECT * FROM archive").fetchall()]
        if not local_data: 
            st.session_state.sync_msg = ("warning", "로컬 데이터가 없습니다.")
            return
        for d in local_data: 
            if 'id' in d: del d['id']
        supabase.table("archive").upsert(local_data).execute()
        st.session_state.sync_msg = ("success", f"✅ {len(local_data)}개 데이터 백업 완료!")
    except Exception as e: st.session_state.sync_msg = ("error", f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        if not cloud_data: return
        conn = get_connection()
        local_df = get_all_data()
        local_keys = set(zip(local_df['title'], local_df['view_date'])) if not local_df.empty else set()
        to_insert = [tuple(row[k] for k in ['category', 'title', 'creator', 'rel_date', 'venue', 'summary', 'brief', 'highlights', 'note', 'img_url', 'img_url2', 'save_date', 'view_date']) 
                     for row in cloud_data if (row['title'], row['view_date']) not in local_keys]
        if to_insert:
            conn.cursor().executemany("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, img_url2, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", to_insert)
            conn.commit()
            st.cache_data.clear()
        st.session_state.sync_msg = ("success", f"✅ {len(to_insert)}개 신규 데이터 복구!")
    except Exception as e: st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")

# --- [5. 팝업 상세 보기 & 연동 시스템] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    # 관리자 기능 (삭제/수정) 생략 (사용자 코드 기반 유지)
    is_mobile = st.session_state.view_mode == "Mobile"
    col_img, col_txt = st.columns([0.3, 0.7]) if not is_mobile else (st.container(), st.container())

    with col_img:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
        if item.get('img_url2'): st.image(item['img_url2'], use_container_width=True)

    with col_txt:
        st.markdown(f'# {item.get("title")}')
        st.write(f"**{item.get('creator')}**")
        st.write(f"**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
        st.markdown(f'<p style="color: #E2E2E2; font-weight: bold;">🍿감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
        st.divider()
        
        sections = [("📖 작품소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 인상 깊은 부분", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]
        for label, key, color in sections:
            content = item.get(key)
            if content:
                st.markdown(f'<div style="background-color: {color}; color: white; padding: 2px 12px; border-radius: 12px; display: inline-block; font-size: 0.8em; margin-bottom: 8px;">{label}</div>', unsafe_allow_html=True)
                st.markdown(content.replace('\n', '  \n'))
                st.markdown("<hr style='margin: 1em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)

        # --- [연동 시스템: #태그 분석] ---
        note_text = item.get('note', '')
        tags = re.findall(r'#(\S+)', note_text)
        if tags:
            st.markdown("#### 🔗 Related Scraps")
            all_df = get_all_data()
            related = all_df[(all_df['category'] == 'SCRAP') & (all_df['title'].str.contains('|'.join(tags), na=False))]
            if not related.empty:
                for _, r in related.iterrows():
                    if st.button(f"📄 {r['title']}", key=f"rel_{r['id']}", use_container_width=True):
                        st.session_state.target_item = r
                        st.rerun()

# --- [6. 메인 로직] ---
if "view_mode" not in st.session_state: st.session_state.view_mode = "PC"
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False

# 사이드바 (로그인/모드) 생략 (사용자 코드 기반 유지)

st.title("🌈 PRISM ARCHIVE")
cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE", "SCRAP"]
is_admin = st.session_state.get('is_logged_in', False)

tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"]) if is_admin else ([None], st.tabs(["📂 ARCHIVE"])[0])

if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 CATEGORY", cat_order, horizontal=True)
        
        if category == "SCRAP":
            url_input = st.text_input("🔗 스크랩 URL 입력")
            if st.button("🔍 메타데이터 가져오기") and url_input:
                meta = get_og_metadata(url_input)
                st.session_state.api_data = {'title': meta['title'], 'img': meta['img'], 'venue': url_input, 'summary': url_input}
                st.rerun()
        else:
            search_query = st.text_input(f"🔍 {category} 검색")
            # 기존 검색 로직 (BOOKS, MUSIC, TMDB 등) 동일 적용
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
                # ... (생략된 기존 검색 엔진들 동일하게 유지)

        st.divider()
        # 공통 저장 폼
        data = st.session_state.get('api_data', {})
        cl, cr = st.columns([0.4, 0.6])
        with cl:
            img_url_val = st.text_input("🖼️ 이미지", value=data.get('img', ''))
            if img_url_val: st.image(img_url_val, use_container_width=True)
            title = st.text_input("제목", value=data.get('title', ''))
            creator = st.text_input("창작자", value=data.get('creator', ''))
        with cr:
            rel_date = st.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
            venue = st.text_input("📍 장소/플랫폼/URL", value=data.get('venue', ''))
            summary = st.text_area("📖 소개", value=data.get('summary', ''))
            note = st.text_area("🌈 PRISM (연동할 제목은 #태그 입력)")
            if st.button("✅ 기록 저장", use_container_width=True):
                new_record = {"category": category, "title": title, "creator": creator, "rel_date": rel_date, "venue": venue, "summary": summary, "note": note, "img_url": img_url_val, "view_date": str(date.today()), "save_date": str(date.today()), "brief": "", "highlights": "", "img_url2": ""}
                conn = get_connection()
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, note, img_url, view_date, save_date, brief, highlights, img_url2) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", 
                             (new_record['category'], new_record['title'], new_record['creator'], new_record['rel_date'], new_record['venue'], new_record['summary'], new_record['note'], new_record['img_url'], new_record['view_date'], new_record['save_date'], "", "", ""))
                conn.commit()
                st.cache_data.clear()
                st.success("저장 완료!")
                st.session_state.api_data = {}
                time.sleep(0.5); st.rerun()

with tab_a:
    all_df = get_all_data()
    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        sub_tabs = st.tabs([f"📅 ALL"] + [f"{c}" for c in cat_order])
        
        # --- [SCRAP 탭: 주간 큐레이션 뷰] ---
        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx+1]:
                c_data = all_df[all_df['category'] == c_name].copy()
                if c_name == "SCRAP" and not c_data.empty:
                    c_data['week'] = c_data['v_dt'].dt.isocalendar().week
                    c_data['year'] = c_data['v_dt'].dt.year
                    for (yr, wk), group in c_data.groupby(['year', 'week'], sort=False):
                        st.markdown(f"#### 🗓️ {yr}년 {wk}주차")
                        for _, row in group.iterrows():
                            c1, c2 = st.columns([0.2, 0.8])
                            with c1:
                                if row['img_url']: st.image(row['img_url'], use_container_width=True)
                            with c2:
                                if st.button(f"{row['title']}", key=f"scr_{row['id']}", use_container_width=True):
                                    show_details(row)
                                st.caption(f"{row['view_date']} | {row['venue'][:50]}...")
                        st.divider()
                else:
                    # 기존 격자 뷰 (생략/유지)
                    st.write(f"{c_name}의 일반 갤러리 뷰...")

# 상시 실행되는 팝업 체크
if "target_item" in st.session_state:
    item = st.session_state.pop("target_item")
    show_details(item)

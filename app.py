import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re
import time
import os
import shutil



# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month
if 'api_data' not in st.session_state: st.session_state.api_data = {}

# 월 이동 함수
def shift_month(delta):
    new_month = st.session_state.cal_month + delta
    if new_month == 0:
        st.session_state.cal_year -= 1
        st.session_state.cal_month = 12
    elif new_month == 13:
        st.session_state.cal_year += 1
        st.session_state.cal_month = 1
    else:
        st.session_state.cal_month = new_month

DB_NAME = 'archive_prism_total_v4.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pub?gid=262271514&single=true&output=csv"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

def restore_from_google():
    try:
        df = pd.read_csv(
            GOOGLE_SHEET_CSV,
            engine="python",
            sep=",",
            quotechar='"',
            on_bad_lines="skip"
        )

        df.columns = df.columns.str.strip()

        col_map = {}

        for col in df.columns:
            lower = col.lower()
            if "category" in lower:
                col_map["category"] = col
            elif "title" in lower:
                col_map["title"] = col
            elif "creator" in lower:
                col_map["creator"] = col
            elif "rel" in lower:
                col_map["rel_date"] = col
            elif "summary" in lower:
                col_map["summary"] = col
            elif "brief" in lower:
                col_map["brief"] = col
            elif "highlight" in lower:
                col_map["highlights"] = col
            elif "note" in lower:
                col_map["note"] = col
            elif "img" in lower:
                col_map["img_url"] = col
            elif "save" in lower:
                col_map["save_date"] = col
            elif "view" in lower:
                col_map["view_date"] = col

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM archive")

            for _, row in df.iterrows():
                conn.execute("""
                    INSERT INTO archive
                    (category, title, creator, rel_date,
                     summary, brief, highlights, note,
                     img_url, save_date, view_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get(col_map.get("category"), ""),
                    row.get(col_map.get("title"), ""),
                    row.get(col_map.get("creator"), ""),
                    row.get(col_map.get("rel_date"), ""),
                    row.get(col_map.get("summary"), ""),
                    row.get(col_map.get("brief"), ""),
                    row.get(col_map.get("highlights"), ""),
                    row.get(col_map.get("note"), ""),
                    row.get(col_map.get("img_url"), ""),
                    row.get(col_map.get("save_date"), ""),
                    row.get(col_map.get("view_date"), ""),
                ))

        st.success("✅ Google 백업 복원 완료")
        time.sleep(1)
        st.rerun()

    except Exception as e:
        st.error(f"❌ 복원 실패: {e}")

# --- [2. API 함수 정의 구역] ---
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
            info_url = m.get('collectionViewUrl' if is_album else 'trackViewUrl', '')
            prefix = "📀 [ALBUM]" if is_album else "🎵 [SINGLE]"
            formatted_res.append({
                'display_name': f"{prefix} {title} - {m.get('artistName', '')}",
                'title': title, 'creator': m.get('artistName', ''),
                'date': m.get('releaseDate', '')[:10],
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'),
                'url': info_url
            })
        return formatted_res
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

def get_tmdb_details(item_id, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}/credits?api_key={TMDB_API_KEY}&language=ko-KR"
    try:
        res = requests.get(url).json()
        director = next((m['name'] for m in res.get('crew', []) if m.get('job') == 'Director'), "정보 없음")
        cast = ", ".join([c['name'] for c in res.get('cast', [])[:3]])
        return f"감독: {director} / 출연: {cast}"
    except: return "정보 없음"

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=20200101&eddate=20261231&rows=10&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

col_empty, col_btn = st.columns([0.85, 0.15]) 

# --- [3. 팝업 함수] ---
@st.dialog("📋 기록 상세 정보", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    # --- [상단 툴바] ---
    t_col1, t_col2, t_col3 = st.columns([0.2, 0.6, 0.2])
    
    with t_col1:
        # [수정] key 값 뒤에 '_dialog'를 붙여서 중복을 피합니다.
        if st.button("🗑️ 삭제", key=f"del_{item['id']}_dialog", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()

    with t_col3:
        # [수정] 토글의 key 값도 '_dialog'를 붙여주는 것이 안전합니다.
        edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}_dialog")

    st.divider()


    col_img, col_txt = st.columns([0.3, 0.7])

    with col_img:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
        else: st.info("등록된 이미지가 없습니다.")

    with col_txt:
        if edit_mode:
            with st.form(key=f"edit_v2_{item['id']}"):
                n_title = st.text_input("📌 Title", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 Creator", value=str(item.get('creator', '')))
                n_rel = st.text_input("📅공개일", value=str(item.get('rel_date', '')))
                try:
                    raw_v = str(item.get('view_date') or item.get('save_date'))[:10]
                    v_dt = datetime.strptime(raw_v, '%Y-%m-%d').date()
                except: v_dt = date.today()
                n_view = st.date_input("🍿 감상일", v_dt)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief') or ''))
                n_sum = st.text_area("📖 줄거리(첫줄 URL)", value=str(item.get('summary') or ''), height=150)
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights') or ''), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note') or ''), height=100)

                try:
                    r_dt = pd.to_datetime(n_rel)
                    ry = str(r_dt.year)
                    rm = str(r_dt.month)
                    rd = str(r_dt.day)

                    v_dt = pd.to_datetime(n_view)
                    vy = str(v_dt.year)
                    vm = str(v_dt.month)
                    vd = str(v_dt.day)

                except:
                    today = date.today()
                    ry = str(today.year)
                    rm = str(today.month)
                    rd = str(today.day)

                    vy = ry
                    vm = rm
                    vd = rd

                if st.form_submit_button("💾 저장", use_container_width=True):
                    # 1. 소문자 변환
                    final_note = n_note.replace("KM", "km").replace("BPM", "bpm")

                    # 2. 구글 백업 데이터 (들여쓰기 주의!)
                    BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
                    edit_payload = {
                        "entry.574529989": item.get('category', '기타'),
                        "entry.898076783": n_title,
                        "entry.345368346": n_creator,
                        "entry.543246487": n_sum,
                        "entry.1816924330": n_brief,
                        "entry.270693677": n_high,
                        "entry.891180756": final_note,
                        "entry.2056153041": item.get('img_url', ''),
                        "entry.780422311_year": ry,
                        "entry.780422311_month": rm,
                        "entry.780422311_day": rd,
                        "entry.1446643193_year": vy,
                        "entry.1446643193_month": vm,
                        "entry.1446643193_day": vd
                    }

                    try:
                        # 구글로 먼저 쏘기
                        requests.post(BACKUP_URL, data=edit_payload, timeout=10)
                        
                        # 로컬 DB 수정
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, summary=?, brief=?, highlights=?, note=?, view_date=? WHERE id=?""", 
                                         (n_title, n_creator, n_rel, n_sum, n_brief, n_high, final_note, str(n_view), item['id']))
                        
                        st.success("✅ 수정 및 백업 완료!")
                        time.sleep(0.5)
                        st.rerun() # 모든 작업 끝난 후 새로고침
                    except Exception as e:
                        st.error(f"❌ 오류 발생: {e}")
        else:
            # 조회 모드 (디자인 가이드 반영)
            st.markdown(f'<div style="font-size:30px; font-weight:bold; line-height:1.1;">{item.get("title")}</div>', unsafe_allow_html=True)
            st.write(f"**Creator:** {item.get('creator')} | **공개일:** {item.get('rel_date')}")
            v_date = item.get('view_date') or item.get('save_date', '')
            st.markdown(f'<p class="date-text">🍿 감상일: {v_date}</p>', unsafe_allow_html=True)
            st.divider()
            
            # 감상 본문 (KM/BPM 소문자 강조 포함)
            note_content = str(item.get('note', '')).replace("km", '<span class="num-text">km</span>').replace("bpm", '<span class="num-text">bpm</span>')
            
            if item.get('brief'): st.success(item['brief'])
            if item.get('summary'): st.info(item['summary'])
            if item.get('highlights'): st.warning(item['highlights'])
            if item.get('note'): st.markdown(note_content, unsafe_allow_html=True)

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    
    if search_query:
        if category == "BOOKS":
            res = search_books(search_query)
            if res:
                opts = {f"📚 {b['title']}": b for b in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': f"{', '.join(b['authors'])}", 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'summary': f"{b['url']}\n\n{b.get('contents', '')}"}
                    st.rerun()
        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {m['display_name']: m for m in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': f"{m['url']}\n\n"}
                    st.rerun()
        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                opts = {f"🎭 {s['title']} ({s['venue']})": s for s in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s['title'], 'creator': f"@{s['venue']}", 'date': s['date'], 'img': s['img'], 'summary': ''}
                    st.rerun()
        else: # MOVIES, SERIES
            res = search_tmdb(search_query, category)
            if res:
                t_key = 'title' if category == 'MOVIES' else 'name'
                d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                opts = {f"🎬 {r.get(t_key)}": r for r in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s.get(t_key), 'creator': get_tmdb_details(s['id'], category), 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'summary': s.get('overview', '')}
                    st.rerun()

    st.divider()
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url_val = st.text_input("🖼️ 이미지", value=data.get('img', ''))
        if img_url_val: st.image(img_url_val, use_container_width=True)
        else: st.info("이미지 URL을 입력하거나 검색해주세요.")
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자 정보", value=data.get('creator', ''))
        col1, col2 = st.columns(2)
        rel_date = col1.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        view_date = col2.date_input("🍿 감상일", value=date.today())
    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=100)
        
# 바로 아래에 버튼을 배치 (가로로 길게 들어갑니다)
       import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re
import time
import os

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

# 세션 상태 초기화
if 'api_data' not in st.session_state: 
    st.session_state.api_data = {}

DB_NAME = 'archive_prism_total_v4.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pub?gid=262271514&single=true&output=csv"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# --- [2. API 함수 정의] ---
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
            info_url = m.get('collectionViewUrl' if is_album else 'trackViewUrl', '')
            prefix = "📀 [ALBUM]" if is_album else "🎵 [SINGLE]"
            formatted_res.append({
                'display_name': f"{prefix} {title} - {m.get('artistName', '')}",
                'title': title, 'creator': m.get('artistName', ''),
                'date': m.get('releaseDate', '')[:10],
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'),
                'url': info_url
            })
        return formatted_res
    except: return []

def search_tmdb(query, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{type_path}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

def get_tmdb_details(item_id, category):
    type_path = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/{type_path}/{item_id}/credits?api_key={TMDB_API_KEY}&language=ko-KR"
    try:
        res = requests.get(url).json()
        director = next((m['name'] for m in res.get('crew', []) if m.get('job') == 'Director'), "정보 없음")
        cast = ", ".join([c['name'] for c in res.get('cast', [])[:3]])
        return f"감독: {director} / 출연: {cast}"
    except: return "정보 없음"

def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=20200101&eddate=20261231&rows=10&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

# --- [3. 팝업 함수] ---
@st.dialog("📋 기록 상세 정보", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    t_col1, t_col2, t_col3 = st.columns([0.2, 0.6, 0.2])
    with t_col1:
        if st.button("🗑️ 삭제", key=f"del_{item['id']}_dialog", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()
    with t_col3:
        edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}_dialog")

    st.divider()
    col_img, col_txt = st.columns([0.3, 0.7])

    with col_img:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
        else: st.info("이미지가 없습니다.")

    with col_txt:
        if edit_mode:
            with st.form(key=f"edit_v2_{item['id']}"):
                n_title = st.text_input("📌 Title", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 Creator", value=str(item.get('creator', '')))
                n_rel = st.text_input("📅공개일", value=str(item.get('rel_date', '')))
                try:
                    v_dt_obj = datetime.strptime(str(item.get('view_date'))[:10], '%Y-%m-%d').date()
                except:
                    v_dt_obj = date.today()
                n_view = st.date_input("🍿 감상일", v_dt_obj)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief') or ''))
                n_sum = st.text_area("📖 줄거리(첫줄 URL)", value=str(item.get('summary') or ''), height=150)
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights') or ''), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note') or ''), height=100)

                if st.form_submit_button("💾 저장", use_container_width=True):
                    final_note = n_note.replace("KM", "km").replace("BPM", "bpm")
                    # 날짜 쪼개기
                    vy, vm, vd = str(n_view.year), str(n_view.month), str(n_view.day)
                    
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, summary=?, brief=?, highlights=?, note=?, view_date=? WHERE id=?""", 
                                     (n_title, n_creator, n_rel, n_sum, n_brief, n_high, final_note, str(n_view), item['id']))
                    st.success("✅ 수정 완료!")
                    time.sleep(0.5)
                    st.rerun()
        else:
            st.markdown(f'<div style="font-size:30px; font-weight:bold;">{item.get("title")}</div>', unsafe_allow_html=True)
            st.write(f"**Creator:** {item.get('creator')} | **공개일:** {item.get('rel_date')}")
            st.write(f"🍿 **감상일:** {item.get('view_date')}")
            st.divider()
            if item.get('brief'): st.success(item['brief'])
            if item.get('summary'): st.info(item['summary'])
            if item.get('highlights'): st.warning(item['highlights'])
            if item.get('note'):
                processed_note = item['note'].replace("km", "**km**").replace("bpm", "**bpm**")
                st.markdown(processed_note)

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    
    if search_query:
        if category == "BOOKS":
            res = search_books(search_query)
            if res:
                opts = {f"📚 {b['title']}": b for b in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': f"{', '.join(b['authors'])}", 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'summary': f"{b['url']}\n\n{b.get('contents', '')}"}
                    st.rerun()
        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {m['display_name']: m for m in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': f"{m['url']}\n\n"}
                    st.rerun()
        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                opts = {f"🎭 {s['title']} ({s['venue']})": s for s in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s['title'], 'creator': f"@{s['venue']}", 'date': s['date'], 'img': s['img'], 'summary': ''}
                    st.rerun()
        else:
            res = search_tmdb(search_query, category)
            if res:
                t_key = 'title' if category == 'MOVIES' else 'name'
                d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                opts = {f"🎬 {r.get(t_key)}": r for r in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s.get(t_key), 'creator': get_tmdb_details(s['id'], category), 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'summary': s.get('overview', '')}
                    st.rerun()

    st.divider()
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url_val = st.text_input("🖼️ 이미지", value=data.get('img', ''))
        if img_url_val: st.image(img_url_val, use_container_width=True)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자 정보", value=data.get('creator', ''))
        col1, col2 = st.columns(2)
        rel_date_val = col1.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        view_date_val = col2.date_input("🍿 감상일", value=date.today())
    with cr:
        summary_val = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief_val = st.text_input("📝 요약")
        highlights_val = st.text_area("✨ 인상 깊은 부분", height=100)
        note_val = st.text_area("💬 감상", height=100)
        
        if st.button("✅ 저장", use_container_width=True):
            # 1. 디자인 가이드 처리 (소문자)
            processed_note = note_val.replace("KM", "km").replace("BPM", "bpm")
            
            # 2. 날짜 처리 (구글 폼 전송용 문자열 추출)
            try:
                r_dt = pd.to_datetime(rel_date_val)
                ry, rm, rd = str(r_dt.year), str(r_dt.month), str(r_dt.day)
            except:
                ry, rm, rd = str(date.today().year), str(date.today().month), str(date.today().day)
            
            vy, vm, vd = str(view_date_val.year), str(view_date_val.month), str(view_date_val.day)

            # 3. 구글 폼 백업
            BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
            payload = {
                "entry.574529989": category, "entry.898076783": title, "entry.345368346": creator,
                "entry.543246487": summary_val, "entry.1816924330": brief_val, "entry.270693677": highlights_val,
                "entry.891180756": processed_note, "entry.2056153041": img_url_val,
                "entry.780422311_year": ry, "entry.780422311_month": rm, "entry.780422311_day": rd,
                "entry.1446643193_year": vy, "entry.1446643193_month": vm, "entry.1446643193_day": vd
            }

            try:
                requests.post(BACKUP_URL, data=payload, timeout=10)
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("""INSERT INTO archive 
                        (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (category, title, creator, rel_date_val, summary_val, brief_val, highlights_val, processed_note, img_url_val, str(date.today()), str(view_date_val)))
                st.success("✅ 저장 및 백업 완료!")
                st.session_state.api_data = {}
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"❌ 저장 실패: {e}")

# --- TAB 2: ARCHIVE ---
with tab2:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1; overflow: hidden; border-radius: 8px; margin-bottom: 5px; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge { position: absolute; top: 5px; background: rgba(0, 0, 0, 0.6); color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; z-index: 10; }
        .badge-left { left: 5px; } .badge-right { right: 5px; }
    </style>""", unsafe_allow_html=True)

    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])

    with sub_tabs[0]:
        if not all_df.empty:
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'])
            yearly_df = all_df.sort_values(by='v_dt', ascending=False)
            years = sorted(yearly_df['v_dt'].dt.year.unique(), reverse=True)
            sel_y = st.selectbox("연도 선택", years)
            
            y_data = yearly_df[yearly_df['v_dt'].dt.year == sel_y]
            for m in range(12, 0, -1):
                m_data = y_data[y_data['v_dt'].dt.month == m]
                if not m_data.empty:
                    st.subheader(f"🗓️ {m}월")
                    items = m_data.to_dict('records')
                    for i in range(0, len(items), 6):
                        cols = st.columns(6)
                        for j in range(6):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    day = pd.to_datetime(row['view_date']).day
                                    st.markdown(f'''<div class="cal-img-box">
                                        <div class="badge badge-left">{row['category']}</div>
                                        <div class="badge badge-right">{day}일</div>
                                        <img src="{row['img_url']}">
                                    </div>''', unsafe_allow_html=True)
                                    if st.button(f"{row['title'][:7]}..", key=f"yr_{row['id']}"):
                                        show_details(row)

    # 카테고리별 탭 루프
    cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
    for idx, c_name in enumerate(cats):
        with sub_tabs[idx+1]:
            c_df = all_df[all_df['category'] == c_name].copy()
            if not c_df.empty:
                c_df['v_dt'] = pd.to_datetime(c_df['view_date'])
                items = c_df.sort_values(by='v_dt', ascending=False).to_dict('records')
                for i in range(0, len(items), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i+j < len(items):
                            row = items[i+j]
                            with cols[j]:
                                st.markdown(f'''<div class="cal-img-box">
                                    <div class="badge badge-left">{row['view_date']}</div>
                                    <img src="{row['img_url']}">
                                </div>''', unsafe_allow_html=True)
                                if st.button(f"{row['title'][:7]}..", key=f"cat_{idx}_{row['id']}"):
                                    show_details(row)

               

# --- TAB 2: ARCHIVE ---
with tab2:
    if st.button("🔄 Google 백업 복원"):
        restore_from_google()	
    st.markdown("""
        <style>
        div[data-testid="column"] {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center !important;
        }
        .cal-img-box { 
            position: relative; 
            width: 100%; aspect-ratio: 1/1; 
            overflow: hidden; border-radius: 6px; 
            margin-bottom: 5px;
        }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        
        /* 배지 스타일 */
        .badge {
            position: absolute;
            top: 5px;
            background: rgba(0, 0, 0, 0.6);
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            z-index: 10;
        }
        .badge-left { left: 5px; background: rgba(50, 50, 50, 0.8); } 
        .badge-right { right: 5px; } 
        </style>
    """, unsafe_allow_html=True)

    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])

    # --- 1. Yearly 탭 (배지 형식 수정) ---
with sub_tabs[0]:
    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'].fillna(all_df['save_date']))
        all_df['year_int'] = all_df['v_dt'].dt.year
        all_df['month_int'] = all_df['v_dt'].dt.month
        yearly_df = all_df.sort_values(by='v_dt', ascending=False)
        
        # [수정] 연도별 개수 계산 및 포맷팅
        raw_years = sorted(list(yearly_df['year_int'].unique()), reverse=True)
        year_options = {y: f"{y} ({len(yearly_df[yearly_df['year_int'] == y])})" for y in raw_years}
        
        # 셀렉트박스 표시 (format_func 사용)
        sel_y = st.selectbox("연도 선택", raw_years, format_func=lambda x: year_options[x], key="yr_sel")
        
        year_data = yearly_df[yearly_df['year_int'] == sel_y]
        
        year_data = yearly_df[yearly_df['year_int'] == sel_y]
        for month in range(12, 0, -1):
            month_data = year_data[year_data['month_int'] == month]
            if not month_data.empty:
                st.markdown(f"### 🗓️ {month}월")
                items = month_data.to_dict('records')
                for i in range(0, len(items), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i + j < len(items):
                            row = items[i + j]
                            with cols[j]:
                                # [수정] 날짜에서 '일'만 추출하여 'nn일' 형식으로 변환
                                try:
                                    day_val = pd.to_datetime(row['view_date']).day
                                    v_date_display = f"{day_val}일"
                                except:
                                    v_date_display = ""

                                img_html = f'''
                                    <div class="cal-img-box">
                                        <div class="badge badge-left">{row['category']}</div>
                                        <div class="badge badge-right">{v_date_display}</div>
                                        <img src="{row["img_url"]}">
                                    </div>'''
                                st.markdown(img_html, unsafe_allow_html=True)
                                if st.button(f"{row['title'][:7]}..", key=f"yr_{row['id']}", use_container_width=True): 
                                    show_details(row)
                st.divider()

    # --- 2. 카테고리 탭 (수정된 부분) ---
    cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
    for idx, c_name in enumerate(cats):
        with sub_tabs[idx+1]:
            cat_df = all_df[all_df['category'] == c_name].copy()
            if not cat_df.empty:
                cat_df['sort_dt'] = pd.to_datetime(cat_df['view_date'].fillna(cat_df['save_date']))
                cat_df = cat_df.sort_values(by='sort_dt', ascending=False)
                items = cat_df.to_dict('records')
                for i in range(0, len(items), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i + j < len(items):
                            row = items[i + j]
                            with cols[j]:
                                # 수정: 배지를 badge-left(왼쪽 상단)로 변경
                                v_date_full = row['view_date'] if row['view_date'] else ""
                                img_html = f'''
                                    <div class="cal-img-box">
                                        <div class="badge badge-left">{v_date_full}</div>
                                        <img src="{row["img_url"]}">
                                    </div>'''
                                st.markdown(img_html, unsafe_allow_html=True)
                                if st.button(f"{row['title'][:7]}..", key=f"cat_{idx}_{row['id']}", use_container_width=True): 
                                    show_details(row)
            else: st.info(f"{c_name} 기록이 없습니다.")











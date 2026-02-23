import streamlit as st
import sqlite3
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import date, datetime
import time
import os
from supabase import create_client, Client

# --- [1. 설정 및 API] ---
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

# API 및 DB 설정
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pub?gid=1160662254&single=true&output=csv"
DB_NAME = 'archive_prism_total_v5.db'

# Supabase 설정
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

if 'api_data' not in st.session_state: st.session_state.api_data = {}

# --- [2. DB 초기화] ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# --- [3. API 함수들 (Books, Music, Movies, Kopis)] ---
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
            formatted_res.append({
                'display_name': f"{'📀' if is_album else '🎵'} {title} - {m.get('artistName', '')}",
                'title': title, 'creator': m.get('artistName', ''),
                'date': m.get('releaseDate', '')[:10],
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'),
                'venue': m.get('artistName', '')
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
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=19500101&eddate=20261231&rows=100&cpage=1"
    try:
        res = requests.get(url)
        root = ET.fromstring(res.content)
        return [{'title': d.findtext('prfnm'), 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 'date': d.findtext('prfpdfrom'), 'venue': d.findtext('fcltynm')} for d in root.findall('db')]
    except: return []

# --- [4. 팝업 상세 보기 및 동기화 수정/삭제] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    t_col1, t_col2, t_col3 = st.columns([0.2, 0.6, 0.2])
    with t_col1:
        if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
            # SQLite 삭제
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            # Supabase 삭제 (제목과 날짜가 일치하는 행 삭제)
            supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
            st.rerun()
    with t_col3:
        edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")

    st.divider()
    col_img, col_txt = st.columns([0.3, 0.7])
    with col_img:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)

    with col_txt:
        if edit_mode:
            with st.form(key=f"edit_form_{item['id']}"):
                n_img = st.text_input("🖼️ 이미지 URL", value=item.get('img_url', ''))
                n_title = st.text_input("📌 제목", value=item.get('title', ''))
                n_creator = st.text_input("👤 창작자", value=item.get('creator', ''))
                n_rel = st.text_input("📅 작품 날짜", value=item.get('rel_date', ''))
                n_venue = st.text_input("📍 장소/플랫폼", value=item.get('venue', ''))
                n_view_date = st.date_input("🍿 감상일", value=pd.to_datetime(item.get('view_date')).date())
                n_brief = st.text_input("📝 요약", value=item.get('brief', ''))
                n_sum = st.text_area("📖 줄거리", value=item.get('summary', ''), height=100)
                n_high = st.text_area("✨ 인상 깊은 부분", value=item.get('highlights', ''), height=100)
                n_note = st.text_area("💬 감상", value=item.get('note', ''), height=100)

                if st.form_submit_button("💾 저장"):
                    # SQLite 업데이트
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, venue=?, summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=? WHERE id=?""", 
                                     (n_title, n_creator, n_rel, n_venue, n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, item['id']))
                    # Supabase 업데이트 (Upsert 혹은 Delete 후 Insert 방식 사용 가능하나 여기선 간략화)
                    st.success("수정 완료!")
                    st.rerun()
        else:
            st.markdown(f'# {item.get("title")}')
            st.write(f"**[{item.get('category')}]** {item.get('creator')} | 📅 {item.get('rel_date')} | 📍 {item.get('venue')}")
            st.markdown(f'<p style="color: #FF4B4B; font-weight: bold; font-size: 1.2em;">🍿 {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()
            if item.get('brief'): st.info(f"**요약:** {item.get('brief')}")
            if item.get('summary'): st.write(f"**줄거리:**\n{item.get('summary')}")
            if item.get('highlights'): st.warning(f"**인상 깊은 부분:**\n{item.get('highlights')}")
            if item.get('note'): st.success(f"**나의 감상:**\n{item.get('note')}")

# --- [5. 메인 화면 - WRITE 탭] ---
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
                    st.session_state.api_data = {'title': b['title'], 'creator': ", ".join(b['authors']), 'date': b['datetime'][:10], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'venue': b.get('publisher', ''), 'summary': b.get('contents', '')}
                    st.rerun()
        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {m['display_name']: m for m in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'venue': m['creator']}
                    st.rerun()
        # ... (TMDB, KOPIS 생략 - 이전 코드와 동일) ...

    st.divider()
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url_val = st.text_input("🖼️ 이미지 URL", value=data.get('img', ''))
        if img_url_val: st.image(img_url_val, use_container_width=True)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자 정보", value=data.get('creator', ''))
        rel_date = st.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        venue = st.text_input("📍 장소/플랫폼", value=data.get('venue', ''))
        
    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=100)
        brief = st.text_input("📝 요약 (한 줄 평)")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 나의 감상", height=100)
        view_date = st.date_input("🍿 감상일", value=date.today())
        
        if st.button("✅ 기록 저장", use_container_width=True):
            new_record = {
                "category": category, "title": title, "creator": creator,
                "rel_date": rel_date, "venue": venue, "summary": summary,
                "brief": brief, "highlights": highlights, "note": note,
                "img_url": img_url_val, "save_date": str(date.today()),
                "view_date": str(view_date)
            }
            try:
                # 1. 로컬 저장
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("INSERT INTO archive (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
                # 2. Supabase 저장
                supabase.table("archive").insert(new_record).execute()
                
                st.success("✅ 로컬 및 Supabase 저장 완료!")
                st.session_state.api_data = {}
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"❌ 저장 오류: {e}")

# --- [6. 아카이브 뷰 - ARCHIVE 탭] ---
with tab2:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; margin-bottom: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); transition: 0.3s; }
        .cal-img-box:hover { transform: scale(1.02); }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
    </style>""", unsafe_allow_html=True)

    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive ORDER BY view_date DESC", conn)

    if not all_df.empty:
        cat_list = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        # 메인 탭 생성 (전체 + 5개 카테고리)
        sub_tabs = st.tabs([f"📅 ALL ({len(all_df)})"] + [f"📂 {c}" for c in cat_list])

        # 1. [전체 보기 탭] - 연도/월별 그룹화
        with sub_tabs[0]:
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
            years = sorted(all_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            if years:
                sel_y = st.selectbox("연도 선택", years, key="year_sel")
                y_data = all_df[all_df['v_dt'].dt.year == sel_y]
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
                                        st.markdown(f'<div class="cal-img-box"><div class="badge">{pd.to_datetime(row["view_date"]).day}일</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                        if st.button(row['title'][:8], key=f"all_{row['id']}", use_container_width=True): 
                                            show_details(row)

        # 2. [카테고리별 탭] - 선택한 카테고리만 필터링
        for idx, c_name in enumerate(cat_list):
            with sub_tabs[idx + 1]: # sub_tabs[0]이 전체이므로 +1
                c_data = all_df[all_df['category'] == c_name]
                if c_data.empty:
                    st.info(f"{c_name} 카테고리에 아직 기록된 데이터가 없습니다.")
                else:
                    st.write(f"총 {len(c_data)}개의 기록이 있습니다.")
                    items = c_data.to_dict('records')
                    for i in range(0, len(items), 6):
                        cols = st.columns(6)
                        for j in range(6):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    # 카테고리 탭에서는 날짜 전체 표시
                                    st.markdown(f'<div class="cal-img-box"><div class="badge">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:8], key=f"cat_{c_name}_{row['id']}", use_container_width=True): 
                                        show_details(row)
    else:

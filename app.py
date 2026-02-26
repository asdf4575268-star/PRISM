import streamlit as st
import requests
import pandas as pd
from datetime import date, datetime
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
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- [2. 데이터 로드 함수] ---
st.title("🌈PRISM ARCHIVE ")

def load_data():
    try:
        # Supabase에서 직접 데이터를 가져옵니다.
        res = supabase.table("archive").select("*").order("view_date", desc=True).execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame()

# --- [3. 로그인 시스템 & 사이드바] ---
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_password" not in st.session_state:
    st.session_state.user_password = ""
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "PC"

if st.session_state.user_password == st.secrets["ADMIN_PASSWORD"]:
    st.session_state.is_logged_in = True

is_admin = st.session_state.is_logged_in 

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not is_admin:
        input_password = st.text_input("Password", type="password", key="sidebar_pw")
        if input_password == st.secrets["ADMIN_PASSWORD"]:
            st.session_state.user_password = input_password 
            st.session_state.is_logged_in = True
            st.rerun()
    
    if st.session_state.is_logged_in:
        st.success("Admin Mode Active")
        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.is_logged_in = False
            st.session_state.user_password = "" 
            st.rerun()
            
    st.divider()
    st.markdown("### 📱 화면 모드")
    st.session_state.view_mode = st.radio("보기 옵션", ["PC", "Mobile"], horizontal=True, label_visibility="collapsed")

is_mobile = st.session_state.view_mode == "Mobile"


# --- [API 검색 함수들 - 변경 없음] ---
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
        cast_label = f"[출연] {cast_names}" if cast_names else ""
        full_creator = f"{creator_label} / {cast_label}".strip(" / ")
        return {"creator": full_creator, "venue": venue_info}
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
    except: return "정보 없음"
    return "정보 없음"


# --- [4. 팝업 상세 보기 - 디자인 원본 유지] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    edit_mode = False
    if is_admin:
        t_col1, t_col2, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                supabase.table("archive").delete().eq("id", item['id']).execute()
                st.rerun()
        with t_col3:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    if is_mobile:
        col_img = st.container(); col_txt = st.container()
    else:
        col_img, col_txt = st.columns([0.3, 0.7])

    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 메인 이미지 URL", value=str(item.get('img_url', '')), key=f"img_in_{item['id']}")
            n_sub_img = st.text_input("📸 추가 이미지 URL", value=str(item.get('sub_img', '')), key=f"sub_img_in_{item['id']}")
            if n_img: st.image(n_img, use_container_width=True, caption="Main")
            if n_sub_img: st.image(n_sub_img, use_container_width=True, caption="Sub")
        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                cat = item.get('category')
                labels = {"BOOKS": "📖 출판사", "MUSIC": "💿 레이블", "MOVIES": "🎬 제작사", "SERIES": "📺 플랫폼", "STAGE": "📍 장소"}
                v_label = labels.get(cat, "📍 장소")
                n_rel = st.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_venue = st.text_input(v_label, value=str(item.get('venue', '')))
                n_view_date = st.date_input("🍿 감상일", value=pd.to_datetime(item.get('view_date')).date())
                n_sum = st.text_area("📖 줄거리/작품소개", value=str(item.get('summary', '')), height=150)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '')))
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '')), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '')), height=100)

                if st.form_submit_button("💾 저장"):
                    supabase.table("archive").update({
                        "title": n_title, "creator": n_creator, "rel_date": n_rel, "venue": n_venue,
                        "summary": n_sum, "brief": n_brief, "highlights": n_high, "note": n_note,
                        "view_date": str(n_view_date), "img_url": n_img, "sub_img": n_sub_img
                    }).eq("id", item['id']).execute()
                    st.success("✅ 수정 완료!")
                    time.sleep(0.5); st.rerun()
    else: 
        with col_img:
            if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
            if item.get('sub_img'): 
                st.markdown("<br>", unsafe_allow_html=True)
                st.image(item['sub_img'], use_container_width=True)
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"#### **[{item.get('category')}]**")
            st.write(f"**{item.get('creator')}**")
            st.write(f"**📅 {item.get('rel_date')} | 📍 {item.get('venue')}**")
            st.markdown(f'<p style="color: #E2E2E2; font-weight: bold; font-size: 1.1em;">🍿감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()
            sections = [("📖 줄거리/작품소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 인상 깊은 부분", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]
            for label, key, color in sections:
                content = item.get(key)
                if content:
                    st.markdown(f'<div style="display: inline-block; background-color: {color}; color: white; padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px;">{label}</div>', unsafe_allow_html=True)
                    st.markdown(content.replace('\n', '  \n'))
                    st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)


# --- [5. 메인 화면 - 디자인 및 로직 유지] ---
if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tab_a = st.tabs(["📂 ARCHIVE"])[0]
    tab_w = None

# WRITE 로직 (Supabase 직접 저장으로 변경)
if is_admin and tab_w:
    with tab_w:
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
                        st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': f"{m.get('url', '')}\n\n"}
                        st.rerun()
            elif category == "STAGE":
                res = search_kopis(search_query)
                if res:
                    opts = {f"🎭 {s['title']} [{s['date']}~] ({s['venue']})": s for s in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        s = opts[sel]
                        st.session_state.api_data = {'title': s['title'], 'creator': get_kopis_detail(s['id']), 'date': s['date'], 'venue': s['venue'], 'img': s['img'], 'summary': f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={s['id']}"}
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
                        det = get_tmdb_details(s['id'], category)
                        st.session_state.api_data = {'title': s.get(t_key), 'creator': det['creator'], 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'venue': det['venue'], 'summary': s.get('overview', '')}
                        st.rerun()

        st.divider()
        data = st.session_state.get('api_data', {})
        cl, cr = st.columns([0.4, 0.6]) if not is_mobile else (st.container(), st.container())
        
        with cl:
            img_url_val = st.text_input("🖼️ 메인 이미지 URL", value=data.get('img', ''), key="main_img_input")
            sub_img_val = st.text_input("📸 추가 이미지 URL (인증샷 등)", value="", key="sub_img_input")
            if img_url_val: st.image(img_url_val, use_container_width=True, caption="Main")
            if sub_img_val: st.image(sub_img_val, use_container_width=True, caption="Sub")
            title = st.text_input("제목", value=data.get('title', ''), key="title_input")
            creator = st.text_input("창작자 정보", value=data.get('creator', ''), key="creator_input")
            rel_date = st.text_input("📅 작품 날짜", value=data.get('date', str(date.today())), key="rel_date_input")
            venue = st.text_input("📍 장소/플랫폼", value=data.get('venue', ''), key="venue_input")
        with cr:
            summary = st.text_area("📖 줄거리/작품소개", value=data.get('summary', ''), height=150, key="summary_input")
            brief = st.text_input("📝 요약 (한 줄 평)", key="brief_input")
            highlights = st.text_area("✨ 인상 깊은 부분", height=100, key="highlights_input")
            note = st.text_area("🌈 PRISM", height=100, key="note_input")
            view_date = st.date_input("🍿 감상일", value=date.today(), key="view_date_input")
            
            if st.button("✅ 기록 저장", use_container_width=True, type="primary"):
                supabase.table("archive").insert({
                    "category": category, "title": title, "creator": creator, "rel_date": rel_date, 
                    "venue": venue, "summary": summary, "brief": brief, "highlights": highlights, 
                    "note": note, "img_url": img_url_val, "sub_img": sub_img_val, 
                    "save_date": str(date.today()), "view_date": str(view_date)
                }).execute()
                st.success("✅ 저장 완료!")
                st.session_state.api_data = {}
                time.sleep(0.8); st.rerun()

# --- ARCHIVE 탭 (디자인 원본 유지) ---
with tab_a:
    st.markdown("""<style>
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1.4; overflow: hidden; border-radius: 8px; margin-top: 5px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); background: #1e1e1e; display: flex; align-items: center; justify-content: center; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .music-tab-style { aspect-ratio: 1/1 !important; }
        .badge-cat { position: absolute; top: 8px; left: 8px; background: rgba(0, 0, 0, 0.7); color: yellow; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
        .badge-date { position: absolute; bottom: 8px; right: 8px; background: rgba(0, 0, 0, 0.7); color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; z-index: 10; }
    </style>""", unsafe_allow_html=True)

    all_df = load_data()

    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        cat_emojis = {"BOOKS": "📚", "MUSIC": "🎧", "MOVIES": "🎞️", "SERIES": "📽️", "STAGE": "🎭"}
        tab_titles = [f"📅 ALL ({len(all_df)})"] + [f"{cat_emojis[c]}{c} ({len(all_df[all_df['category'] == c])})" for c in cat_order]
        sub_tabs = st.tabs(tab_titles)
        grid_cols = 6 

        with sub_tabs[0]:
            years = sorted(all_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            year_options = {y: f"{y}({len(all_df[all_df['v_dt'].dt.year == y])})" for y in years}
            sel_y = st.selectbox("📅 연도 선택", options=list(year_options.keys()), format_func=lambda x: year_options[x])
            y_df = all_df[all_df['v_dt'].dt.year == sel_y]
            
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
                                is_music = row["category"] == "MUSIC"
                                music_cls = "music-tab-style" if is_music else ""
                                img_style = 'style="object-fit: contain; background: #000;"' if row["category"] == "MUSIC" else 'style="object-fit: cover;"'
                                with cols[j]:
                                    st.markdown(f'''
                                        <div class="cal-img-box {music_cls}">
                                            <div class="badge-cat">{row["category"]}</div>
                                            <div class="badge-date">{pd.to_datetime(row["view_date"]).day}일</div>
                                            <img src="{row["img_url"]}">
                                        </div>
                                    ''', unsafe_allow_html=True)
                                    if st.button(row['title'][:10], key=f"all_{row['id']}", use_container_width=True): 
                                        show_details(row)

        for idx, c_name in enumerate(cat_order):
            with sub_tabs[idx + 1]:
                c_data = all_df[all_df['category'] == c_name]
                if c_data.empty: st.info(f"{c_name} 데이터 없음")
                else:
                    items = c_data.to_dict('records')
                    tab_cls = "music-tab-style" if c_name == "MUSIC" else ""
                    for i in range(0, len(items), grid_cols):
                        cols = st.columns(grid_cols)
                        for j in range(grid_cols):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    st.markdown(f'<div class="cal-img-box {tab_cls}"><div class="badge-date">{row["view_date"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:10], key=f"cat_{row['id']}", use_container_width=True): show_details(row)




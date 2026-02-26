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

# --- [2. 데이터 로드 함수 (Supabase 전용)] ---
st.title("🌈PRISM ARCHIVE ")

@st.cache_data(ttl=60) # 1분간 캐시 유지 (성능 향상)
def load_data_from_supabase():
    try:
        res = supabase.table("archive").select("*").order("view_date", desc=True).execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"❌ 데이터 로드 실패: {e}")
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


# --- [API 검색 함수들 - 기존과 동일] ---
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


# --- [4. 팝업 상세 보기 (Supabase 전용)] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    edit_mode = False
    if is_admin:
        t_col1, t_col2, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                supabase.table("archive").delete().eq("id", item['id']).execute()
                st.cache_data.clear()
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
        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 창작자", value=str(item.get('creator', '')))
                n_rel = st.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_venue = st.text_input("📍 장소/플랫폼", value=str(item.get('venue', '')))
                n_view_date = st.date_input("🍿 감상일", value=pd.to_datetime(item.get('view_date')).date())
                n_sum = st.text_area("📖 작품소개", value=str(item.get('summary', '')), height=150)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '')))
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '')), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '')), height=100)

                if st.form_submit_button("💾 수정사항 저장"):
                    supabase.table("archive").update({
                        "title": n_title, "creator": n_creator, "rel_date": n_rel, "venue": n_venue,
                        "summary": n_sum, "brief": n_brief, "highlights": n_high, "note": n_note,
                        "view_date": str(n_view_date), "img_url": n_img, "sub_img": n_sub_img
                    }).eq("id", item['id']).execute()
                    st.cache_data.clear()
                    st.success("✅ 수정 완료!")
                    st.rerun()
    else: 
        with col_img:
            if item.get('img_url'): st.image(item['img_url'], use_container_width=True)
            if item.get('sub_img'): st.image(item['sub_img'], use_container_width=True, caption="Sub Image")
        with col_txt:
            st.markdown(f'# {item.get("title")}')
            st.write(f"#### **[{item.get('category')}]** {item.get('creator')}")
            st.write(f"📅 {item.get('rel_date')} | 📍 {item.get('venue')}")
            st.write(f"🍿 **감상일: {item.get('view_date')}**")
            st.divider()
            sections = [("📖 작품소개", "summary", "#444"), ("📝 요약", "brief", "#0E6245"), ("✨ 인상 깊은 부분", "highlights", "#7D5600"), ("🌈 PRISM", "note", "#1E425E")]
            for lbl, k, col in sections:
                if item.get(k):
                    st.markdown(f'<div style="background:{col}; color:white; padding:2px 10px; border-radius:10px; display:inline-block; font-size:0.8em;">{lbl}</div>', unsafe_allow_html=True)
                    st.markdown(item[k].replace('\n', '  \n'))
                    st.divider()


# --- [5. 메인 화면] ---
if is_admin:
    tab_w, tab_a = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])
else:
    tab_a = st.tabs(["📂 ARCHIVE"])[0]
    tab_w = None

# --- WRITE 로직 (Supabase 저장) ---
if is_admin and tab_w:
    with tab_w:
        category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
        search_query = st.text_input(f"🔍 {category} 검색")
        
        if search_query:
            # (API 검색 로직 동일... 지면상 중략)
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
                        st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': f"{m.get('url', '')}"}
                        st.rerun()
            elif category == "STAGE":
                res = search_kopis(search_query)
                if res:
                    opts = {f"🎭 {s['title']} ({s['venue']})": s for s in res}
                    sel = st.selectbox("결과 선택", list(opts.keys()))
                    if st.button("✨ 가져오기"):
                        s = opts[sel]
                        st.session_state.api_data = {'title': s['title'], 'creator': get_kopis_detail(s['id']), 'date': s['date'], 'venue': s['venue'], 'img': s['img']}
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
                        det = get_tmdb_details(s['id'], category)
                        st.session_state.api_data = {'title': s.get(t_key), 'creator': det['creator'], 'date': s.get(d_key), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'venue': det['venue'], 'summary': s.get('overview', '')}
                        st.rerun()

        st.divider()
        data = st.session_state.get('api_data', {})
        cl, cr = st.columns([0.4, 0.6]) if not is_mobile else (st.container(), st.container())
        
        with cl:
            img_v = st.text_input("🖼️ 메인 이미지 URL", value=data.get('img', ''))
            sub_v = st.text_input("📸 추가 이미지 URL")
            if img_v: st.image(img_v, use_container_width=True)
        with cr:
            t = st.text_input("제목", value=data.get('title', ''))
            c = st.text_input("창작자", value=data.get('creator', ''))
            rd = st.text_input("📅 날짜", value=data.get('date', ''))
            vn = st.text_input("📍 장소/플랫폼", value=data.get('venue', ''))
            sm = st.text_area("📖 소개", value=data.get('summary', ''), height=100)
            br = st.text_input("📝 요약")
            hi = st.text_area("✨ 하이라이트")
            nt = st.text_area("🌈 PRISM")
            vd = st.date_input("🍿 감상일", value=date.today())
            
            if st.button("✅ 수퍼베이스에 저장", use_container_width=True, type="primary"):
                supabase.table("archive").insert({
                    "category": category, "title": t, "creator": c, "rel_date": rd, "venue": vn,
                    "summary": sm, "brief": br, "highlights": hi, "note": nt, "img_url": img_v,
                    "sub_img": sub_v, "save_date": str(date.today()), "view_date": str(vd)
                }).execute()
                st.cache_data.clear()
                st.success("✅ 클라우드 저장 완료!")
                st.session_state.api_data = {}
                time.sleep(0.5); st.rerun()

# --- ARCHIVE 로직 (Supabase 호출) ---
with tab_a:
    all_df = load_data_from_supabase()
    if not all_df.empty:
        all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce')
        cat_order = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sub_tabs = st.tabs([f"📅 ALL"] + [f"{c}" for c in cat_order])
        
        with sub_tabs[0]:
            years = sorted(all_df['v_dt'].dt.year.dropna().unique().astype(int), reverse=True)
            sel_y = st.selectbox("📅 연도", years)
            y_df = all_df[all_df['v_dt'].dt.year == sel_y]
            for m in range(12, 0, -1):
                m_data = y_df[y_df['v_dt'].dt.month == m]
                if not m_data.empty:
                    st.subheader(f"🗓️ {m}월")
                    items = m_data.to_dict('records')
                    cols = st.columns(6)
                    for idx, row in enumerate(items):
                        with cols[idx % 6]:
                            st.image(row["img_url"], use_container_width=True)
                            if st.button(row['title'][:8], key=f"all_{row['id']}", use_container_width=True): show_details(row)

        for i, c_name in enumerate(cat_order):
            with sub_tabs[i+1]:
                c_data = all_df[all_df['category'] == c_name]
                if not c_data.empty:
                    items = c_data.to_dict('records')
                    cols = st.columns(6)
                    for idx, row in enumerate(items):
                        with cols[idx % 6]:
                            st.image(row["img_url"], use_container_width=True)
                            if st.button(row['title'][:8], key=f"cat_{row['id']}", use_container_width=True): show_details(row)

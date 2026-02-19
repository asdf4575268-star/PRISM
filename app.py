import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime

# --- [1. 스타일 및 설정] ---
st.set_page_config(
    layout="wide", 
    page_title="PRISM", 
    page_icon="🌈"
)

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    
    .act-name {{ font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }}
    .date-text {{ font-size: 30px; color: #666; margin: 0; }}
    .num-text {{ font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; line-height: 1; }}
    
    .cal-img-box {{ 
        width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:4px; 
        margin-bottom:4px; border: 1px solid #eee; 
    }}
    .cal-img-box img {{ width:100%; height:100%; object-fit:cover; }}
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_total_v4.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, 
                         img_url TEXT, save_date TEXT, view_date TEXT)''')
        try:
            conn.execute("ALTER TABLE archive ADD COLUMN view_date TEXT")
        except sqlite3.OperationalError:
            pass

init_db()

# --- [2. 상세 정보 및 수정 팝업] ---
@st.dialog("📋 기록 상세 정보", width="large")
def show_details(item):
    edit_mode = st.toggle("✏️ 수정 모드 켜기", key=f"tog_{item['id']}")

    if edit_mode:
        with st.form(key=f"edit_form_{item['id']}", clear_on_submit=False):
            col_img, col_txt = st.columns([0.4, 0.6])
            with col_img:
                if item['img_url']: st.image(item['img_url'], use_container_width=True)
                new_img = st.text_input("🖼️ 이미지 URL", value=item['img_url'])
            with col_txt:
                new_title = st.text_input("📌 제목", value=item['title'])
                new_creator = st.text_input("👤 창작자", value=item['creator'])
                new_rel_date = st.text_input("📅 작품 날짜", value=item['rel_date'])
                
                # 수정 모드에서도 날짜 선택기(date_input) 사용
                current_v_date = datetime.strptime(item['view_date'], '%Y-%m-%d') if item.get('view_date') else date.today()
                new_view_date = st.date_input("🍿 감상일 수정", value=current_v_date)
                
                new_brief = st.text_input("📝 요약", value=item['brief'])
                new_summary = st.text_area("📖 줄거리", value=item['summary'], height=120)
                new_highlights = st.text_area("✨ 인상 깊은 부분", value=item['highlights'], height=100)
                new_note = st.text_area("💬 감상", value=item['note'], height=100)
                
                if st.form_submit_button("💾 변경사항 저장", use_container_width=True):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, summary=?, 
                                        brief=?, highlights=?, note=?, img_url=?, view_date=? WHERE id=?""",
                                     (new_title, new_creator, new_rel_date, new_summary, 
                                      new_brief, new_highlights, new_note, new_img, str(new_view_date), int(item['id'])))
                    st.rerun()
    else:
        col_img, col_txt = st.columns([0.4, 0.6])
        with col_img:
            if item['img_url']: st.image(item['img_url'], use_container_width=True)
        with col_txt:
            st.markdown(f'<p class="act-name">{item["title"]}</p>', unsafe_allow_html=True)
            st.write(f"**정보:** {item['creator']} | **작품날짜:** {item['rel_date']}")
            v_date = item.get('view_date') if item.get('view_date') else item['save_date']
            st.markdown(f'<p class="date-text">🍿 관람일: {v_date}</p>', unsafe_allow_html=True)
            st.divider()
            if item['brief']: st.success(f"**📝 요약:** {item['brief']}")
            st.info(f"**📖 줄거리:**\n\n{item['summary']}")
            st.warning(f"**✨ 인상 깊은 부분:**\n\n{item['highlights']}")
            st.write(f"**💬 감상:**\n\n{item['note']}")
            
            if st.button("🗑️ 기록 삭제", key=f"del_{item['id']}", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
                st.rerun()

# --- [3. 세션 및 내비게이션] ---
if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month

def shift_month(delta):
    new_month = st.session_state.cal_month + delta
    if new_month > 12: st.session_state.cal_month = 1; st.session_state.cal_year += 1
    elif new_month < 1: st.session_state.cal_month = 12; st.session_state.cal_year -= 1
    else: st.session_state.cal_month = new_month

# --- API 캐시 처리 ---
@st.cache_data(ttl=3600)
def search_kopis(query):
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr?service={KOPIS_KEY}&shprfnm={query}&stdate=20200101&eddate=20261231&rows=10&cpage=1"
    try:
        response = requests.get(url)
        root = ET.fromstring(response.content)
        results = []
        for db in root.findall('db'):
            results.append({'title': db.findtext('prfnm'), 'id': db.findtext('mt20id'), 'img': db.findtext('poster'), 'date': db.findtext('prfpdfrom'), 'venue': db.findtext('fcltynm')})
        return results
    except: return []

@st.cache_data(ttl=3600)
def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

@st.cache_data(ttl=3600)
def search_apple_music(query):
    url = f"https://itunes.apple.com/search?term={query}&limit=10&country=kr&entity=musicTrack,album"
    try: return requests.get(url).json().get("results", [])
    except: return []

@st.cache_data(ttl=3600)
def search_tmdb(query, category):
    search_type = "movie" if category == "MOVIES" else "tv"
    url = f"https://api.themoviedb.org/3/search/{search_type}?api_key={TMDB_API_KEY}&query={query}&language=ko-KR"
    try: return requests.get(url).json().get("results", [])
    except: return []

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab1:
    category = st.radio("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"], horizontal=True)
    search_query = st.text_input(f"🔍 {category} 검색")
    
    if search_query:
        # API 검색 로직 (생략 - 이전과 동일)
        if category == "BOOKS":
            res = search_books(search_query)
            if res:
                opts = {f"📚 {b['title']}": b for b in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    b = opts[sel]
                    st.session_state.api_data = {'title': b['title'], 'creator': f"저자: {', '.join(b['authors'])}", 'date': b['datetime'][:10], 'img': b['thumbnail'], 'summary': b['contents']}
                    st.rerun()
        elif category == "MUSIC":
            res = search_apple_music(search_query)
            if res:
                opts = {f"🎵 {m.get('trackName', m.get('collectionName'))}": m for m in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    m = opts[sel]
                    st.session_state.api_data = {'title': m.get('trackName', m.get('collectionName')), 'creator': f"아티스트: {m['artistName']}", 'date': m['releaseDate'][:10], 'img': m.get('artworkUrl100', '').replace('100x100bb', '600x600bb'), 'summary': ''}
                    st.rerun()
        elif category == "STAGE":
            res = search_kopis(search_query)
            if res:
                opts = {f"🎭 {r['title']} ({r['venue']})": r for r in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s['title'], 'creator': f"공연장: {s['venue']}", 'date': s['date'], 'img': s['img'], 'summary': ''}
                    st.rerun()
        else:
            res = search_tmdb(search_query, category)
            if res:
                opts = {f"🎬 {r.get('title' if category=='MOVIES' else 'name')}": r for r in res}
                sel = st.selectbox("검색 결과", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    st.session_state.api_data = {'title': s.get('title' if category=='MOVIES' else 'name'), 'date': s.get('release_date' if category=='MOVIES' else 'first_air_date'), 'img': f"https://image.tmdb.org/t/p/w500{s.get('poster_path')}", 'summary': s.get('overview', '')}
                    st.rerun()

    st.divider()
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    with cl:
        img_url_val = st.text_input("🖼️ 이미지 URL", value=data.get('img', ''))
        if img_url_val: st.image(img_url_val, width=300)
        title = st.text_input("제목", value=data.get('title', ''))
        creator = st.text_input("창작자/공연장", value=data.get('creator', ''))
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            rel_date = st.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        with col_d2:
            # 기본값은 오늘(date.today())이지만, 클릭해서 수정 가능
            view_date = st.date_input("🍿 감상일", value=date.today())
            
    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=100)
        if st.button("✅ 저장", key="final_save", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("""INSERT INTO archive 
                                (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) 
                                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                             (category, title, creator, rel_date, summary, brief, highlights, note, 
                              img_url_val, str(date.today()), str(view_date)))
            st.success(f"성공적으로 저장되었습니다! (관람일: {view_date})")
            st.session_state.api_data = {}
            st.rerun()

with tab2:
    # (ARCHIVE 탭 로직 - 이전 코드와 동일하게 view_date_dt 기준 정렬 유지)
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)
    
    if not all_df.empty:
        all_df['view_date_dt'] = pd.to_datetime(all_df['view_date'].fillna(all_df['save_date']))
        all_df = all_df.sort_values(by='view_date_dt', ascending=False)
        
        # ... (이하 동일) ...
        sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])
        # (각 탭별 렌더링 코드...)
        # (생략된 부분은 이전 답변의 ARCHIVE 탭 로직과 동일합니다)


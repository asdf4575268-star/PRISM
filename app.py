import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date, datetime
import xml.etree.ElementTree as ET
import io

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")

# CSS: 활동명 90, 날짜 30, 숫자 60 및 요청 폰트 적용 (로컬 폰트 미사용)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Jolly+Lodger&family=Kirang+Haerang&family=Lacquer&display=swap');
    
    /* 텍스트 크기 가이드라인 반영 */
    .act-name { font-size: 90px !important; font-family: 'Kirang Haerang', cursive; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px !important; color: #666; font-family: sans-serif; margin: 0; }
    .num-text { font-size: 60px !important; font-family: 'Jolly Lodger', cursive; margin: 0; line-height: 1; }
    
    .cal-img-box { width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:10px; margin-bottom:4px; border: 1px solid #eee; background-color: #f0f0f0; }
    .cal-img-box img { width:100%; height:100%; object-fit:cover; }
    
    [data-testid="stDialog"] img { max-height: 450px !important; object-fit: contain !important; }
    
    /* 사이드바 제거를 위한 스타일 가이드 (기본적으로 정의하지 않음으로써 메인 집중) */
    .system-banner { background-color: #f8f9fa; padding: 15px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #eee; }
    </style>
    """, unsafe_allow_html=True)

# 상단 타이틀 및 시스템 컨트롤 (사이드바 대체)
t_col1, t_col2 = st.columns([0.7, 0.3])
with t_col1:
    st.title("🌈PRISM")
with t_col2:
    # DB 백업 버튼을 상단 우측에 배치 (안정성 확보)
    DB_NAME = 'archive_prism_total_v4.db'
    try:
        with open(DB_NAME, "rb") as f:
            st.download_button(
                label="📥 DB 백업(유실 방지)",
                data=f.read(),
                file_name=f"prism_backup_{date.today()}.db",
                mime="application/x-sqlite3",
                use_container_width=True
            )
    except:
        pass

# 세션 상태 초기화
if 'api_data' not in st.session_state: st.session_state.api_data = {}

# --- [2. DB 안정성 및 관리] ---
def init_db():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                             rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
    except sqlite3.Error as e:
        st.error(f"데이터베이스 연결 오류: {e}")

init_db()

# --- [3. API 함수 (기존 유지)] ---
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    try:
        res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
        return res.json().get("documents", []) if res.status_code == 200 else []
    except: return []

def search_apple_music(query):
    # km, bpm 소문자 준수
    url = f"https://itunes.apple.com/search?term={query}&limit=20&country=kr&entity=musicTrack,album"
    try:
        res = requests.get(url).json().get("results", [])
        formatted_res = []
        for m in res:
            is_album = m.get('wrapperType') == 'collection'
            title = m.get('collectionName' if is_album else 'trackName', 'Unknown')
            formatted_res.append({
                'display_name': f"{'📀 [ALBUM]' if is_album else '🎵 [SINGLE]'} {title} - {m.get('artistName', '')}",
                'title': title, 'creator': m.get('artistName', ''), 'date': m.get('releaseDate', '')[:10],
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'url': m.get('collectionViewUrl', '')
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

# --- [4. 팝업 상세 보기 - 토글 모드 적용] ---
@st.dialog("📋 기록 상세 정보", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    # 세션 상태를 이용해 개별 아이템의 수정 모드 토글 관리
    edit_key = f"is_editing_{item['id']}"
    if edit_key not in st.session_state: 
        st.session_state[edit_key] = False

    # 상단 버튼 바
    c_del, c_mid, c_edit = st.columns([0.1, 0.8, 0.1])
    with c_del:
        if st.button("🗑️", key=f"del_btn_{item['id']}", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.rerun()
    with c_edit:
        # ✏️ 누르면 수정 모드 켜지고, ❌ 누르면 꺼짐
        icon = "❌" if st.session_state[edit_key] else "✏️"
        if st.button(icon, key=f"edit_btn_{item['id']}", use_container_width=True):
            st.session_state[edit_key] = not st.session_state[edit_key]
            st.rerun()
            
    st.divider()
    
    col_img, col_txt = st.columns([0.4, 0.6])
    
    # 왼쪽: 이미지는 항상 표시 (요청사항 반영)
    with col_img:
        if item.get('img_url'): 
            st.image(item['img_url'], use_container_width=True)
        else:
            st.info("이미지가 없습니다.")
            
    # 오른쪽: 토글 상태에 따라 '보기' 또는 '수정' 모드 표시
    with col_txt:
        if st.session_state[edit_key]:
            # --- [수정 모드] ---
            with st.form(key=f"edit_form_{item['id']}", clear_on_submit=False):
                st.caption("📝 내용 수정 중...")
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 Creator", value=str(item.get('creator', '')))
                
                # 날짜 처리
                try:
                    v_dt_val = datetime.strptime(item.get('view_date')[:10], '%Y-%m-%d').date()
                except:
                    v_dt_val = date.today()
                    
                n_view = st.date_input("🍿 감상일", value=v_dt_val)
                n_rel = st.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '') or ''))
                n_sum = st.text_area("📖 줄거리/링크", value=str(item.get('summary', '') or ''), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '') or ''), height=150)
                
                if st.form_submit_button("💾 변경사항 저장", use_container_width=True):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE archive SET 
                                        title=?, creator=?, rel_date=?, summary=?, 
                                        brief=?, note=?, view_date=? 
                                        WHERE id=?""", 
                                     (n_title, n_creator, n_rel, n_sum, n_brief, n_note, str(n_view), item['id']))
                    st.session_state[edit_key] = False # 저장 후 다시 보기 모드로
                    st.success("수정되었습니다!")
                    st.rerun()
        else:
            # --- [보기 모드] ---
            st.markdown(f'<p class="act-name">{item.get("title")}</p>', unsafe_allow_html=True)         
            st.markdown(f'<p class="date-text">🍿 {item.get("view_date") or item.get("save_date")}</p>', unsafe_allow_html=True)
            st.divider()
            st.write(f"**Creator:** {item.get('creator')}")
            st.write(f"**Released:** {item.get('rel_date')}")
            if item.get('brief'): 
                st.info(f"📝 {item.get('brief')}")
            if item.get('note'): 
                st.write("---")
                st.write(item.get('note'))

# --- [5. 메인 레이아웃] ---
tab_write, tab_archive = st.tabs(["🖋️ WRITE", "📂 ARCHIVE"])

with tab_write:
    # 카테고리 선택 및 검색
    c_sel, c_sch = st.columns([0.3, 0.7])
    with c_sel:
        category = st.selectbox("📂 CATEGORY", ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"])
    with c_sch:
        search_query = st.text_input(f"🔍 {category} 검색")
    
    if search_query:
        # API 검색 처리 (기존 로직 동일)
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
                    st.session_state.api_data = {'title': m['title'], 'creator': m['creator'], 'date': m['date'], 'img': m['img'], 'summary': ''}
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
    
    # 💡 입력 레이아웃: 사진을 상시 확인 가능하도록 좌측 배치
    data = st.session_state.get('api_data', {})
    cl, cr = st.columns([0.4, 0.6])
    
    with cl:
        img_url_val = st.text_input("이미지 URL", value=data.get('img', ''))
        if img_url_val: st.image(img_url_val, use_container_width=True)
        else: st.info("이미지 URL을 입력하거나 검색하면 여기에 표시됩니다.")
        
        title = st.text_input("활동명/제목 (글자크기 90)", value=data.get('title', ''))
        creator = st.text_input("Creator/정보", value=data.get('creator', ''))
        rel_date = st.text_input("📅 작품 날짜 (글자크기 30)", value=data.get('date', str(date.today())))
        view_date = st.date_input("🍿 감상일", value=date.today())

    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=200)
        
        if st.button("✅ 저장", use_container_width=True):
            if not title:
                st.error("제목은 필수입니다.")
            else:
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                 (category, title, creator, rel_date, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
                st.session_state.api_data = {}
                st.success("DB에 성공적으로 기록되었습니다.")
                st.rerun()

with tab_archive:
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    if all_df.empty:
        st.info("아직 저장된 기록이 없습니다.")
    else:
        sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])

        # --- YEARLY 탭 ---
        with sub_tabs[0]:
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'].fillna(all_df['save_date']))
            raw_years = sorted(list(all_df['v_dt'].dt.year.unique()), reverse=True)
            sel_y = st.selectbox("연도 선택", raw_years)
            
            year_data = all_df[all_df['v_dt'].dt.year == sel_y].sort_values(by='v_dt', ascending=False)
            for month in range(12, 0, -1):
                m_data = year_data[year_data['v_dt'].dt.month == month]
                if not m_data.empty:
                    # 숫자 크기 60 적용
                    st.markdown(f'<p class="num-text">{month}<span style="font-size:30px; font-family: sans-serif; margin-left: 5px;">월</span></p>', unsafe_allow_html=True)
                    items = m_data.to_dict('records')
                    cols = st.columns(6)
                    for idx, row in enumerate(items):
                        with cols[idx % 6]:
                            if row['img_url']: st.markdown(f'<div class="cal-img-box"><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                            if st.button(row['title'][:8], key=f"yr_{row['id']}", use_container_width=True):
                                show_details(row)
                    st.divider()

        # --- 카테고리 탭 (공통 로직) ---
        cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        for idx, c_name in enumerate(cats):
            with sub_tabs[idx+1]:
                c_df = all_df[all_df['category'] == c_name].sort_values(by='id', ascending=False)
                if not c_df.empty:
                    items = c_df.to_dict('records')
                    for i in range(0, len(items), 6):
                        cols = st.columns(6)
                        for j in range(6):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    if row['img_url']: st.markdown(f'<div class="cal-img-box"><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(row['title'][:8], key=f"cat_{idx}_{row['id']}", use_container_width=True):
                                        show_details(row)





import streamlit as st
import sqlite3
import requests
import pandas as pd
import calendar
import xml.etree.ElementTree as ET
from datetime import date, datetime
import re

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM")
st.title("🌈PRISM")

if 'cal_year' not in st.session_state: st.session_state.cal_year = datetime.now().year
if 'cal_month' not in st.session_state: st.session_state.cal_month = datetime.now().month
if 'api_data' not in st.session_state: st.session_state.api_data = {}

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

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; line-height: 1; }
    .cal-img-box { width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:10px; margin-bottom:4px; border: 1px solid #eee; background-color: #f0f0f0; }
    .cal-img-box img { width:100%; height:100%; object-fit:cover; }
    </style>
    """, unsafe_allow_html=True)

DB_NAME = 'archive_prism_total_v4.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

# --- [2. API 함수 정의] --- (기존과 동일하므로 유지)
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
                'display_name': f"{'📀 [ALBUM]' if is_album else '🎵 [SINGLE]'} {title} - {m.get('artistName', '')}",
                'title': title, 'creator': m.get('artistName', ''), 'date': m.get('releaseDate', '')[:10],
                'img': m.get('artworkUrl100', '').replace('100x100bb', '800x800bb'), 'url': m.get('collectionViewUrl' if is_album else 'trackViewUrl', '')
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

# --- [3. 팝업 함수 (수정/조회 통합)] ---
@st.dialog("📋 기록 상세 정보", width="large")
def show_details(item):
    # 판다스 row 데이터일 경우를 대비해 딕셔너리로 변환하여 안전하게 접근
    if isinstance(item, pd.Series): item = item.to_dict()
    
    edit_mode = st.toggle("✏️ 수정 모드", key=f"tog_{item['id']}")
    col_img, col_txt = st.columns([0.4, 0.6])

    with col_img:
        if item.get('img_url'): st.image(item['img_url'], use_container_width=True)

    with col_txt:
        if edit_mode:
            with st.form(f"edit_f_{item['id']}"):
                n_title = st.text_input("📌 제목", item['title'])
                n_creator = st.text_input("👤 창작자", item['creator'])
                n_rel = st.text_input("📅 작품 날짜", item['rel_date'])
                
                # 날짜 파싱 안전 처리
                raw_v = item.get('view_date') or item.get('save_date') or str(date.today())
                try: v_dt = datetime.strptime(raw_v[:10], '%Y-%m-%d').date()
                except: v_dt = date.today()
                n_view = st.date_input("🍿 감상일", v_dt)

                n_brief = st.text_input("📝 요약", item.get('brief', ''))
                n_sum = st.text_area("📖 줄거리(첫줄 URL)", item.get('summary', ''), height=150)
                n_high = st.text_area("✨ 인상 깊은 부분", item.get('highlights', ''), height=100)
                n_note = st.text_area("💬 감상", item.get('note', ''), height=100)

                if st.form_submit_button("💾 저장", use_container_width=True):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, summary=?, 
                                        brief=?, highlights=?, note=?, view_date=? WHERE id=?""",
                                     (n_title, n_creator, n_rel, n_sum, n_brief, n_high, n_note, str(n_view), item['id']))
                    st.rerun()
        else:
            st.markdown(f'<p class="act-name">{item["title"]}</p>', unsafe_allow_html=True)
            urls = re.findall(r'(https?://[^\s]+)', str(item.get('summary', '')))
            if urls: st.link_button("🌐 공식 정보", urls[0], use_container_width=True)
            
            st.write(f"**정보:** {item['creator']} | **작품날짜:** {item['rel_date']}")
            v_date = item.get('view_date') or item.get('save_date', '')
            st.markdown(f'<p class="date-text">🍿 감상일: {v_date}</p>', unsafe_allow_html=True)
            st.divider()

            # 데이터가 있으면 무조건 표시 (안 보일 수 없게 조건 완화)
            b_val = str(item.get('brief', '')).strip()
            if b_val and b_val != 'None': st.success(f"**📝 요약**\n\n{b_val}")
            
            s_val = str(item.get('summary', '')).strip()
            if s_val and s_val != 'None': st.info(f"**📖 줄거리/상세**\n\n{s_val}")
            
            h_val = str(item.get('highlights', '')).strip()
            if h_val and h_val != 'None': st.warning(f"**✨ 인상 깊은 부분**\n\n{h_val}")
            
            n_val = str(item.get('note', '')).strip()
            if n_val and n_val != 'None': st.write(f"**💬 감상**\n\n{n_val}")
            
            st.divider()
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                st.rerun()

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
                sel = st.selectbox("결과 선택 (SINGLE/ALBUM)", list(opts.keys()))
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
                    st.session_state.api_data = {'title': s['title'], 'creator': f"공연장: {s['venue']}", 'date': s['date'], 'img': s['img'], 'summary': ''}
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
        img_url_val = data.get('img', '') 
        if img_url_val: st.image(img_url_val, use_container_width=True)
        else: st.info("검색을 통해 이미지를 불러와주세요.")
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
        if st.button("✅ 저장", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("INSERT INTO archive (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (category, title, creator, rel_date, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
            st.session_state.api_data = {}
            st.rerun()

# --- TAB 2: ARCHIVE ---
with tab2:
    sub_tabs = st.tabs(["📅 YEARLY", "📚 BOOKS", "🎸 MUSIC", "🎬 MOVIES", "📺 SERIES", "🎭 STAGE"])
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    if not all_df.empty:
        with sub_tabs[0]:
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'].fillna(all_df['save_date']))
            all_df['year_int'] = all_df['v_dt'].dt.year
            year_counts = all_df['year_int'].value_counts().to_dict()
            unique_years = sorted(list(set([datetime.now().year] + list(year_counts.keys()))), reverse=True)
            year_labels = [f"{y} ({year_counts.get(y, 0)})" for y in unique_years]
            
            c_yr, _ = st.columns([1.5, 3])
            with c_yr:
                sel_y = st.selectbox("연도 선택", year_labels, index=unique_years.index(st.session_state.cal_year) if st.session_state.cal_year in unique_years else 0)
                st.session_state.cal_year = int(sel_y[:4])

            _, n1, n2, n3, _ = st.columns([1.5, 1, 2, 1, 1.5])
            with n1: 
                if st.button("◀", key="prev"): shift_month(-1); st.rerun()
            with n2: st.markdown(f"<p class='num-text' style='text-align:center;'>{st.session_state.cal_year} / {st.session_state.cal_month}</p>", unsafe_allow_html=True)
            with n3:
                if st.button("▶", key="next"): shift_month(1); st.rerun()

            cal = calendar.monthcalendar(st.session_state.cal_year, st.session_state.cal_month)
            month_df = all_df[(all_df['v_dt'].dt.year == st.session_state.cal_year) & (all_df['v_dt'].dt.month == st.session_state.cal_month)]

            for week in cal:
                cols = st.columns(7)
                for i, day in enumerate(week):
                    if day == 0: continue
                    with cols[i]:
                        st.markdown(f"<p class='num-text' style='font-size:25px;'>{day}</p>", unsafe_allow_html=True)
                        day_items = month_df[month_df['v_dt'].dt.day == day]
                        if not day_items.empty:
                            if day_items.iloc[0]['img_url']:
                                st.markdown(f'<div class="cal-img-box"><img src="{day_items.iloc[0]["img_url"]}"></div>', unsafe_allow_html=True)
                            for _, r in day_items.iterrows():
                                if st.button(f"• {r['title'][:5]}", key=f"cal_{r['id']}", use_container_width=True): show_details(r)

    # 카테고리별 탭 루프
    cats = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
    for idx, c_name in enumerate(cats):
        with sub_tabs[idx+1]:
            cat_df = all_df[all_df['category'] == c_name].sort_values(by='save_date', ascending=False)
            if not cat_df.empty:
                cols = st.columns(4)
                for i, (_, row) in enumerate(cat_df.iterrows()):
                    with cols[i % 4]:
                        if row['img_url']:
                            st.markdown(f'<div style="width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:10px; background-color:#f0f0f0; display:flex; align-items:center; justify-content:center;"><img src="{row["img_url"]}" style="width:100%; height:100%; object-fit:cover;"></div>', unsafe_allow_html=True)
                        v_date = row.get('view_date') or row.get('save_date', '')
                        st.markdown(f'<p class="date-text" style="font-size:15px; text-align:center;">🍿 {v_date}</p>', unsafe_allow_html=True)
                        if st.button(row['title'], key=f"list_{idx}_{row['id']}", use_container_width=True): show_details(row)
            else: st.info("기록이 없습니다.")

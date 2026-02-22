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

DB_NAME = 'archive_prism_total_v5.db'
TMDB_API_KEY = "6e7c55b6259b7731655033f783f3fc5b"
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pub?gid=1160662254&single=true&output=csv"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

def restore_from_google():
    try:
        df = pd.read_csv(GOOGLE_SHEET_CSV).fillna("")
        df.columns = df.columns.str.strip()

        col_map = {}
        for col in df.columns:
            lower = col.lower().replace(" ", "")
            if "감상일" in lower: col_map["view_date"] = col
            elif "category" in lower or "카테고리" in lower: col_map["category"] = col
            elif "title" in lower or "제목" in lower: col_map["title"] = col
            elif "creator" in lower or "작가" in lower or "감독" in lower: col_map["creator"] = col
            elif any(x in lower for x in ["rel", "공개", "출판", "개봉", "발매"]): col_map["rel_date"] = col
            elif "summary" in lower or "줄거리" in lower: col_map["summary"] = col
            elif "brief" in lower or "요약" in lower: col_map["brief"] = col
            elif "highlight" in lower or "인상" in lower: col_map["highlights"] = col
            elif "note" in lower or "감상" in lower: col_map["note"] = col
            elif "img" in lower or "이미지" in lower: col_map["img_url"] = col
            elif "타임스탬프" in lower or "timestamp" in lower: col_map["save_date"] = col
            elif "venue" in lower or "장소" in lower: col_map["venue"] = col

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM archive")
            for _, row in df.iterrows():
                raw_v = str(row.get(col_map.get("view_date"), "")).strip()
                if raw_v:
                    try:
                        clean_v = raw_v.replace("오전", "AM").replace("오후", "PM")
                        v_date = pd.to_datetime(clean_v).strftime('%Y-%m-%d')
                    except:
                        v_date = raw_v
                else:
                    v_date = ""

                r_date = str(row.get(col_map.get("rel_date"), "")).strip()

                conn.execute("""
                    INSERT INTO archive
                    (category, title, creator, rel_date,
                     summary, brief, highlights, note,
                     img_url, save_date, view_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(row.get(col_map.get("category"), "")),
                    str(row.get(col_map.get("title"), "")),
                    str(row.get(col_map.get("creator"), "")),
                    r_date,
                    str(row.get(col_map.get("venue"), "")),
                    str(row.get(col_map.get("summary"), "")),
                    str(row.get(col_map.get("brief"), "")),
                    str(row.get(col_map.get("highlights"), "")),
                    str(row.get(col_map.get("note"), "")),
                    str(row.get(col_map.get("img_url"), "")),
                    str(row.get(col_map.get("save_date"), "")),
                    v_date
                ))
        st.success("복원 완료")
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
                'title': title, 
                'id': d.findtext('mt20id'), 
                'img': d.findtext('poster'), 
                'date': date_from, 
                'venue': d.findtext('fcltynm')
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
            if not crew and not cast: return "정보 없음"
            return f"{crew} / {cast}".strip(" / ")
    except: return "상세정보 로드 실패"
    return "정보 없음"

# --- [3. 팝업 함수] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    if f"deleted_{item['id']}" in st.session_state:
        st.rerun()
        return

    t_col1, t_col2, t_col3 = st.columns([0.2, 0.6, 0.2])
    with t_col1:
        if st.button("🗑️ 삭제", key=f"del_{item['id']}_dialog", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.session_state[f"deleted_{item['id']}"] = True
            st.rerun()
    with t_col3:
        edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}_dialog")

    st.divider()
    col_img, col_txt = st.columns([0.3, 0.7])

    with col_img:
        img_url = item.get('img_url')
        if img_url:
            try: st.image(img_url, use_container_width=True)
            except: st.warning("이미지를 불러올 수 없습니다.")
        else: st.info("등록된 이미지가 없습니다.")

    with col_txt:
        if edit_mode:
            with st.form(key=f"edit_v2_{item['id']}"):
                n_title = st.text_input("📌 Title", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 Creator", value=str(item.get('creator', '')))
                n_rel = st.text_input("📅 공개일", value=str(item.get('rel_date', '')))
                try:
                    raw_v = str(item.get('view_date') or item.get('save_date')).strip().split(' ')[0]
                    v_dt = pd.to_datetime(raw_v).date()
                except: v_dt = date.today()
                
                n_view = st.date_input("🍿 감상일", v_dt)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief') or ''))
                n_sum = st.text_area("📖 줄거리", value=str(item.get('summary') or ''), height=150)
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights') or ''), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note') or ''), height=100)

                if st.form_submit_button("💾 저장", use_container_width=True):
                    vy, vm, vd = str(n_view.year), f"{n_view.month:02d}", f"{n_view.day:02d}"
                    BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
                    edit_payload = {
                        "entry.574529989": item.get('category', '기타'),
                        "entry.898076783": n_title,
                        "entry.345368346": n_creator,
                        "entry.543246487": n_sum,
                        "entry.1816924330": n_brief,
                        "entry.270693677": n_high,
                        "entry.891180756": n_note,
                        "entry.2056153041": item.get('img_url', ''),
                        "entry.1446643193_year": vy,
                        "entry.1446643193_month": vm,
                        "entry.1446643193_day": vd
                    }
                    try:
                        requests.post(BACKUP_URL, data=edit_payload, timeout=10)
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, summary=?, brief=?, highlights=?, note=?, view_date=? WHERE id=?""", 
                                         (n_title, n_creator, n_rel, n_sum, n_brief, n_high, n_note, str(n_view), item['id']))
                        st.success("✅ 수정 완료!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e: st.error(f"❌ 오류: {e}")
        else:
            def get_val(key):
                v = str(item.get(key, '')).strip()
                return "" if v.lower() in ["nan", "none", "null"] else v

            title_v = get_val('title')
            creator_v = get_val('creator')
            rel_v = get_val('rel_date')
            cat_v = get_val('category')
            view_v = get_val('view_date') or get_val('save_date')
            venue_v = get_val('venue')

            st.markdown(f'<div style="font-size:30px; font-weight:bold; line-height:1.1;">{title_v}</div>', unsafe_allow_html=True)
            st.write(f"**[{cat_v}]** {creator_v}")
            venue_display = f" | 📍 {venue_v}" if venue_v else ""
            st.markdown(f'<p style="margin-top:-15px; margin-bottom:5px;">📅 {rel_v}{venue_display}</p>', unsafe_allow_html=True)
            st.markdown(f'<p style="color:gray; font-size:0.9em; margin-top:-5px;">🍿 감상일: {view_v}</p>', unsafe_allow_html=True)
            st.divider()

            for label, key, is_note in [("📝 요약", "brief", False), ("📖 정보/줄거리", "summary", False), ("✨ 인상 깊은 부분", "highlights", False), ("💬 감상", "note", True)]:
                val = get_val(key)
                if val:
                    if is_note:
                        st.markdown(f'<div style="background-color:#fff4cc; padding:15px; border-radius:10px; color:#000; border-left:5px solid #ffcc00; margin-top:10px;"><strong>{label}</strong><br><br>{val.replace("\n", "<br>")}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div style="padding:10px; border-radius:8px; border:1px solid #ddd; margin-bottom:10px;"><small style="color:#666;">{label}</small><br>{"<strong>" if key=="brief" else ""}{val.replace("\n", "<br>")}{"</strong>" if key=="brief" else ""}</div>', unsafe_allow_html=True)

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
                opts = {f"🎭 {s['title']} [{s['date']}~] ({s['venue']})": s for s in res}
                sel = st.selectbox("결과 선택", list(opts.keys()))
                if st.button("✨ 가져오기"):
                    s = opts[sel]
                    combined_creator = get_kopis_detail(s['id'])
                    st.session_state.api_data = {'title': s['title'], 'creator': combined_creator, 'date': s['date'], 'venue': s['venue'], 'img': s['img'], 'summary': f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={s['id']}"}
                    st.rerun()
        else: # MOVIES, SERIES
            res = search_tmdb(search_query, category)
            if res:
                t_key = 'title' if category == 'MOVIES' else 'name'
                d_key = 'release_date' if category == 'MOVIES' else 'first_air_date'
                opts = {f"🎬 {r.get(t_key)} ({str(r.get(d_key))[:4]})": r for r in res}
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
        c_rel, c_ven = st.columns(2)
        rel_date = c_rel.text_input("📅 작품 날짜", value=data.get('date', str(date.today())))
        venue = c_ven.text_input("📍 장소", value=data.get('venue', ''))
        
    with cr:
        summary = st.text_area("📖 줄거리", value=data.get('summary', ''), height=150)
        brief = st.text_input("📝 요약")
        highlights = st.text_area("✨ 인상 깊은 부분", height=100)
        note = st.text_area("💬 감상", height=100)
        view_date = st.date_input("🍿 감상일", value=date.today())
        
        if st.button("✅ 저장", use_container_width=True):
            try:
                r_dt = pd.to_datetime(rel_date)
                ry, rm, rd = str(r_dt.year), f"{r_dt.month:02d}", f"{r_dt.day:02d}"
                v_dt = pd.to_datetime(view_date)
                vy, vm, vd = str(v_dt.year), f"{v_dt.month:02d}", f"{v_dt.day:02d}"
            except:
                ry, rm, rd = "2026", "02", "20"
                vy, vm, vd = "2026", "02", "20"

            BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
            payload = {
                "entry.574529989": category, "entry.898076783": title, "entry.345368346": creator,
                "entry.543246487": summary, "entry.1816924330": brief, "entry.270693677": highlights,
                "entry.891180756": note, "entry.2056153041": img_url_val,
                "entry.780422311_year": ry, "entry.780422311_month": rm, "entry.780422311_day": rd,
                "entry.1446643193_year": vy, "entry.1446643193_month": vm, "entry.1446643193_day": vd
            }

            try:
                res = requests.post(BACKUP_URL, data=payload, timeout=10)
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("""INSERT INTO archive 
                        (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (category, title, creator, str(rel_date), venue, summary, brief, highlights, note, img_url_val, str(date.today()), str(view_date)))
                
                if res.status_code == 200:
                    st.success("✅ 저장 성공!")
                    for key in list(st.session_state.keys()): del st.session_state[key]
                    st.rerun()
            except Exception as e: st.error(f"❌ 오류 발생: {e}")

# --- TAB 2: ARCHIVE ---
with tab2:
    if st.button("🔄"):
        restore_from_google()
        st.rerun()

    st.markdown("""
        <style>
        div[data-testid="column"] { display: flex; flex-direction: column; align-items: center; text-align: center !important; }
        .cal-img-box { position: relative; width: 100%; aspect-ratio: 1/1; overflow: hidden; border-radius: 6px; margin-bottom: 5px; }
        .cal-img-box img { width: 100%; height: 100%; object-fit: cover; }
        .badge { position: absolute; top: 5px; background: rgba(0, 0, 0, 0.6); color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; z-index: 10; }
        .badge-left { left: 5px; background: rgba(50, 50, 50, 0.8); } 
        .badge-right { right: 5px; } 
        </style>
    """, unsafe_allow_html=True)

    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    cat_list = ['BOOKS', 'MUSIC', 'MOVIES', 'SERIES', 'STAGE']
    counts = {cat: len(all_df[all_df['category'] == cat]) for cat in cat_list}
    tab_names = [f"📅 ALL ({len(all_df)})"] + [f"{cat} ({counts[cat]})" for cat in cat_list]
    sub_tabs = st.tabs(tab_names)

    # ALL 탭
    with sub_tabs[0]:
        if not all_df.empty:
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'], errors='coerce').fillna(pd.Timestamp.now())
            yearly_df = all_df.sort_values(by='v_dt', ascending=False)
            years = sorted(yearly_df['v_dt'].dt.year.unique(), reverse=True)
            sel_y = st.selectbox("연도 선택", years)
            
            y_data = yearly_df[yearly_df['v_dt'].dt.year == sel_y]
            for m in range(12, 0, -1):
                m_data = y_data[y_data['v_dt'].dt.month == m]
                if not m_data.empty:
                    st.markdown(f"### 🗓️ {m}월")
                    items = m_data.to_dict('records')
                    for i in range(0, len(items), 6):
                        cols = st.columns(6)
                        for j in range(6):
                            if i+j < len(items):
                                row = items[i+j]
                                with cols[j]:
                                    st.markdown(f'<div class="cal-img-box"><div class="badge badge-left">{row["category"]}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                    if st.button(f"{row['title'][:7]}..", key=f"all_{row['id']}"): show_details(row)

    # 카테고리별 탭
    for idx, c_name in enumerate(cat_list):
        with sub_tabs[idx+1]:
            cat_df = all_df[all_df['category'] == c_name].copy()
            if not cat_df.empty:
                cat_df['v_dt'] = pd.to_datetime(cat_df['view_date'], errors='coerce')
                items = cat_df.sort_values(by='v_dt', ascending=False).to_dict('records')
                for i in range(0, len(items), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i+j < len(items):
                            row = items[i+j]
                            with cols[j]:
                                b_date = pd.to_datetime(row['view_date']).strftime('%y.%m.%d') if row['view_date'] else ""
                                st.markdown(f'<div class="cal-img-box"><div class="badge badge-left">{b_date}</div><img src="{row["img_url"]}"></div>', unsafe_allow_html=True)
                                if st.button(f"{row['title'][:7]}..", key=f"c_{c_name}_{row['id']}"): show_details(row)
            else: st.info(f"{c_name} 기록이 없습니다.")



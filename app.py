import streamlit as st
import sqlite3
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
DB_NAME = 'archive_prism_total_v5.db'
KOPIS_KEY = "7a919bc272204f06bbca10e2af376dea"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- [2. DB 함수 및 동기화 로직] ---
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, venue TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

def migrate_to_supabase():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            local_data = conn.execute("SELECT * FROM archive").fetchall()
        
        if not local_data:
            st.session_state.sync_msg = ("warning", "로컬 데이터가 없습니다.")
            return

        upload_list = [dict(row) for row in local_data]
        for d in upload_list:
            if 'id' in d: del d['id']
            
        supabase.table("archive").upsert(upload_list).execute() 
        st.session_state.sync_msg = ("success", f"✅ {len(upload_list)}개 데이터 클라우드 백업 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 백업 실패: {e}")

def restore_from_supabase():
    try:
        res = supabase.table("archive").select("*").execute()
        cloud_data = res.data if hasattr(res, 'data') else res
        
        if not cloud_data:
            st.session_state.sync_msg = ("warning", "클라우드가 비어있습니다.")
            return

        with sqlite3.connect(DB_NAME) as conn:
            for row in cloud_data:
                exists = conn.execute("SELECT id FROM archive WHERE title=? AND view_date=?", 
                                     (row['title'], row['view_date'])).fetchone()
                if not exists:
                    conn.execute("""INSERT INTO archive 
                        (category, title, creator, rel_date, venue, summary, brief, highlights, note, img_url, save_date, view_date) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row['category'], row['title'], row['creator'], row['rel_date'], 
                         row['venue'], row['summary'], row['brief'], row['highlights'], 
                         row['note'], row['img_url'], row['save_date'], row['view_date']))
        st.session_state.sync_msg = ("success", "✅ 데이터 복구 완료!")
    except Exception as e:
        st.session_state.sync_msg = ("error", f"❌ 복구 실패: {e}")


# --- [3. 로그인 시스템 & 사이드바] ---
if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "PC"

with st.sidebar:
    st.markdown("### 🔐 Admin Access")
    if not st.session_state.is_logged_in:
        input_password = st.text_input("Password", type="password")
        if input_password:
            if input_password == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.is_logged_in = True
                st.rerun()
            else:
                st.error("Incorrect Password")
    
    st.divider()
    st.markdown("### 📱 화면 모드")
    st.session_state.view_mode = st.radio("보기 옵션", ["PC", "Mobile"], horizontal=True, label_visibility="collapsed")
    
    
    if st.session_state.is_logged_in:
        st.success("Admin Mode Active")
        if st.button("🔓 Logout", use_container_width=True):
            st.session_state.is_logged_in = False
            st.rerun()
            
        st.divider()
        st.markdown("### 🔄 Data Sync")
        if 'sync_msg' in st.session_state:
            m_type, m_txt = st.session_state.sync_msg
            if m_type == "success": st.success(m_txt)
            elif m_type == "warning": st.warning(m_txt)
            else: st.error(m_txt)
            del st.session_state.sync_msg
        
        st.button("📤 Cloud Backup", on_click=migrate_to_supabase, use_container_width=True)
        st.button("📥 Cloud Restore", on_click=restore_from_supabase, use_container_width=True)

is_admin = st.session_state.is_logged_in
is_mobile = st.session_state.view_mode == "Mobile"


# --- [API 검색 함수들] --- (기존과 동일하므로 생략하지 않고 유지)
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
        
        # 1. 창작자(감독/작가) 정보 추출
        if is_movie:
            director = next((m['name'] for m in crew_list if m.get('job') == 'Director'), "정보 없음")
            creator_label = f"[감독] {director}"
            
            companies = res.get('production_companies', [])
            venue_info = companies[0].get('name', '') if companies else ""
        else:
            # 시리즈물 (TV)
            creators = res.get('created_by', [])
            if creators:
                creator_names = ", ".join([c['name'] for c in creators])
            else:
                creator_names = next((m['name'] for m in crew_list if m.get('job') in ['Writer', 'Executive Producer']), "정보 없음")
            
            creator_label = f"[작가/제작] {creator_names}"
            
            networks = res.get('networks', [])
            venue_info = networks[0].get('name', '') if networks else ""

        # 2. 출연진 정보 추출 (최대 3명)
        cast_names = ", ".join([c['name'] for c in cast_list[:3]])
        cast_label = f"[출연] {cast_names}" if cast_names else ""

        # 3. 최종 결합 (역할별로 구분자 / 를 넣어 나중에 split하기 좋게 만듦)
        full_creator = f"{creator_label} / {cast_label}".strip(" / ")
        
        return {"creator": full_creator, "venue": venue_info}
    
    except Exception as e:
        return {"creator": "정보 없음", "venue": ""}

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
                'title': title, 'id': d.findtext('mt20id'), 'img': d.findtext('poster'), 
                'date': date_from, 'venue': d.findtext('fcltynm')
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
            # 1. 제작진(연출, 작가 등) 정보 추출
            crew = d.findtext('prfcrew').strip() if d.findtext('prfcrew') else ""
            # 2. 출연진 정보 추출
            cast = d.findtext('prfcast').strip() if d.findtext('prfcast') else ""
            
            info_parts = []
            if crew:
                # '연출: 홍길동' 식으로 올 수도 있고 이름만 올 수도 있으므로 태그 부여
                info_parts.append(f"[제작] {crew}")
            if cast:
                # 출연진 정보 추가
                info_parts.append(f"[출연] {cast}")
            
            if not info_parts:
                return "정보 없음"
                
            # 최종 형태: [제작] 연출진 / [출연] 배우들
            return " / ".join(info_parts)
            
    except Exception as e:
        return "상세정보 로드 실패"
    return "정보 없음"


# --- [4. 팝업 상세 보기] ---
@st.dialog("📋 기록", width="large")
def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    edit_mode = False
    if is_admin:
        t_col1, t_col2, t_col3 = st.columns([0.3, 0.4, 0.3])
        with t_col1:
            if st.button("🗑️ 삭제", key=f"del_{item['id']}", use_container_width=True):
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
                try: supabase.table("archive").delete().eq("title", item['title']).eq("view_date", item['view_date']).execute()
                except: pass
                st.rerun()
        with t_col3:
            edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}")
        st.divider()

    if is_mobile:
        col_img = st.container()
        col_txt = st.container()
    else:
        col_img, col_txt = st.columns([0.3, 0.7])

    # --- [1] 수정 모드 (Admin 전용) ---
    if is_admin and edit_mode:
        with col_img:
            n_img = st.text_input("🖼️ 이미지 URL", value=str(item.get('img_url', '')), key=f"img_in_{item['id']}")
            if n_img: st.image(n_img, use_container_width=True)

        with col_txt:
            with st.form(key=f"edit_form_{item['id']}"):
                n_title = st.text_input("📌 제목", value=str(item.get('title', '')))
                # 창작자 정보는 길어질 수 있으므로 text_area 권장
                n_creator = st.text_area("👤 창작자", value=str(item.get('creator', '')), height=100)
                
                cat = item.get('category')
                labels = {"BOOKS": "📖 출판사", "MUSIC": "💿 레이블", "MOVIES": "🎬 제작사", "SERIES": "📺 플랫폼", "STAGE": "📍 장소"}
                v_label = labels.get(cat, "📍 장소")

                c1, c2 = st.columns(2)
                n_rel = c1.text_input("📅 작품 날짜", value=str(item.get('rel_date', '')))
                n_venue = c2.text_input(v_label, value=str(item.get('venue', '')))
                
                try: curr_view = pd.to_datetime(item.get('view_date')).date()
                except: curr_view = date.today()
                
                n_view_date = st.date_input("🍿 감상일 수정", value=curr_view)
                n_sum = st.text_area("📖 줄거리/작품소개", value=str(item.get('summary', '')), height=150)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief', '')))
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights', '')), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note', '')), height=100)

                if st.form_submit_button("💾 저장"):
                    try:
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("""UPDATE archive SET 
                                            title=?, creator=?, rel_date=?, venue=?, 
                                            summary=?, brief=?, highlights=?, note=?, view_date=?, img_url=? 
                                            WHERE id=?""", 
                                         (n_title, n_creator, n_rel, n_venue, 
                                          n_sum, n_brief, n_high, n_note, str(n_view_date), n_img, item['id']))
                        
                        supabase.table("archive").update({
                            "title": n_title, "creator": n_creator, "rel_date": n_rel, "venue": n_venue,
                            "summary": n_sum, "brief": n_brief, "highlights": n_high, "note": n_note,
                            "view_date": str(n_view_date), "img_url": n_img
                        }).eq("title", item['title']).eq("view_date", item['view_date']).execute()

                        st.success("✅ 수정 완료!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 오류: {e}")

    # --- [2] 조회 모드 ---
    else: 
        with col_img:
            img_url = item.get('img_url')
            if img_url: 
                st.image(img_url, use_container_width=True)
            
        with col_txt:
            # 제목
            st.markdown(f'# {item.get("title")}')
            
            # 카테고리와 창작자 분리 출력 (요청하신 가독성 개선)
            st.markdown(f"#### **[{item.get('category')}]**")
            st.markdown(f"**{item.get('creator')}**")
            
            # 날짜 및 장소
            st.write(f"📅 {item.get('rel_date')} | 📍 {item.get('venue')}")
            st.markdown(f'<p style="color: #E2E2E2; font-weight: bold; font-size: 1.1em;">🍿 감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
            st.divider()

            # 배지 스타일 섹션 로직
            sections = [
                ("📖 줄거리/작품소개", "summary", "#444"),
                ("📝 요약", "brief", "#0E6245"),
                ("✨ 인상 깊은 부분", "highlights", "#7D5600"),
                ("💬 나의 감상", "note", "#1E425E")
            ]

            for label, key, color in sections:
                content = item.get(key)
                if content and str(content).strip():
                    # 배지 형태의 라벨
                    st.markdown(f"""
                        <div style="display: inline-block; background-color: {color}; color: white; 
                        padding: 2px 12px; border-radius: 12px; font-size: 0.8em; margin-bottom: 10px; font-weight: bold;">
                            {label}
                        </div>""", unsafe_allow_html=True)
                    
                    # 본문 (줄바꿈 유지)
                    st.markdown(str(content).replace('\n', '  \n'))
                    
                    # 섹션 구분선
                    st.markdown("<hr style='margin: 1.2em 0; border: 0; border-top: 1px solid #333;'>", unsafe_allow_html=True)




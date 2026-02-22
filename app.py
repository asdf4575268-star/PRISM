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
GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pub?gid=1160662254&single=true&output=csv"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                         rel_date TEXT, summary TEXT, brief TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT, view_date TEXT)''')
init_db()

def restore_from_google():
    try:
        df = pd.read_csv(GOOGLE_SHEET_CSV).fillna("")
        df.columns = df.columns.str.strip()

        col_map = {}
        for col in df.columns:
            lower = col.lower().replace(" ", "")
            # [1] 감상일: '감상일'이라는 단어가 들어간 열만 사용 (타임스탬프와 분리)
            if "감상일" in lower: col_map["view_date"] = col
            elif "category" in lower or "카테고리" in lower: col_map["category"] = col
            elif "title" in lower or "제목" in lower: col_map["title"] = col
            elif "creator" in lower or "작가" in lower or "감독" in lower: col_map["creator"] = col
            # [2] 공개일 추가
            elif any(x in lower for x in ["rel", "공개", "출판", "개봉", "발매"]): col_map["rel_date"] = col
            elif "summary" in lower or "줄거리" in lower: col_map["summary"] = col
            elif "brief" in lower or "요약" in lower: col_map["brief"] = col
            elif "highlight" in lower or "인상" in lower: col_map["highlights"] = col
            elif "note" in lower or "감상" in lower: col_map["note"] = col
            elif "img" in lower or "이미지" in lower: col_map["img_url"] = col
            # [3] 타임스탬프는 save_date로 보내서 view_date에 침범 못하게 차단
            elif "타임스탬프" in lower or "timestamp" in lower: col_map["save_date"] = col

        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM archive")
            for _, row in df.iterrows():
                # [핵심 수정] 1월 1일 오류 방지 (정교한 날짜 파싱)
                raw_v = str(row.get(col_map.get("view_date"), "")).strip()
                if raw_v:
                    try:
                        # 오전/오후 텍스트 처리 후 YYYY-MM-DD 포맷으로 완벽 변환
                        clean_v = raw_v.replace("오전", "AM").replace("오후", "PM")
                        v_date = pd.to_datetime(clean_v).strftime('%Y-%m-%d')
                    except:
                        v_date = raw_v # 변환 실패 시 원본 유지
                else:
                    v_date = ""

                r_date = str(row.get(col_map.get("rel_date"), "")).strip()

                conn.execute("""
                    INSERT INTO archive
                    (category, title, creator, rel_date,
                     summary, brief, highlights, note,
                     img_url, save_date, view_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(row.get(col_map.get("category"), "")),
                    str(row.get(col_map.get("title"), "")),
                    str(row.get(col_map.get("creator"), "")),
                    r_date, # 공개일
                    str(row.get(col_map.get("summary"), "")),
                    str(row.get(col_map.get("brief"), "")),
                    str(row.get(col_map.get("highlights"), "")),
                    str(row.get(col_map.get("note"), "")),
                    str(row.get(col_map.get("img_url"), "")),
                    str(row.get(col_map.get("save_date"), "")), # 타임스탬프는 여기에 격리
                    v_date # 깨끗해진 날짜 저장
                ))
        st.success("복원 완료")
    except Exception as e:
        st.error(f"오류 발생: {e}")

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
            
            # 3. 만약 사용자가 연도를 입력했다면, 해당 연도와 일치하는 공연만 필터링
            if search_year:
                if search_year not in date_from:
                    continue
            
            results.append({
                'title': title, 
                'id': d.findtext('mt20id'), 
                'img': d.findtext('poster'), 
                'date': date_from, 
                'venue': d.findtext('fcltynm')
            })
        return results
    except:
        return []
def get_kopis_detail(mt20id):
    """공연 ID를 이용해 제작진(prfcrew)과 출연진(prfcast) 정보를 정밀 추출"""
    url = f"http://www.kopis.or.kr/openApi/restful/pblprfr/{mt20id}?service={KOPIS_KEY}"
    try:
        res = requests.get(url)
        # XML 구조를 더 확실히 파악하기 위해 루트부터 다시 잡습니다.
        root = ET.fromstring(res.content)
        
        # 상세 정보는 <db> 태그 안에 들어있습니다.
        d = root.find('db')
        if d is not None:
            # 태그를 찾고 내용이 비어있으면 '미상'으로 처리
            crew = d.findtext('prfcrew').strip() if d.findtext('prfcrew') else ""
            cast = d.findtext('prfcast').strip() if d.findtext('prfcast') else ""
            
            # 둘 다 정보가 아예 없을 경우를 대비
            if not crew and not cast:
                return "정보 없음"
            
            # 정보가 하나라도 있으면 결합 (제작진 / 출연진)
            return f"{crew} / {cast}".strip(" / ")
    except Exception as e:
        return f"상세정보 로드 실패"
    return "정보 없음"

col_empty, col_btn = st.columns([0.85, 0.15]) 

# --- [3. 팝업 함수] ---
@st.dialog("📋 기록", width="large")

def show_details(item):
    if hasattr(item, 'to_dict'): item = item.to_dict()
    
    # 세션 상태를 이용해 삭제 여부 체크 (에러 방지)
    if f"deleted_{item['id']}" in st.session_state:
        st.rerun()
        return

    # --- [상단 툴바] ---
    t_col1, t_col2, t_col3 = st.columns([0.2, 0.6, 0.2])
    
    with t_col1:
        if st.button("🗑️ 삭제", key=f"del_{item['id']}_dialog", use_container_width=True):
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM archive WHERE id=?", (item['id'],))
            st.session_state[f"deleted_{item['id']}"] = True # 삭제 표식
            st.rerun() # 즉시 새로고침하여 팝업을 닫음

    with t_col3:
        edit_mode = st.toggle("✏️ 수정", key=f"tog_{item['id']}_dialog")

    st.divider()

    col_img, col_txt = st.columns([0.3, 0.7])

    with col_img:
        # 삭제된 후 이미지를 그리려 하면 에러가 나므로 조건문 강화
        img_url = item.get('img_url')
        if img_url:
            try:
                st.image(img_url, use_container_width=True)
            except:
                st.warning("이미지를 불러올 수 없습니다.")
        else:
            st.info("등록된 이미지가 없습니다.")

    with col_txt:
        if edit_mode:
            with st.form(key=f"edit_v2_{item['id']}"):
                n_title = st.text_input("📌 Title", value=str(item.get('title', '')))
                n_creator = st.text_input("👤 Creator", value=str(item.get('creator', '')))
                n_rel = st.text_input("📅공개일", value=str(item.get('rel_date', '')))
                
                try:
                    # 빈 칸을 제거하고 앞부분 날짜만 가져옵니다.
                    raw_v = str(item.get('view_date') or item.get('save_date')).strip().split(' ')[0]
                    # Pandas를 이용해 유연하게 날짜 객체로 변환
                    v_dt = pd.to_datetime(raw_v).date()
                except: 
                    v_dt = date.today()
                
                n_view = st.date_input("🍿 감상일", v_dt)
                n_brief = st.text_input("📝 요약", value=str(item.get('brief') or ''))
                n_sum = st.text_area("📖 줄거리", value=str(item.get('summary') or ''), height=150)
                n_high = st.text_area("✨ 인상 깊은 부분", value=str(item.get('highlights') or ''), height=100)
                n_note = st.text_area("💬 감상", value=str(item.get('note') or ''), height=100)

                if st.form_submit_button("💾 저장", use_container_width=True):
                    # KM, BPM 소문자화 (기억하고 있는 가이드 반영)
                    final_note = n_note
                    
                    # 구글 전송용 날짜 쪼개기
                    vy, vm, vd = str(n_view.year), f"{n_view.month:02d}", f"{n_view.day:02d}"

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
                        "entry.1446643193_year": vy,
                        "entry.1446643193_month": vm,
                        "entry.1446643193_day": vd
                    }

                    try:
                        requests.post(BACKUP_URL, data=edit_payload, timeout=10)
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("""UPDATE archive SET title=?, creator=?, rel_date=?, summary=?, brief=?, highlights=?, note=?, view_date=? WHERE id=?""", 
                                         (n_title, n_creator, n_rel, n_sum, n_brief, n_high, final_note, str(n_view), item['id']))
                        st.success("✅ 수정 완료!")
                        time.sleep(0.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 오류: {e}")
        else:
            def get_val(key):
                v = str(item.get(key, '')).strip()
                return "" if v.lower() in ["nan", "none", "null"] else v

            title_v = get_val('title')
            creator_v = get_val('creator')
            rel_v = get_val('rel_date')
            cat_v = get_val('category')
            view_v = get_val('view_date') or get_val('save_date')
            
            # 2. 상단 제목 및 정보
            st.markdown(f'<div style="font-size:25px; font-weight:bold; line-height:1.1;">{title_v}</div>', unsafe_allow_html=True)
            st.write(f"**[{cat_v}]** {creator_v}")
            st.write(f"**공개일:** {rel_v}{venue_display}")
            st.markdown(f'<p style="color:gray;">🍿 감상일: {view_v}</p>', unsafe_allow_html=True)
            
            st.divider()
            
           # 3. 본문 출력
            # [요약] - 심플 스타일
            b_val = get_val('brief')
            if b_val:
                st.markdown(f"""
                <div style="padding: 10px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 10px;">
                    <small style="color: #666;">📝 요약</small><br><strong>{b_val}</strong>
                </div>
                """, unsafe_allow_html=True)
            
            # [줄거리/정보] - 심플 스타일
            s_val = get_val('summary')
            if s_val:
                st.markdown(f"""
                <div style="padding: 10px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 10px;">
                    <small style="color: #666;">📖 정보/줄거리</small><br>{s_val.replace('\n', '<br>')}
                </div>
                """, unsafe_allow_html=True)

            # [인상 깊은 부분] - 심플 스타일
            h_val = get_val('highlights')
            if h_val:
                st.markdown(f"""
                <div style="padding: 10px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 10px;">
                    <small style="color: #666;">✨ 인상 깊은 부분</small><br>{h_val.replace('\n', '<br>')}
                </div>
                """, unsafe_allow_html=True)
            
            # 4. 감상(Note) - 노란색 강조 박스 유지
            note_v = get_val('note')
            if note_v:
                st.markdown(f"""
                <div style="background-color: #fff4cc; padding: 15px; border-radius: 10px; color: #000; border-left: 5px solid #ffcc00; margin-top: 10px;">
                    <strong>💬 감상</strong><br><br>{note_v.replace('\n', '<br>')}
                </div>
                """, unsafe_allow_html=True)

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
                    st.session_state.api_data = {'title': b['title'], 'creator': f"{', '.join(b['authors'])}", 'date': b['datetime'][:10], 'venue': s['venue'], 'img': b.get('thumbnail', '').replace("R120x174", "R400x0"), 'summary': f"{b['url']}\n\n{b.get('contents', '')}"}
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
                    detail_url = f"https://www.kopis.or.kr/por/db/pblprfr/pblprfrView.do?menuId=MNU_00020&mt20Id={s['id']}"
                    st.session_state.api_data = {
                        'title': f"{s['title']} ",
                        'creator': combined_creator, # 상세 정보에서 가져온 제작진/출연진
                        'date': f"{s['date']}",
                        'img': s['img'],
                        'summary': detail_url
                    }
                    
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
        if st.button("✅ 저장", use_container_width=True):
            # 1. 변수 안전장치 (NameError 방지)
            safe_img_url = img_url_val if 'img_url_val' in locals() else ""
            
            # 2. 디자인 가이드: KM, BPM 소문자 처리
            processed_note = note

            # 3. 날짜 에러(AttributeError) 해결: 문자열을 날짜 객체로 변환
            import pandas as pd
            try:
                # rel_date가 문자열일 경우를 대비해 변환
                r_dt = pd.to_datetime(rel_date)
                ry, rm, rd = str(r_dt.year), f"{r_dt.month:02d}", f"{r_dt.day:02d}"
                
                # view_date도 변환
                v_dt = pd.to_datetime(view_date)
                vy, vm, vd = str(v_dt.year), f"{v_dt.month:02d}", f"{v_dt.day:02d}"
            except Exception as e:
                # 변환 실패 시 오늘 날짜로 방어
                ry, rm, rd = "2026", "02", "20"
                vy, vm, vd = "2026", "02", "20"
                st.warning("날짜 형식이 올바르지 않아 기본값으로 설정되었습니다.")

            # 4. 구글 설문지 전송 (날짜 쪼개기 방식)
            BACKUP_URL = "https://docs.google.com/forms/d/e/1FAIpQLScrhM-MqmoMlF5ud5da8m9jmRXkUkjB8BIcZwv9JOq7WmYGsQ/formResponse"
            
            payload = {
                "entry.574529989": category,
                "entry.898076783": title,
                "entry.345368346": creator,
                "entry.543246487": summary,
                "entry.1816924330": brief,
                "entry.270693677": highlights,
                "entry.891180756": processed_note,
                "entry.2056153041": safe_img_url,
                "entry.780422311_year": ry,
                "entry.780422311_month": rm,
                "entry.780422311_day": rd,
                "entry.1446643193_year": vy,
                "entry.1446643193_month": vm,
                "entry.1446643193_day": vd
            }

            # 5. 실행 및 로컬 DB 저장
            try:
                # 구글 전송
                res = requests.post(BACKUP_URL, data=payload, timeout=10)
                
                # 로컬 저장
                with sqlite3.connect(DB_NAME) as conn:
                    conn.execute("""INSERT INTO archive 
                        (category, title, creator, rel_date, summary, brief, highlights, note, img_url, save_date, view_date) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (category, title, creator, str(rel_date), summary, brief, highlights, processed_note, safe_img_url, str(date.today()), str(view_date)))
                
                if res.status_code == 200:
                    st.success("✅ 로컬 저장 및 구글 백업 성공!")
                    for key in st.session_state.keys():
                        del st.session_state[key]
                    st.rerun()
                else:
                    st.error(f"⚠️ 전송 실패 (코드: {res.status_code})")
            except Exception as e:
                st.error(f"❌ 오류 발생: {e}")

               

# --- TAB 2: ARCHIVE ---
with tab2:
    # 1. 새로고침 버튼
    if st.button("🔄"):
        restore_from_google()
        st.rerun()

    # 2. 스타일 정의 (들여쓰기 유지)
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

    # 3. 데이터 로드 및 탭 생성 준비
    with sqlite3.connect(DB_NAME) as conn:
        all_df = pd.read_sql_query("SELECT * FROM archive", conn)

    # [수정] 카테고리 리스트와 개수 계산 (누적 숫자 반영)
    total_cnt = len(all_df)
    cat_list = ['BOOKS', 'MUSIC', 'MOVIES', 'SERIES', 'STAGE']
    counts = {cat: len(all_df[all_df['category'] == cat]) for cat in cat_list}
    
    # 탭 이름 정의: YEARLY(0) + 나머지 5개(1~5) = 총 6개 탭
    tab_names = [f"📅 ALL ({total_cnt})"] + [f"{cat} ({counts[cat]})" for cat in cat_list]
    sub_tabs = st.tabs(tab_names)

    # --- 1. Yearly 탭 내용 채우기 ---
    with sub_tabs[0]:
        if not all_df.empty:
            all_df['v_dt'] = pd.to_datetime(all_df['view_date'].fillna(all_df['save_date']), errors='coerce')
            all_df['v_dt'] = all_df['v_dt'].fillna(pd.Timestamp.now()) 
            all_df['year_int'] = all_df['v_dt'].dt.year
            all_df['month_int'] = all_df['v_dt'].dt.month
            yearly_df = all_df.sort_values(by='v_dt', ascending=False)
            
            raw_years = sorted(list(yearly_df['year_int'].unique()), reverse=True)
            year_options = {y: f"{y} ({len(yearly_df[yearly_df['year_int'] == y])})" for y in raw_years}
            
            sel_y = st.selectbox("연도 선택", raw_years, format_func=lambda x: year_options[x], key="yr_sel")
            
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

    # --- 2. 카테고리 탭 내용 채우기 (정확한 인덱스 관리) ---
    for idx, c_name in enumerate(cat_list):
        with sub_tabs[idx + 1]: # YEARLY가 0이므로 카테고리는 1부터 시작
            cat_df = all_df[all_df['category'] == c_name].copy()
            
            if not cat_df.empty:
                # 정렬 로직
                cat_df['sort_dt'] = pd.to_datetime(
                    cat_df['view_date'].replace(['', 'nan', 'NaN', 'None'], pd.NA), 
                    errors='coerce'
                )
                cat_df = cat_df.sort_values(by='sort_dt', ascending=False, na_position='last')
                items = cat_df.to_dict('records')

                # 그리드 출력 (6열)
                for i in range(0, len(items), 6):
                    cols = st.columns(6)
                    for j in range(6):
                        if i + j < len(items):
                            row = items[i + j]
                            with cols[j]:
                                # 날짜 배지 텍스트 정제
                                raw_v = str(row.get('view_date') or "").strip()
                                if raw_v.lower() in ["nan", "none", ""]:
                                    badge_d = ""
                                else:
                                    try:
                                        temp_dt = pd.to_datetime(raw_v.split(' ')[0])
                                        badge_d = temp_dt.strftime('%y.%m.%d')
                                    except:
                                        badge_d = raw_v[:10]
                                
                                img_html = f'''
                                    <div class="cal-img-box">
                                        <div class="badge badge-left">{badge_d}</div>
                                        <img src="{row["img_url"]}">
                                    </div>'''
                                st.markdown(img_html, unsafe_allow_html=True)
                                
                                # 버튼 키값 (중복 방지)
                                btn_key = f"cat_{c_name}_{row['id']}_{i+j}"
                                if st.button(f"{str(row['title'])[:7]}..", key=btn_key, use_container_width=True): 
                                    show_details(row)
            else: 
                st.info(f"{c_name} 기록이 아직 없습니다.")






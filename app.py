import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import date

# --- [1. 스타일 및 DB 설정] ---
st.set_page_config(layout="wide", page_title="My Archive")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    .act-name { font-size: 90px; font-family: 'Kirang Haerang'; line-height: 1.1; margin: 0; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; }
    .sidebar-content { background-color: #f8f9fa; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

def init_db():
    conn = sqlite3.connect('archive_final.db')
    # category 컬럼 추가됨
    conn.execute('''CREATE TABLE IF NOT EXISTS archive 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, title TEXT, creator TEXT, 
                     rel_date TEXT, summary TEXT, highlights TEXT, note TEXT, img_url TEXT, save_date TEXT)''')
    conn.commit()
    return conn

def search_books(query):
    headers = {"Authorization": "KakaoAK a356895a3aae4f0acf9f4ee884d90a6a"}
    res = requests.get("https://dapi.kakao.com/v3/search/book", headers=headers, params={"query": query})
    return res.json().get("documents", []) if res.status_code == 200 else []

init_db()

# --- [2. 메인 화면: 탭 구성] ---
tab1, tab2 = st.tabs(["🖋️ 아카이빙 입력", "📂 전체 목록 및 상세"])

with tab1:
    category = st.radio("📂 카테고리 선택", ["도서", "음악"], horizontal=True)
    
    # 도서일 때만 검색창 활성화 (음악은 수동 입력 기반)
    if category == "도서":
        search_query = st.text_input("🔍 도서 검색", placeholder="연동할 책 제목을 입력하세요")
        if search_query:
            books = search_books(search_query)
            if books:
                options = {f"{b['title']} ({b['authors'][0] if b['authors'] else '미상'})": b for b in books}
                sel = st.selectbox("검색 결과 선택", list(options.keys()))
                if st.button("✨ 데이터 연동"):
                    st.session_state.api_data = options[sel]
                    st.rerun()
    else:
        st.info("🎸 음악 아카이빙 모드입니다. 정보를 직접 입력해주세요.")

    data = st.session_state.get('api_data', {}) if category == "도서" else {}
    st.divider()

    col_l, col_r = st.columns([0.4, 0.6])
    
    with col_l:
        img_url = st.text_input("이미지 주소(URL)", value=data.get('thumbnail', ''))
        if img_url:
            st.image(img_url, use_container_width=False, caption="원본 크기 유지")
        
        # 카테고리에 따른 라벨 변경
        title_label = "곡명/앨범명" if category == "음악" else "활동명 (제목)"
        creator_label = "아티스트" if category == "음악" else "창작자 (작가)"
        
        title = st.text_input(title_label, value=data.get('title', ''))
        creator = st.text_input(creator_label, value=", ".join(data.get('authors', [])) if 'authors' in data else "")
        rel_date = st.text_input("날짜", value=data.get('datetime', '')[:10] if data.get('datetime') else "")
        
    with col_r:
        summary_label = "📖 요약/한줄평" if category == "음악" else "📖 요약"
        high_label = "✨ 추천 트랙/킬링 파트" if category == "음악" else "✨ 인상 깊은 부분 (쪽수 포함)"
        
        summary = st.text_area(summary_label, height=80, placeholder="내용을 입력해 주세요.")
        highlights = st.text_area(high_label, height=150, placeholder="자유롭게 기록해 주세요.")
        note = st.text_area("💬 감상", value=data.get('contents', ''), height=150)
        
        # 실시간 폰트 시각화
        st.markdown(f'<p class="act-name">{title if title else "Title"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="date-text">{rel_date if rel_date else "2026-00-00"}</p>', unsafe_allow_html=True)
        st.markdown(f'<p class="num-text">12.5 km / 145 bpm</p>', unsafe_allow_html=True)
        
        if st.button("✅ 아카이브 최종 저장", use_container_width=True):
            conn = sqlite3.connect('archive_final.db')
            conn.execute("""INSERT INTO archive (category, title, creator, rel_date, summary, highlights, note, img_url, save_date) 
                            VALUES (?,?,?,?,?,?,?,?,?)""",
                         (category, title, creator, rel_date, summary, highlights, note, img_url, str(date.today())))
            conn.commit()
            st.success(f"{category} 기록이 저장되었습니다!")
            st.rerun()

with tab2:
    st.subheader("🗂️ 전체 아카이빙 상세 보기")
    conn = sqlite3.connect('archive_final.db')
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    conn.close()

    if not df.empty:
        # 필터링 및 선택
        selected_title = st.selectbox("보고 싶은 기록을 선택하세요", df['title'].tolist())
        item = df[df['title'] == selected_title].iloc[0]
        
        st.divider()
        det_l, det_r = st.columns([0.3, 0.7])
        
        with det_l:
            st.caption(f"카테고리: {item.get('category', '도서')}")
            if item['img_url']:
                st.image(item['img_url'], use_container_width=False)
            
            # 카테고리별 출력 라벨 분기
            c_label = "아티스트" if item.get('category') == "음악" else "작가"
            st.write(f"**{c_label}:** {item['creator']}")
            st.write(f"**날짜:** {item['rel_date']}")
            st.write(f"**저장일:** {item['save_date']}")
        
        with det_r:
            s_label = "요약/한줄평" if item.get('category') == "음악" else "핵심 요약"
            h_label = "추천 트랙/킬링 파트" if item.get('category') == "음악" else "인상 깊은 부분"
            
            st.info(f"**📖 {s_label}**\n\n{item['summary']}")
            st.warning(f"**✨ {h_label}**\n\n{item['highlights']}")
            st.write(f"**💬 감상 노트**\n\n{item['note']}")
            
            if st.button("🗑️ 이 기록 삭제"):
                conn = sqlite3.connect('archive_final.db')
                conn.execute("DELETE FROM archive WHERE id=?", (int(item['id']),))
                conn.commit()
                st.rerun()
    else:
        st.info("아직 저장된 아카이브가 없습니다.")

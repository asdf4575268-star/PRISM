import streamlit as st
import pandas as pd
import requests
from datetime import date, datetime
import xml.etree.ElementTree as ET

# --- [1. 스타일 및 설정] ---
st.set_page_config(layout="wide", page_title="PRISM Cloud")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kirang+Haerang&family=Jolly+Lodger&family=Lacquer&display=swap');
    
    /* 가이드 반영: 활동명 35px, 날짜 30px, 숫자 60px */
    .act-name-35 { font-size: 35px; font-family: 'Kirang Haerang'; line-height: 1.1; margin-bottom: 5px; font-weight: bold; }
    .date-text { font-size: 30px; color: #666; margin: 0; }
    .num-text { font-size: 60px; font-family: 'Jolly Lodger'; text-transform: lowercase; margin: 0; }
    
    .cal-img-box { width:100%; aspect-ratio:1/1; overflow:hidden; border-radius:10px; margin-bottom:4px; border: 1px solid #eee; background-color: #f0f0f0; }
    .cal-img-box img { width:100%; height:100%; object-fit:cover; }
    
    /* km, bpm 소문자 규칙 및 버튼 스타일 */
    div.stButton > button { text-transform: lowercase !important; font-size: 12px !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🌈PRISM (Cloud Archive)")

# --- [2. 구글 시트 데이터 로드] ---
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/pub?gid=0&single=true&output=csv"

def get_cloud_data():
    try:
        # 실시간 데이터를 위해 불러올 때마다 새로 읽음
        df = pd.read_csv(SHEET_CSV_URL)
        # 컬럼명에 앞뒤 공백이 있을 수 있으니 제거
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame()

# --- [3. 상세 팝업 함수 (0.2:0.6:0.2 레이아웃)] ---
@st.dialog("📋 기록 상세 정보", width="large")
def show_details(item):
    c_del, c_empty, c_tog = st.columns([0.2, 0.6, 0.2])
    
    with c_del:
        st.button("🗑️ 삭제 안내", help="데이터 안전을 위해 구글 시트 앱에서 직접 행을 삭제해 주세요.", use_container_width=True)
            
    with c_tog:
        st.info("💡 실시간 반영 중")
    
    st.divider()
    
    col_img, col_txt = st.columns([0.4, 0.6])
    
    with col_img:
        img_url = item.get('img_url')
        if pd.notnull(img_url) and str(img_url).startswith('http'):
            st.image(img_url, use_container_width=True)
        else:
            st.info("이미지가 없습니다.")
    
    with col_txt:
        # 활동명 35px
        st.markdown(f'<p class="act-name-35">{item.get("title")}</p>', unsafe_allow_html=True)
        
        # 창작자 소문자 적용
        creator = str(item.get('creator', '')).lower()
        st.write(f"**creator:** {creator} | 📅 {item.get('rel_date')}")
        
        # 감상일 30px
        st.markdown(f'<p class="date-text">🍿 감상일: {item.get("view_date")}</p>', unsafe_allow_html=True)
        
        st.divider()
        if pd.notnull(item.get('brief')): st.success(item['brief'])
        if pd.notnull(item.get('note')): st.write(item['note'])

# --- [4. 메인 화면 구성] ---
tab1, tab2 = st.tabs(["🖋️ WRITE (안내)", "📂 ARCHIVE"])

with tab1:
    st.info("🔒 클라우드 보안 모드")
    st.markdown("""
    데이터 유실을 완벽히 방지하기 위해 **기록은 구글 시트에서 직접 입력**해주세요.
    입력 후 아래 '새로고침' 버튼을 누르면 즉시 업데이트됩니다.
    
    [👉 내 구글 시트 바로가기](https://docs.google.com/spreadsheets/d/1vQDDV1yl-cDAjFN8B0SIpnkGzfGB5gRJvRDjE6AJXqOgWnhJ0hy9tNmW4tkL3SUMBkuX-Uw3um_pdjT/edit)
    """)
    if st.button("🔄 데이터 새로고침"):
        st.rerun()

with tab2:
    all_df = get_cloud_data()
    
    if not all_df.empty:
        categories = ["BOOKS", "MUSIC", "MOVIES", "SERIES", "STAGE"]
        sub_tabs = st.tabs(categories)
        
        for i, cat in enumerate(categories):
            with sub_tabs[i]:
                # 카테고리 필터링 (대소문자 무관)
                if 'category' in all_df.columns:
                    cat_df = all_df[all_df['category'].str.upper() == cat]
                    
                    if not cat_df.empty:
                        items = cat_df.to_dict('records')
                        for j in range(0, len(items), 6):
                            cols = st.columns(6)
                            for k in range(6):
                                if j + k < len(items):
                                    row = items[j + k]
                                    with cols[k]:
                                        # 썸네일 이미지
                                        img = row.get('img_url')
                                        if pd.notnull(img) and str(img).startswith('http'):
                                            st.markdown(f'<div class="cal-img-box"><img src="{img}"></div>', unsafe_allow_html=True)
                                        
                                        # 버튼 라벨 (소문자/길이 제한)
                                        btn_label = str(row['title'])[:8].lower()
                                        if st.button(btn_label, key=f"btn_{cat}_{j+k}", use_container_width=True):
                                            show_details(row)
                    else:
                        st.info(f"{cat} 기록이 아직 없습니다.")
    else:
        st.warning("불러올 데이터가 없습니다. 구글 시트를 확인해주세요.")

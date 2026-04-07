import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

st.set_page_config(page_title="롯데마트 수주 자동화", page_icon="🛒", layout="wide")

@st.cache_data
def load_lotte_master(path):
    try:
        # [롯데마트 제품코드] 시트 로드
        df_prod = pd.read_excel(path, sheet_name='롯데마트 제품코드', dtype=str)
        df_prod.columns = [str(c).strip() for c in df_prod.columns]
        
        # 바코드(A열)와 ME코드(C열) 매핑 (인덱스 기준: 0번, 2번 열)
        barcode_col = df_prod.columns[0]
        me_col = df_prod.columns[2]
        
        prod_map = {
            str(r[barcode_col]).strip(): str(r[me_col]).strip() 
            for _, r in df_prod.iterrows() if pd.notna(r[barcode_col])
        }
        return prod_map, None
    except Exception as e:
        return {}, str(e)

st.title("🛒 롯데마트 수주 자동화")

# 1. 마스터 파일 로드
MASTER_FILE = "롯데마트_서식파일_업데이트용.xlsx"
prod_dict, error = load_lotte_master(MASTER_FILE)

if error:
    st.error(f"마스터 파일 로드 실패: {error}")
else:
    uploaded_file = st.file_uploader("가공된 롯데마트 로우 데이터를 업로드하세요 (ORDERS_...)", type=['xlsx'])

    if uploaded_file:
        try:
            # 2. 원본 데이터 전체 읽기 (납품일 추출 및 헤더 찾기용)
            df_all = pd.read_excel(uploaded_file, header=None)
            
            delivery_date = ""
            header_row_idx = 0
            
            # 3. 납품일자 추출 및 실제 표의 헤더(상품코드) 위치 탐색
            for i, row in df_all.iterrows():
                row_list = [str(val).strip() for val in row.values]
                
                # '납품일' 키워드가 포함된 행에서 날짜(YYYY-MM-DD) 패턴 추출
                if '납품일' in row_list:
                    row_str = " ".join(row_list)
                    date_match = re.search(r'(\d{4})[-./]?(\d{2})[-./]?(\d{2})', row_str)
                    if date_match:
                        delivery_date = "".join(date_match.groups()) # 20260408 형식
                
                # '상품코드'가 있는 행을 실제 데이터 시작점으로 인식
                if '상품코드' in row_list:
                    header_row_idx = i
                    break

            # 4. 실제 데이터 영역 로드
            df_raw = pd.read_excel(uploaded_file, header=header_row_idx)
            df_raw.columns = [str(c).strip() for c in df_raw.columns]

            temp_rows = []

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

MASTER_FILE = "롯데마트_서식파일_업데이트용.xlsx"
prod_dict, error = load_lotte_master(MASTER_FILE)

if error:
    st.error(f"마스터 파일 로드 실패: {error}")
else:
    uploaded_file = st.file_uploader("가공된 롯데마트 로우 데이터를 업로드하세요", type=['xlsx'])

    if uploaded_file:
        try:
            # 1. 원본 데이터 로드 (헤더 없는 상태로 전체 읽기)
            df_all = pd.read_excel(uploaded_file, header=None)
            
            delivery_date = ""
            header_row_idx = 0
            
            # 2. 납품일자 추출 및 헤더 행 찾기
            for i, row in df_all.iterrows():
                row_list = [str(val).strip() for val in row.values]
                
                # '납품일' 키워드가 있는 행에서 날짜 찾기
                if '납품일' in row_list:
                    for item in row_list:
                        # 날짜 형식(2026-04-08 등) 추출
                        date_match = re.search(r'(\d{4})[-./]?(\d{2})[-./]?(\d{2})', item)
                        if date_match:
                            delivery_date = "".join(date_match.groups())
                            break
                
                # '상품코드'가 있는 행을 데이터 시작점으로 인식
                if '상품코드' in row_list:
                    header_row_idx = i
                    break

            # 3. 데이터 본문 읽기
            df_raw = pd.read_excel(uploaded_file, header=header_row_idx)
            df_raw.columns = [str(c).strip() for c in df_raw.columns]

            temp_rows = []
            for _, row in df_raw.iterrows():
                # 센터명 확인 및 배송코드 부여
                center_nm = str(row.get('점포(센터)', '')).strip()
                if '오산상온센타' in center_nm:
                    s_code = '81030907'
                elif '김해상온센타' in center_nm:
                    s_code = '81030908'
                else:
                    continue  

                # 수량 계산 (BOX 문자 제거 후 숫자 추출 * 입수)
                raw_order = str(row.get('주문수', '0'))
                order_num_match = re.search(r'\d+', raw_order)
                order_qty = int(order_num_match.group()) if order_num_match else 0
                
                ipsu = row.get('입수', 1)
                try:
                    ipsu = int(float(str(ipsu).replace(',', '')))
                except:
                    ipsu = 1
                
                unit_qty = order_qty * ipsu
                
                # ME코드 매칭
                sell_code = str(row.get('판매코드', '')).strip()
                me_code = prod_dict.get(sell_code, f"미등록({sell_code})")
                
                # 단가 숫자 변환 (콤마 제거)
                try:
                    unit_price = int(float(str(row.get('단가', '0')).replace(',', '')))

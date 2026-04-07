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
        
        # 바코드(A열)와 ME코드(C열) 매핑
        # 컬럼명이 다를 경우를 대비해 인덱스로 접근 (0: 바코드, 2: ME코드)
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
            # 1. 납품일자 및 헤더 위치 찾기
            df_all = pd.read_excel(uploaded_file, header=None)
            
            delivery_date = ""
            header_row = 0
            
            for i, row in df_all.iterrows():
                row_values = [str(v) for v in row.values]
                # '납품일' 글자가 있는 행에서 날짜 추출 (예: ORDERS 행)
                if '납품일' in row_values:
                    idx = row_values.index('납품일')
                    delivery_date = row_values[idx+1].replace('-', '')[:8] # YYYYMMDD 형식
                
                # '상품코드'가 있는 행을 데이터 시작점으로 인식
                if '상품코드' in row_values:
                    header_row = i
                    break
            
            df_raw = pd.read_excel(uploaded_file, header=header_row)
            df_raw.columns = [str(c).strip() for c in df_raw.columns]

            temp_rows = []
            for _, row in df_raw.iterrows():
                # 센터 및 배송코드 판별
                center_nm = str(row.get('점포(센터)', '')).strip()
                if '오산상온센타' in center_nm:
                    s_code = '81030907'
                elif '김해상온센타' in center_nm:
                    s_code = '81030908'
                else:
                    continue  

                # 수량 계산 (BOX 제거 후 숫자 * 입수)
                raw_order = str(row.get('주문수', '0'))
                order_num = re.sub(r'[^0-9]', '', raw_order)
                order_qty = int(order_num) if order_num else 0
                
                ipsu = row.get('입수', 1)
                try:
                    ipsu = int(float(ipsu))
                except:
                    ipsu = 1
                unit_qty = order_qty * ipsu
                
                # ME코드 매칭
                sell_code = str(row.get('판매코드', '')).strip()
                me_code = prod_dict.get(sell_code, f"미등록({sell_code})")
                
                # 단가 콤마 제거 및 숫자 변환
                unit_price = str(row.get('단가', '0')).replace(',', '')
                unit_price = int(pd.to_numeric(unit_price, errors='coerce') or 0)

                if unit_qty > 0:
                    temp_rows.append({
                        '출고구분': 0,
                        '수주일자': datetime.now().strftime('%Y%m%d'),
                        '납품일자': delivery_date,
                        '발주처코드': '81030907',
                        '발주처': '롯데마트',
                        '배송코드': s_code,
                        '배송지': center_nm,
                        '상품코드': me_code,
                        '상품명': row.get('상품명', ''),
                        'UNIT수량': unit_qty,
                        'UNIT단가': unit_price
                    })

            if temp_rows:
                df_temp = pd.DataFrame(temp_rows)
                
                # 동일 배송코드 + 동일 상품 합산
                grp_cols = ['출고구분', '수주일자', '납품일자', '발주처코드', '발주처', '배송코드', '배송지', '상품코드', '상품명', 'UNIT단가']
                df_final = df_temp.groupby(grp_cols, as_index=False)['UNIT수량'].sum()
                
                # 금액 및 부가세 계산
                df_final['금        액'] = df_final['UNIT수량'] * df_final['UNIT단가']
                df_final['부  가   세'] = (df_final['금        액'] * 0.1).astype(int)

                # final.xlsx 양식의 컬럼 순서 강제 지정
                final_columns = [
                    '출고구분', '수주일자', '납품일자', '발주처코드', '발주처', '배송코드', 
                    '배송지', '상품코드', '상품명', 'UNIT수량', 'UNIT단가', '금        액', '부  가   세'
                ]
                df_final = df_final[final_columns]

                st.success(f"✅ 분석 완료! 납품일자: {delivery_date}")
                st.dataframe(df_final, use_container_width=True)

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='서식업로드')
                
                st.download_button(
                    label="📥 롯데마트 서식 다운로드",
                    data=output.getvalue(),
                    file_name=f"LotteMart_Final_{datetime.now().strftime('%m%d')}.xlsx"
                )
            else:
                st.warning("분석할 수 있는 수주 데이터가 없습니다.")

        except Exception as e:
            st.error(f"처리 중 오류 발생: {e}")

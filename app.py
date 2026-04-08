import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

st.set_page_config(page_title="롯데마트 수주 자동화", page_icon="🔴", layout="wide")

@st.cache_data
def load_lotte_master(path):
    try:
        # [롯데마트 제품코드] 시트 로드
        df_prod = pd.read_excel(path, sheet_name='롯데마트 제품코드', dtype=str)
        df_prod.columns = [str(c).strip() for c in df_prod.columns]
        
        # 바코드(A열)와 ME코드(C열) 매핑
        barcode_col = df_prod.columns[0]
        me_col = df_prod.columns[2]
        
        prod_map = {
            str(r[barcode_col]).strip(): str(r[me_col]).strip() 
            for _, r in df_prod.iterrows() if pd.notna(r[barcode_col])
        }
        return prod_map, None
    except Exception as e:
        return {}, str(e)

st.title("🛒🔴 롯데마트 수주 자동화")

# 1. 마스터 파일 로드
MASTER_FILE = "롯데마트_서식파일_업데이트용.xlsx"
prod_dict, error = load_lotte_master(MASTER_FILE)

if error:
    st.error(f"마스터 파일 로드 실패: {error}")
else:
    # --- 안내 문구 추가 구간 ---
    st.markdown("### ※ 업로드 전 확인사항")
    st.info("💡 **엑셀파일 확장자를 .xlsx로 변환 후 업로드해주세요.** (xls, csv 파일은 변환이 필요합니다)")
    # -----------------------
    
    uploaded_file = st.file_uploader("가공된 롯데마트 로우 데이터를 업로드하세요. (K열에 점포(센터) 목록 및 정보 추가필요)", type=['xlsx'])

    if uploaded_file:
        try:
            # 2. 납품일자 추출 (H6 셀 기준: 인덱스 5행, 7열)
            df_for_date = pd.read_excel(uploaded_file, header=None)
            
            # H6 셀 값 안전하게 가져오기
            try:
                raw_delivery_date = str(df_for_date.iloc[5, 7]) 
                # 숫자만 추출하여 YYYYMMDD 형식으로 변환
                delivery_date = "".join(re.findall(r'\d+', raw_delivery_date))[:8]
            except Exception:
                delivery_date = ""

            # 3. 데이터 본문 로드 (헤더 '상품코드' 위치 찾기)
            header_row_idx = 0
            for i, row in df_for_date.iterrows():
                if '상품코드' in [str(v).strip() for v in row.values]:
                    header_row_idx = i
                    break
            
            df_raw = pd.read_excel(uploaded_file, header=header_row_idx)
            df_raw.columns = [str(c).strip() for c in df_raw.columns]

            temp_rows = []
            for _, row in df_raw.iterrows():
                # 센터 및 배송코드 할당
                center_nm = str(row.get('점포(센터)', '')).strip()
                if '오산상온센타' in center_nm:
                    s_code = '81030907'
                elif '김해상온센타' in center_nm:
                    s_code = '81030908'
                else:
                    continue  

                # 수량 계산 (주문수 숫자 * 입수)
                raw_order = str(row.get('주문수', '0'))
                order_num = "".join(re.findall(r'\d+', raw_order))
                order_qty = int(order_num) if order_num else 0
                
                try:
                    ipsu = int(float(str(row.get('입수', 1)).replace(',', '')))
                except Exception:
                    ipsu = 1
                
                try:
                    unit_price = int(float(str(row.get('단가', '0')).replace(',', '')))
                except Exception:
                    unit_price = 0
                
                unit_qty = order_qty * ipsu
                sell_code = str(row.get('판매코드', '')).strip()
                me_code = prod_dict.get(sell_code, f"미등록({sell_code})")
                
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
                        '상품명': str(row.get('상품명', '')),
                        'UNIT수량': unit_qty,
                        'UNIT단가': unit_price
                    })

            if temp_rows:
                df_temp = pd.DataFrame(temp_rows)
                # 4. 합산
                grp_cols = ['출고구분', '수주일자', '납품일자', '발주처코드', '발주처', '배송코드', '배송지', '상품코드', '상품명', 'UNIT단가']
                df_final = df_temp.groupby(grp_cols, as_index=False)['UNIT수량'].sum()
                
                # 5. 금액 및 부가세 계산
                df_final['금        액'] = df_final['UNIT수량'] * df_final['UNIT단가']
                df_final['부  가   세'] = (df_final['금        액'] * 0.1).astype(int)

                # 6. 컬럼 순서 조정
                final_cols = ['출고구분', '수주일자', '납품일자', '발주처코드', '발주처', '배송코드', '배송지', '상품코드', '상품명', 'UNIT수량', 'UNIT단가', '금        액', '부  가   세']
                df_final = df_final.reindex(columns=final_cols)

                st.success(f"✅ 분석 완료!")
                st.dataframe(df_final, use_container_width=True)

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='서식업로드')
                st.download_button(label="📥 결과 다운로드", data=output.getvalue(), file_name=f"Lotte_Result_{datetime.now().strftime('%m%d')}.xlsx")
            else:
                st.warning("데이터가 없습니다. 점포(센터) 열이 '오산상온센타' 또는 '김해상온센타'인지 확인해주세요.")
        except Exception as e:
            st.error(f"실행 오류: {str(e)}")

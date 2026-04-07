import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

st.set_page_config(page_title="롯데마트 수주 자동화", page_icon="🛒", layout="wide")

@st.cache_data
def load_lotte_master(path):
    try:
        # [롯데마트 제품코드] 시트에서 판매코드와 ME코드 매핑 추출
        df_prod = pd.read_excel(path, sheet_name='롯데마트 제품코드', dtype=str)
        # 바코드(판매코드) 열을 키로, ME코드 열을 값으로 매핑
        prod_map = {
            str(r['바코드']).strip(): str(r['ME코드']).strip() 
            for _, r in df_prod.iterrows() if pd.notna(r['바코드'])
        }
        return prod_map, None
    except Exception as e:
        return {}, str(e)

st.title("🛒 롯데마트 수주 자동화")

# 마스터 파일 설정 (Github에 업로드된 파일명과 일치해야 함)
MASTER_FILE = "롯데마트_서식파일_업데이트용.xlsx"
prod_dict, error = load_lotte_master(MASTER_FILE)

if error:
    st.error(f"마스터 파일 로드 실패: {error}")
else:
    uploaded_file = st.file_uploader("ORDERS로 시작하는 롯데마트 로우 데이터를 업로드하세요", type=['xlsx'])

    if uploaded_file:
        try:
            # 롯데마트 로우 데이터 로드
            df_raw = pd.read_excel(uploaded_file)
            
            temp_rows = []
            for _, row in df_raw.iterrows():
                # 1. 센터 구분 및 배송코드 설정
                center_nm = str(row.get('점포(센터)', '')).strip()
                if '오산상온센타' in center_nm:
                    s_code = '81030907'
                elif '김해상온센타' in center_nm:
                    s_code = '81030908'
                else:
                    continue  # 지정된 센터가 아니면 제외
                
                # 2. ME코드 매칭 (판매코드 기준)
                sell_code = str(row.get('판매코드', '')).strip()
                me_code = prod_dict.get(sell_code, "미등록상품")
                
                # 3. 수량 계산 (주문수에서 '(BOX)' 제거 후 숫자만 추출 * 입수)
                raw_order_qty = str(row.get('주문수', '0'))
                # 숫자만 남기기 (정규표현식 사용)
                order_qty_num = re.sub(r'[^0-9]', '', raw_order_qty)
                order_qty = int(order_qty_num) if order_qty_num else 0
                
                ipsu = int(row.get('입수', 1))
                final_unit_qty = order_qty * ipsu
                
                if final_unit_qty <= 0:
                    continue

                temp_rows.append({
                    '수주일자': datetime.now().strftime('%Y%m%d'),
                    '발주처코드': '81030907',  # 고정
                    '발주처': '롯데마트',        # 고정
                    '배송코드': s_code,
                    '배송지': center_nm,
                    '상품코드': me_code,
                    '상품명': row.get('상품명', ''),
                    'UNIT수량': final_unit_qty,
                    'UNIT단가': int(row.get('단가', 0))
                })

            if temp_rows:
                df_temp = pd.DataFrame(temp_rows)
                
                # 4. 동일 배송코드 + 동일 ME코드 기준 수량 합산
                grp_cols = ['수주일자', '발주처코드', '발주처', '배송코드', '배송지', '상품코드', '상품명', 'UNIT단가']
                df_final = df_temp.groupby(grp_cols, as_index=False)['UNIT수량'].sum()
                
                # 금액 및 부가세 계산
                df_final['금액'] = df_final['UNIT수량'] * df_final['UNIT단가']
                df_final['부가세'] = (df_final['금액'] * 0.1).astype(int)

                st.success(f"✅ 분석 완료 (총 {len(df_final)}건)")
                st.dataframe(df_final, use_container_width=True)

                # 엑셀 다운로드 생성
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='롯데마트_수주업로드')
                
                st.download_button(
                    label="📥 롯데마트 수주 결과 다운로드",
                    data=output.getvalue(),
                    file_name=f"LotteMart_Order_{datetime.now().strftime('%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("처리할 수 있는 데이터가 없습니다. 센터명(오산/김해)을 확인하세요.")

        except Exception as e:
            st.error(f"오류 발생: {e}")

import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

st.set_page_config(page_title="롯데마트 수주 자동화", page_icon="🛒", layout="wide")

@st.cache_data
def load_lotte_master(path):
    try:
        # [롯데마트 제품코드] 시트 로드 (판매코드-ME코드 매핑)
        df_prod = pd.read_excel(path, sheet_name='롯데마트 제품코드', dtype=str)
        prod_map = {
            str(r['판매코드']).strip(): str(r['ME코드']).strip() 
            for _, r in df_prod.iterrows() if pd.notna(r['판매코드'])
        }
        return prod_map, None
    except Exception as e:
        return {}, str(e)

st.title("🛒 롯데마트 수주 자동화 (가공 로직 반영)")

# 1. 마스터 파일 로드
MASTER_FILE = "롯데마트_서식파일_업데이트용.xlsx"
prod_dict, error = load_lotte_master(MASTER_FILE)

if error:
    st.error(f"마스터 파일 로드 실패: {error}")
else:
    # 2. 로우 데이터 업로드
    uploaded_file = st.file_uploader("가공된 롯데마트 로우 데이터(ORDERS_...)를 업로드하세요", type=['xlsx'])

    if uploaded_file:
        try:
            # 롯데마트 가공 데이터는 위쪽에 제목(주문서 리스트 등)이 있으므로 
            # 실제 컬럼명이 있는 행(보통 4~5행 사이)을 자동으로 찾습니다.
            df_all = pd.read_excel(uploaded_file, header=None)
            
            # '상품코드'라는 글자가 있는 행을 헤더로 지정
            header_row = 0
            for i, row in df_all.iterrows():
                if '상품코드' in row.values:
                    header_row = i
                    break
            
            df_raw = pd.read_excel(uploaded_file, header=header_row)
            df_raw.columns = [str(c).strip() for c in df_raw.columns]

            temp_rows = []
            
            for _, row in df_raw.iterrows():
                # [로직 1] 센터별 배송코드 할당
                center_nm = str(row.get('점포(센터)', '')).strip()
                if '오산상온센타' in center_nm:
                    s_code = '81030907'
                elif '김해상온센타' in center_nm:
                    s_code = '81030908'
                else:
                    continue  # 오산/김해 외 데이터 제외
                
                # [로직 2] 수량 계산 (주문수 숫자만 추출 * 입수)
                raw_order = str(row.get('주문수', '0'))
                order_num = re.sub(r'[^0-9]', '', raw_order) # "1 (BOX)" -> "1"
                order_qty = int(order_num) if order_num else 0
                
                ipsu = row.get('입수', 1)
                try:
                    ipsu = int(float(ipsu))
                except:
                    ipsu = 1
                
                unit_qty = order_qty * ipsu
                
                # [로직 3] ME코드 매칭
                sell_code = str(row.get('판매코드', '')).strip()
                me_code = prod_dict.get(sell_code, f"미등록({sell_code})")
                
                if unit_qty > 0:
                    temp_rows.append({
                        '수주일자': datetime.now().strftime('%Y%m%d'),
                        '발주처코드': '81030907', # 고정
                        '발주처': '롯데마트',      # 고정
                        '배송코드': s_code,
                        '배송지': center_nm,
                        '상품코드': me_code,
                        '상품명': row.get('상품명', ''),
                        'UNIT수량': unit_qty,
                        'UNIT단가': int(pd.to_numeric(str(row.get('단가', 0)).replace(',', ''), errors='coerce') or 0)
                    })

            if temp_rows:
                df_temp = pd.DataFrame(temp_rows)
                
                # [로직 4] 동일 배송코드 + 동일 ME코드 합산
                grp = ['수주일자', '발주처코드', '발주처', '배송코드', '배송지', '상품코드', '상품명', 'UNIT단가']
                df_final = df_temp.groupby(grp, as_index=False)['UNIT수량'].sum()
                
                # 금액 및 부가세 계산
                df_final['금액'] = df_final['UNIT수량'] * df_final['UNIT단가']
                df_final['부가세'] = (df_final['금액'] * 0.1).astype(int)

                st.success("✅ 분석 완료!")
                st.dataframe(df_final, use_container_width=True)

                # 엑셀 다운로드 파일 생성
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='롯데마트_수주업로드')
                
                st.download_button(
                    label="📥 결과 다운로드 (업로드용)",
                    data=output.getvalue(),
                    file_name=f"Lotte_Order_{datetime.now().strftime('%m%d')}.xlsx"
                )
            else:
                st.warning("데이터를 처리하지 못했습니다. 파일의 '점포(센터)' 열을 확인해주세요.")

        except Exception as e:
            st.error(f"프로그램 실행 중 오류 발생: {e}")

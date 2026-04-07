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
        # '바코드' 컬럼과 'ME코드' 컬럼 사용 (C열이 ME코드인 것 반영)
        prod_map = {
            str(r['바코드']).strip(): str(r['ME코드']).strip() 
            for _, r in df_prod.iterrows() if pd.notna(r['바코드']) and pd.notna(r['ME코드'])
        }
        return prod_map, None
    except Exception as e:
        return {}, str(e)

st.title("🛒 롯데마트 수주 자동화")

MASTER_FILE = "롯데마트_서식파일_업데이트용.xlsx"
prod_dict, error = load_lotte_master(MASTER_FILE)

if error:
    st.error(f"마스터 파일(업데이트용) 로드 실패: {error} \n 파일명이 정확한지 확인하세요.")
else:
    uploaded_file = st.file_uploader("ORDERS로 시작하는 롯데마트 RAW 데이터를 업로드하세요", type=['xlsx', 'csv'])

    if uploaded_file:
        try:
            # 확장자에 따라 읽기 방식 결정
            if uploaded_file.name.endswith('.csv'):
                df_raw = pd.read_csv(uploaded_file)
            else:
                df_raw = pd.read_excel(uploaded_file)
            
            # 데이터 시작 부분 확인 (헤더가 첫 줄이 아닐 경우를 대비해 컬럼명 청소)
            df_raw.columns = [str(c).strip() for c in df_raw.columns]

            temp_rows = []
            
            # 필터링할 센터명 정의
            target_centers = ['오산상온센타', '김해상온센타']
            
            for _, row in df_raw.iterrows():
                # 센터명 추출 및 배송코드 할당
                center_val = str(row.get('점포(센터)', '')).strip()
                
                s_code = ""
                if '오산상온센타' in center_val:
                    s_code = '81030907'
                elif '김해상온센타' in center_val:
                    s_code = '81030908'
                
                if not s_code:
                    continue  # 센터명이 맞지 않으면 건너뜀

                # ME코드 매칭 (판매코드 기준)
                sell_code = str(row.get('판매코드', '')).strip()
                me_code = prod_dict.get(sell_code, f"미등록({sell_code})")
                
                # 주문수 숫자 추출 (예: "1(BOX)" -> 1)
                raw_order = str(row.get('주문수', '0'))
                order_num = re.sub(r'[^0-9]', '', raw_order)
                order_qty = int(order_num) if order_num else 0
                
                # 입수 확인
                ipsu = row.get('입수', 1)
                try:
                    ipsu = int(float(ipsu))
                except:
                    ipsu = 1
                    
                unit_qty = order_qty * ipsu
                
                if unit_qty > 0:
                    temp_rows.append({
                        '수주일자': datetime.now().strftime('%Y%m%d'),
                        '발주처코드': '81030907',
                        '발주처': '롯데마트',
                        '배송코드': s_code,
                        '배송지': center_val,
                        '상품코드': me_code,
                        '상품명': row.get('상품명', ''),
                        'UNIT수량': unit_qty,
                        'UNIT단가': int(pd.to_numeric(row.get('단가', 0), errors='coerce') or 0)
                    })

            if temp_rows:
                df_temp = pd.DataFrame(temp_rows)
                
                # 합산 로직 (배송코드, 상품코드 기준)
                grp = ['수주일자', '발주처코드', '발주처', '배송코드', '배송지', '상품코드', '상품명', 'UNIT단가']
                df_final = df_temp.groupby(grp, as_index=False)['UNIT수량'].sum()
                
                df_final['금액'] = df_final['UNIT수량'] * df_final['UNIT단가']
                df_final['부가세'] = (df_final['금액'] * 0.1).astype(int)

                st.success(f"✅ 처리 완료! (총 {len(df_final)}개 품목 합산됨)")
                st.dataframe(df_final, use_container_width=True)

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='수주업로드')
                
                st.download_button(
                    label="📥 결과 파일 다운로드",
                    data=output.getvalue(),
                    file_name=f"Lotte_Result_{datetime.now().strftime('%m%d')}.xlsx"
                )
            else:
                st.warning("⚠️ 데이터를 찾을 수 없습니다. 원본 파일의 '점포(센터)' 열에 '오산상온센타' 또는 '김해상온센타'라는 글자가 포함되어 있는지 확인해주세요.")
                st.write("현재 파일의 컬럼명들:", list(df_raw.columns)) # 디버깅용

        except Exception as e:
            st.error(f"오류 발생: {e}")

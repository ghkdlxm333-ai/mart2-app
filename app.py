import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

st.set_page_config(page_title="롯데마트 수주 자동화", page_icon="🔴", layout="wide")

# 💡 센터별 고정 발주/배송코드 매핑
CENTER_CODE_MAP = {
    '오산센터': '81030907',
    '김해센터': '81030908'
}

# 💡 센터명 정제 함수
def clean_center_name(name):
    name = str(name).strip()
    # '상온센타', '상온센터', '센타'를 모두 '센터'로 통일
    name = re.sub(r'상온센타|상온센터|센타', '센터', name)
    # 중복 정제 처리 (예: 센터센터 -> 센터)
    return name.replace('센터센터', '센터')

@st.cache_data
def load_lotte_master(path):
    try:
        df_prod = pd.read_excel(path, sheet_name='롯데마트 제품코드', dtype=str)
        df_prod.columns = [str(c).strip() for c in df_prod.columns]
        barcode_col = df_prod.columns[0]
        me_col = df_prod.columns[2]
        
        prod_map = {}
        for _, r in df_prod.iterrows():
            if pd.notna(r[barcode_col]):
                b_code = str(r[barcode_col]).strip().split('.')[0]
                prod_map[b_code] = str(r[me_col]).strip()
        return prod_map, None
    except Exception as e:
        return {}, str(e)

st.title("🛒🔴 롯데마트 수주 자동화")

MASTER_FILE = "롯데마트_서식파일_업데이트용.xlsx"
prod_dict, error = load_lotte_master(MASTER_FILE)

if error:
    st.error(f"마스터 파일 로드 실패: {error}")
else:
    st.markdown("### ※ 업로드 전 확인사항")
    st.info("💡 **엑셀파일 확장자를 .xlsx로 변환 후 업로드해주세요.**")
    
    uploaded_file = st.file_uploader("가공된 롯데마트 로우 데이터를 업로드하세요.", type=['xlsx'])

    if uploaded_file:
        try:
            # 전체 데이터를 헤더 없이 로드 (위치 파악용)
            df_full = pd.read_excel(uploaded_file, header=None)
            
            # 1. 납품일자 추출 (H6 셀 -> 인덱스 5행, 7열)
            try:
                raw_delivery_date = str(df_full.iloc[5, 7]) 
                delivery_date = "".join(re.findall(r'\d+', raw_delivery_date))[:8]
            except:
                delivery_date = ""

            # 2. 센터정보 추출 (F6 셀 -> 인덱스 5행, 5열)
            # 파일 구조상 6행의 '점포(센터)' 열에 해당하는 위치에서 센터명을 가져옵니다.
            try:
                raw_center = str(df_full.iloc[5, 5]).strip()
                cleaned_center = clean_center_name(raw_center)
                s_code = CENTER_CODE_MAP.get(cleaned_center)
            except:
                raw_center = ""
                s_code = None

            # 3. 데이터 본문 시작점 찾기 (헤더 '상품코드' 위치)
            header_row_idx = 0
            for i, row in df_full.iterrows():
                if '상품코드' in [str(v).strip() for v in row.values]:
                    header_row_idx = i
                    break
            
            # 실제 데이터 로드
            df_raw = pd.read_excel(uploaded_file, header=header_row_idx)
            df_raw.columns = [str(c).strip() for c in df_raw.columns]

            if not s_code:
                st.error(f"❌ 센터 정보를 찾을 수 없습니다. (추출된 값: {raw_center})")
                st.stop()

            temp_rows = []
            for _, row in df_raw.iterrows():
                # '합계' 행 등 불필요한 행 제외
                if pd.isna(row.get('상품코드')) or '합계' in str(row.get('상품코드')):
                    continue

                # 수량 계산
                raw_order = str(row.get('주문수', '0'))
                order_num = "".join(re.findall(r'\d+', raw_order))
                order_qty = int(order_num) if order_num else 0
                
                try:
                    ipsu = int(float(str(row.get('입수', 1)).replace(',', '')))
                except:
                    ipsu = 1
                
                try:
                    unit_price = int(float(str(row.get('단가', '0')).replace(',', '')))
                except:
                    unit_price = 0
                
                unit_qty = order_qty * ipsu
                
                # 바코드 소수점 제거 후 ME코드 매칭
                sell_code = str(row.get('판매코드', '')).strip().split('.')[0]
                me_code = prod_dict.get(sell_code, f"미등록({sell_code})")
                
                if unit_qty > 0:
                    temp_rows.append({
                        '출고구분': 0,
                        '수주일자': datetime.now().strftime('%Y%m%d'),
                        '납품일자': delivery_date,
                        '발주처코드': '81030907',
                        '발주처': '롯데마트',
                        '배송코드': s_code,
                        '배송지': raw_center,
                        '상품코드': me_code,
                        '상품명': str(row.get('상품명', '')),
                        'UNIT수량': unit_qty,
                        'UNIT단가': unit_price
                    })

            if temp_rows:
                df_temp = pd.DataFrame(temp_rows)
                grp_cols = ['출고구분', '수주일자', '납품일자', '발주처코드', '발주처', '배송코드', '배송지', '상품코드', '상품명', 'UNIT단가']
                df_final = df_temp.groupby(grp_cols, as_index=False)['UNIT수량'].sum()
                
                df_final['금        액'] = df_final['UNIT수량'] * df_final['UNIT단가']
                df_final['부  가   세'] = (df_final['금        액'] * 0.1).astype(int)

                final_cols = ['출고구분', '수주일자', '납품일자', '발주처코드', '발주처', '배송코드', '배송지', '상품코드', '상품명', 'UNIT수량', 'UNIT단가', '금        액', '부  가   세']
                df_final = df_final.reindex(columns=final_cols)

                st.success(f"✅ 분석 완료! (센터: {raw_center}, 납품일: {delivery_date})")
                st.dataframe(df_final, use_container_width=True)

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='서식업로드')
                st.download_button(label="📥 결과 다운로드", data=output.getvalue(), file_name=f"Lotte_Result_{datetime.now().strftime('%m%d')}.xlsx")
            else:
                st.warning("처리할 데이터가 없습니다.")
        except Exception as e:
            st.error(f"실행 오류: {str(e)}")

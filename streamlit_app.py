import streamlit as st
import pandas as pd
import os
import json
import base64

# 因子マッピング
BLUE_FACTORS = [
    {'id': 1,  'name': 'スピード'},
    {'id': 2,  'name': 'スタミナ'},
    {'id': 3,  'name': 'パワー'},
    {'id': 4,  'name': '根性'},
    {'id': 5,  'name': '賢さ'},
    {'id': -1, 'name': '合計'},
]
RED_FACTORS = [
    {'id': 11, 'name': '芝'},
    {'id': 12, 'name': 'ダート'},
    {'id': 31, 'name': '短距離'},
    {'id': 32, 'name': 'マイル'},
    {'id': 33, 'name': '中距離'},
    {'id': 34, 'name': '長距離'},
    {'id': 21, 'name': '逃げ'},
    {'id': 22, 'name': '先行'},
    {'id': 23, 'name': '差し'},
    {'id': 24, 'name': '追込'},
]

# --------------------
# ユーティリティ関数
# --------------------

def trim_matrix(df_raw, anchor: str):
    hdr_idx = df_raw.eq(anchor).any(axis=1).idxmax()
    raw_hdr = df_raw.iloc[hdr_idx].astype(str)
    start_col = raw_hdr[raw_hdr == anchor].index[0] + 1
    end_col = raw_hdr[raw_hdr == '合計'].index[0]
    last_row = df_raw.iloc[:,1].notna()[::-1].idxmax()
    sub = df_raw.iloc[hdr_idx+1:last_row+1, start_col:end_col].copy()
    names = df_raw.iloc[hdr_idx+1:last_row+1,1].astype(str).tolist()
    sub.columns = raw_hdr[start_col:end_col]
    sub.index = names
    return sub.reindex(index=names, columns=names, fill_value=0).values.astype(int), names

@st.cache_data
def load_preferences():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pref_path = os.path.join(base_dir, 'preferences.json')
    if os.path.isfile(pref_path):
        with open(pref_path, 'r', encoding='utf-8') as f:
            pref = json.load(f)
    else:
        pref = {
            'spec_folder': os.path.join(base_dir, '3gen'),
            'gen2_path':   os.path.join(base_dir, '2gen.csv'),
            'index_path':  os.path.join(base_dir, 'uma_index.csv'),
            'g1_win_count': 0,
            'search_count': 100,
            'white_total': 0
        }
        with open(pref_path, 'w', encoding='utf-8') as f:
            json.dump(pref, f, ensure_ascii=False, indent=2)
    return pref

@st.cache_data
def load_2gen(path: str):
    df = pd.read_csv(path, header=None, encoding='cp932')
    arr, names = trim_matrix(df, '列クリックでソート→')
    return arr, names

@st.cache_data
def load_index(path: str):
    df = pd.read_csv(path, header=0, encoding='cp932')
    sub = df[['name','id','deploy']].dropna(subset=['name','id','deploy']).copy()
    sub['id'] = sub['id'].astype(int)
    sub['deploy'] = sub['deploy'].astype(int)
    id_deploy = dict(zip(sub['id'], sub['deploy']))
    name_to_ids = sub.groupby('name')['id'].apply(list).to_dict()
    char_deploy = {name: int(any(id_deploy[i]==1 for i in ids)) for name, ids in name_to_ids.items()}
    return name_to_ids, id_deploy, char_deploy

# フィルタ処理を実行

def run_filter(child, parent1, parent2, own1, own2,
               anc11, anc12, anc21, anc22,
               x_pct, y_pct, spec_folder,
               gen2_arr, gen2_chars):
    # 子のインデックス取得
    cid = gen2_chars.index(child)
    # spec CSV 読み込み
    sf = os.path.join(spec_folder, f"{child}.csv")
    df = pd.read_csv(sf, header=None, encoding='cp932')
    spec_arr, _ = trim_matrix(df, '親相性')
    # 親選択
    p1_sel = parent1 in gen2_chars
    p2_sel = parent2 in gen2_chars
    p1_idx = gen2_chars.index(parent1) if p1_sel else None
    p2_idx = gen2_chars.index(parent2) if p2_sel else None
    # 手動祖先
    manual1 = {gen2_chars.index(v) for v in (anc11, anc12) if v in gen2_chars and not own1}
    manual2 = {gen2_chars.index(v) for v in (anc21, anc22) if v in gen2_chars and not own2}
    N = len(gen2_chars)
    # Phase1: ペア作成
    pairs = []
    if p1_sel and p2_sel:
        r = (gen2_arr[cid,p1_idx] + gen2_arr[cid,p2_idx] + gen2_arr[p1_idx,p2_idx])
        pairs = [(r, p1_idx, p2_idx)]
    elif p1_sel:
        for k in range(N):
            if k == p1_idx: continue
            r = (gen2_arr[cid,p1_idx] + gen2_arr[cid,k] + gen2_arr[p1_idx,k])
            pairs.append((r, p1_idx, k))
    elif p2_sel:
        for k in range(N):
            if k == p2_idx: continue
            r = (gen2_arr[cid,k] + gen2_arr[cid,p2_idx] + gen2_arr[k,p2_idx])
            pairs.append((r, k, p2_idx))
    else:
        for i in range(N):
            for j in range(i+1, N):
                r = (gen2_arr[cid,i] + gen2_arr[cid,j] + gen2_arr[i,j])
                pairs.append((r, i, j))
    pairs.sort(reverse=True, key=lambda x: x[0])
    per_pass = max(1, int(len(pairs) * x_pct / 100))
    # Phase2: ブラックリスト
    target_bl = int(N * y_pct / 100)
    bottom = (y_pct / x_pct) if x_pct > 0 else 0
    cnt_pp = max(1, int(N * bottom / 100))
    max_pass = ((target_bl + cnt_pp - 1) // cnt_pp) if target_bl > 0 else 1
    blacklist = set()
    pass_no = 0
    while len(blacklist) < target_bl and pass_no < max_pass:
        pass_no += 1
        processed = 0
        for r, i, j in pairs:
            if processed >= per_pass or len(blacklist) >= target_bl:
                break
            processed += 1
            # 親1側
            if not own1:
                cand = [k for k in range(N) if gen2_chars[k] not in blacklist and k not in (cid, i, j)]
                t1 = sorted((min(gen2_arr[cid,i], gen2_arr[cid,k], spec_arr[i,k]), k) for k in cand)
                for _, k2 in t1[:cnt_pp]:
                    if k2 not in manual1 and gen2_chars[k2] not in blacklist:
                        blacklist.add(gen2_chars[k2])
            # 親2側
            if not own2:
                cand = [k for k in range(N) if gen2_chars[k] not in blacklist and k not in (cid, i, j)]
                t2 = sorted((min(gen2_arr[cid,j], gen2_arr[cid,k], spec_arr[j,k]), k) for k in cand)
                for _, k2 in t2[:cnt_pp]:
                    if k2 not in manual2 and gen2_chars[k2] not in blacklist:
                        blacklist.add(gen2_chars[k2])
    # Phase3: ホワイトリスト
    single = {c: 0 for c in gen2_chars if c not in blacklist}
    for r, i, j in pairs:
        ci, cj = gen2_chars[i], gen2_chars[j]
        if ci in single: single[ci] += r
        if cj in single: single[cj] += r
    if p1_sel and p2_sel:
        if own1 and not own2:
            whitelist = [parent2]
        elif own2 and not own1:
            whitelist = [parent1]
        else:
            whitelist = [parent1, parent2]
    else:
        cnt_w = max(1, int(len(gen2_chars) * x_pct / 100))
        whitelist = [c for c, _ in sorted(single.items(), key=lambda x: x[1], reverse=True)[:cnt_w]]
        # 所有済み親の除外
        if p1_sel and not p2_sel and own1:
            whitelist = [c for c in whitelist if c != parent1]
        if p2_sel and not p1_sel and own2:
            whitelist = [c for c in whitelist if c != parent2]
    return whitelist, list(blacklist)

# URL生成

def generate_url(whitelist, blacklist,
                  name_to_ids, id_deploy,
                  g1_win_count, white_total, search_count, white_type,
                  blue_params, red_params):
    partner_ids = []
    exclude_ids = []
    for n in whitelist:
        for cid in name_to_ids.get(n, []):
            if id_deploy.get(cid, 0) == 1:
                partner_ids.append(cid)
    for n in blacklist:
        for cid in name_to_ids.get(n, []):
            if id_deploy.get(cid, 0) == 1:
                exclude_ids.append(cid)
    info = {
        'partner_card_ids': partner_ids,
        'exclude_type': 0,
        'exclude_card_ids': exclude_ids,
        'support_card': {'id': 0, 'limit_break': 4},
        'blue_factors': blue_params,
        'red_factors': red_params,
        'green_factors': [],
        'common_factors': [],
        'race_factors': [],
        'scenario_factors': [],
        'other_factors': [],
        'race': {'win_count': 0, 'g1_win_count': g1_win_count},
        'white_factor': {'num': white_total, 'search_type': white_type},
        'search_count': search_count
    }
    js = json.dumps(info, ensure_ascii=False)
    b64 = base64.urlsafe_b64encode(js.encode('utf-8')).decode('utf-8')
    return f"https://uma.pure-db.com/#/search?searchInfo={b64}"  

# --------------------
# Streamlit アプリ本体
# --------------------

def main():
    st.set_page_config(page_title="ウマ娘フレンド検索アシスト", layout="wide")
    st.title("ウマ娘フレンド検索アシストツール v1.0.0")

    # 設定読み込み
    pref = load_preferences()
    gen2_arr, gen2_chars = load_2gen(pref['gen2_path'])
    name_to_ids, id_deploy, char_deploy = load_index(pref['index_path'])
    spec_folder = pref['spec_folder']

    # レイアウト: 左右2カラム
    left_col, right_col = st.columns([3, 1])

    with left_col:
        x_pct = st.slider("上位 x% 親ペア (X%)", 0.05, 100.0, pref.get('x_pct', 10.0), step=0.05, format="%.2f")
        y_pct = st.slider("下位 y% 除外 (Y%)", 0.05, 100.0, pref.get('y_pct', 20.0), step=0.05, format="%.2f")
        child = st.selectbox("子", ["(未選択)"] + gen2_chars)
        st.write("")
        parent1 = st.selectbox("親1", ["(未選択)"] + gen2_chars)
        own1 = st.checkbox("Owned 親1")
        anc11 = st.selectbox("祖1-1", ["(未選択)"] + gen2_chars)
        anc12 = st.selectbox("祖1-2", ["(未選択)"] + gen2_chars)
        st.write("")
        parent2 = st.selectbox("親2", ["(未選択)"] + gen2_chars)
        own2 = st.checkbox("Owned 親2")
        anc21 = st.selectbox("祖2-1", ["(未選択)"] + gen2_chars)
        anc22 = st.selectbox("祖2-2", ["(未選択)"] + gen2_chars)

        if st.button("Filter"):
            with st.spinner("フィルタ中…"):
                whitelist, blacklist = run_filter(
                    child, parent1, parent2, own1, own2,
                    anc11, anc12, anc21, anc22,
                    x_pct, y_pct, spec_folder,
                    gen2_arr, gen2_chars
                )
            # 結果表示
            url = generate_url(
                whitelist, blacklist,
                name_to_ids, id_deploy,
                g1, white_total, search_count, white_type,
                blue_params, red_params
            )            
            st.markdown(f"[検索結果URLを開く]({url})")
            wh_col, bl_col = st.columns(2)
            with wh_col:
                st.subheader("Whitelist")
                for n in whitelist:
                    st.write(n)
            with bl_col:
                st.subheader("Blacklist")
                for n in blacklist:
                    st.write(n)
            # URL生成用パラメータ収集
            blue_params = []
            for i in range(4):
                # Streamlitではキー管理のためsession_stateを用いて入力を保持
                cb = st.session_state.get(f"blue_cb_{i}", None)
                num = st.session_state.get(f"blue_num_{i}", 1)
                stype = st.session_state.get(f"blue_type_{i}", 0)
                if cb and cb != '(未選択)':
                    for f in BLUE_FACTORS:
                        if f['name'] == cb:
                            blue_params.append({'group_id': f['id'], 'num': num, 'search_type': stype, 'enabled': True})
            red_params = []
            for i in range(3):
                cb = st.session_state.get(f"red_cb_{i}", None)
                num = st.session_state.get(f"red_num_{i}", 1)
                stype = st.session_state.get(f"red_type_{i}", 0)
                if cb and cb != '(未選択)':
                    for f in RED_FACTORS:
                        if f['name'] == cb:
                            red_params.append({'group_id': f['id'], 'num': num, 'search_type': stype, 'enabled': True})
            g1 = st.session_state.get('g1_win_count', pref['g1_win_count'])
            search_count = st.session_state.get('search_count', pref['search_count'])
            white_total = st.session_state.get('white_total', pref['white_total'])
            white_type = st.session_state.get('white_type', 0)

    with right_col:
        st.subheader("数値設定")
        st.number_input("G1勝利数", min_value=0, step=1, key='g1_win_count', value=pref['g1_win_count'])
        st.number_input("検索数", min_value=1, step=1, key='search_count', value=pref['search_count'])
        st.number_input("白因子合計", min_value=0, step=1, key='white_total', value=pref['white_total'])
        st.selectbox("白因子種類", ['全て', '代表', '継承元'], key='white_type')

        st.subheader("青因子")
        for i in range(4):
            cols = st.columns([2,1,1])
            with cols[0]:
                st.selectbox("", ['(未選択)'] + [f['name'] for f in BLUE_FACTORS], key=f'blue_cb_{i}')
            with cols[1]:
                st.number_input("", min_value=1, max_value=9, step=1, key=f'blue_num_{i}')
            with cols[2]:
                st.selectbox("", ['全て', '代表', '継承元'], key=f'blue_type_{i}')

        st.subheader("赤因子")
        for i in range(3):
            cols = st.columns([2,1,1])
            with cols[0]:
                st.selectbox("", ['(未選択)'] + [f['name'] for f in RED_FACTORS], key=f'red_cb_{i}')
            with cols[1]:
                st.number_input("", min_value=1, max_value=9, step=1, key=f'red_num_{i}')
            with cols[2]:
                st.selectbox("", ['全て', '代表', '継承元'], key=f'red_type_{i}')

if __name__ == '__main__':
    main()

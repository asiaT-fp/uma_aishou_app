#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import pandas as pd

def main():
    # 現在のフォルダ内のCSVファイルを取得
    files = [f for f in os.listdir('.') if f.lower().endswith('.csv')]
    ok = []
    ng = []

    for file in files:
        base = os.path.splitext(file)[0]
        try:
            # ファイル読み込み（エンコーディング自動判別）
            df_raw = None
            for enc in ['utf-8', 'cp932', 'shift_jis']:
                try:
                    df_raw = pd.read_csv(file, header=None, encoding=enc)
                    break
                except Exception:
                    continue
            if df_raw is None:
                ng.append((file, '読み込み失敗'))
                continue

            # '親相性'ヘッダ行を検出
            hdr_bool = df_raw.eq('親相性').any(axis=1)
            if not hdr_bool.any():
                ng.append((file, '親相性ヘッダなし'))
                continue
            hdr_idx = hdr_bool.idxmax()
            raw_hdr = df_raw.iloc[hdr_idx].astype(str).tolist()

            # ヘッダから列インデックスを取得
            try:
                parent_col_idx = raw_hdr.index('親相性')
                name_col_idx = raw_hdr.index('名前')
            except ValueError:
                ng.append((file, '親相性または名前列見つからず'))
                continue

            # データ行を走査してファイル名と一致する行を検索
            data = df_raw.iloc[hdr_idx+1:]
            found = False
            for _, row in data.iterrows():
                if str(row[name_col_idx]).strip() == base:
                    found = True
                    try:
                        val = float(row[parent_col_idx])
                    except Exception:
                        ng.append((file, f'値数値変換失敗:{row[parent_col_idx]}'))
                        break
                    if val == 0:
                        ok.append(file)
                    else:
                        ng.append((file, f'親相性={val}'))
                    break
            if not found:
                ng.append((file, '該当キャラ行なし'))

        except Exception as e:
            ng.append((file, f'例外:{e}'))

    # 結果を出力
    print('問題なしファイル:')
    for f in ok:
        print(f)
    print('\n問題ありファイル:')
    for f, reason in ng:
        print(f, reason)

if __name__ == '__main__':
    main()

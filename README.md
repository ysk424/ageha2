# 揚羽 (Ageha) 0.3.1

Blender 5.2 以降 / Windows x64 向けの、髪を用意するところからシミュレーションまでを一つにまとめた個人用拡張です。表示名と 3D ビューのタブ名は **揚羽** です。

## 方針

- 植毛、Z列植え、前髪カットは `ageha` のワークフローを継承
- シミュレーターは **Kami4 Hair Solver 固定**
- CPRS、XPBD、およびソルバー選択 UI は収録しない
- `kami4_solver/` は `kami4-hair-solver/extension/` の無改変コピー
- Kami4 の11計算パラメータを「揚羽」パネルですべて表示・編集
- 小数パラメータは文字列で保持し、Blenderの単精度丸めによる結果変化を防止
- ベイク完了時にキャッシュ再生を自動で有効化し、タイムラインへ結果を反映
- 入力変更時は過去のキャッシュを削除せず、次回ベイクを新しいキャッシュへ切り替える

## 使い方

1. 3D ビューの **揚羽** タブを開く。
2. 入力する髪とボディを指定する。服などは「服・追加コライダー」のコレクションへ入れる。
3. 必要なら「ヘッドマスク作成」から髪を植える。
4. 「セットアップ検証」を実行する。
5. 開始・終了フレーム、固定する根元点数、Kami4計算パラメータを確認する。
6. 「全フレーム計算」を実行する。完了後はキャッシュ再生が自動で有効になる。

Kami4 は元の髪を変更せず、`Kami4_髪_計算結果` を作ります。キャッシュ先を空欄にすると、Blend ファイル横（未保存ならユーザーホーム）へ日時付きの新しい `kami4_cache` を作ります。

## 構成

```text
ageha2/
  __init__.py             # 揚羽ワークフローと統合登録
  ui.py                   # 「揚羽」一体型パネル
  _mask_plant.py          # ageha 由来の植毛処理
  _groom_ops.py           # ageha 由来の前髪処理
  kami4_solver/           # Kami4 拡張ランタイム（無改変）
  vendor/kami4-hair-solver/ # Kami4 元リポジトリの追跡ファイル（無改変）
```

## 検証

```powershell
python -m unittest tests.test_vendor_integrity
python -m compileall -q .
```

## ライセンス

統合物は GPL-3.0-or-later です。揚羽由来部分の元ライセンスは `LICENSE-AGEHA-MIT`、Kami4 のライセンスは `LICENSE` と `kami4_solver/LICENSE` に収録しています。

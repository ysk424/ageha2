# 髪4 髪物理計算機

ブレンダー5.2、ウィンドウズ64ビット版、クーダ向けの髪物理計算機です。現在の画面名は **エーシーズ**。線形曲げ・長さ補正・速度力積を基本とし、身体メッシュの階層境界箱接触と、残った接触を修復する局所順運動学を組み合わせています。

**2026-09-17 作業終了・再開時は [引き継ぎメモ](docs/RESUME_JA.md) を先に確認してください。** 87フレームの画面を別名保存し、電源断用の一式を `session-end-20260917` に記録しています。

**現在の採用・復帰点は `baseline-local-fk-adopted-20260917` です。** 根元2点固定、曲げ剛性5×10⁻⁷、最小計算長30センチメートル、局所順運動学の第2版。採用済み200フレームは106.94秒、平均は1フレーム当たり0.535秒です（計算とキャッシュ保存のみで、描画を除く）。実髪でのユーザー採用と、原仕様の全受入条件の合格は区別しています。

- [日本語の現行設計書](docs/ACES_DESIGN_JA.md)：原仕様との差分、処理図、数式、画像処理装置配置、設定、検証範囲。
- [完全な採用パラメータ](presets/local-fk-contact-20260917.json)：材料の既定ジェイソンだけでは採用状態を再現できません。
- [実験・採用記録](docs/experiments/local-fk-contact-20260917/README.md)と[復帰手順・全保存点](docs/CHECKPOINTS.md)。
- [採用公開保存点](https://github.com/ysk424/kami4-hair-solver/releases/tag/baseline-local-fk-adopted-20260917)：対応するソース・拡張・シーン・200フレーム分のキャッシュの保存点。

採用シーンは `outputs/local_fk_v2_200/kami4_aces_local_fk_v2.blend`、拡張は `dist/kami4_bvh_hair_solver-0.3.0-windows-x64.zip`。日本語Nパネル「エーシーズ」で保存済みキャッシュを再生できます。元の入力ブレンドファイルは上書きしていません。再現計算は[設計書の手順](docs/ACES_DESIGN_JA.md#132-再計算する場合のコマンド)を使用し、既存の結果を上書きしないでください。

## 初版0.1.0の記録

以下は初版の操作・検証資料です。現在の拡張名、設定、保存先とは異なります。旧復帰点 `baseline-root2-200f-20260917` も保持しています（根元2点固定、200フレーム80.80秒、平均は1フレーム当たり0.404秒）。初回検証には根元1点固定の結果も含みます。

**初版の一括受入判定は不合格でした。** 3試験と200フレームの計算・再生は動作しましたが、元アニメーションの移動上限、一部のメッシュ接触、および厳密な微小残差の中央処理装置／画像処理装置相対比較に未達がありました。[初版の実測結果](docs/RESULTS_JA.md)を参照してください。

今回の入力は、ポート9876で開いていた `kami-hair-solver` と同じ **「カーブ」6,757本・74,327点**、**「身体メッシュ」225,184頂点・449,472三角形** です。元の `.blend` は上書きしていません。新しいシーンは `outputs/kami4_current_scene.blend`、拡張圧縮書庫は `dist/kami4_hair_solver-0.1.0-windows-x64.zip` です。

### 初版の使用

新しいシーンを開くと、`Kami4_髪_計算結果` と200フレームのキャッシュが接続済みです。三次元ビューの「髪4」で キャッシュ再生 を有効にし、タイムラインを動かしてください。再計算は 初期化 → 全フレーム計算、1フレームだけなら 1フレーム計算、開始形状へ戻す場合は 開始形状へ戻す を使用します。全フレーム計算 はエスケープキーで中止できます。

操作用キャッシュは `outputs/scene_cache` です。検証結果の原本 `outputs/real_final` は別に保存しています。シーンを別の場所へ移す場合はキャッシュもコピーし、髪4パネルのパスを変更してください。

材質と固定回数は [拡張の設定ファイル](extension/parameters.json) の一つにあります。値を変更する際は新しいキャッシュフォルダーを指定して初期化します。入力する髪と身体メッシュは編集せず、計算結果を別のカーブへ書き戻します。処理とキャッシュの詳細は [構造説明](docs/ARCHITECTURE.md) に記載しています。

### 初版のビルドと再現

今回の環境: ブレンダー 5.2.2 長期支援版、アールティーエックス 5070 ティーアイ、ドライバー 616.92、クーダ開発環境 12.9.41、マイクロソフトC/C++コンパイラ 19.44。C言語二進呼出規約ヘッダーはC11/C++の両方で使用できます。

```powershell
./tools/build.ps1
ctest --test-dir build --output-on-failure
python tests/protocols.py --output outputs/protocols_final
python tests/benchmark.py
python tools/run_real.py --name real_final
python tools/replay_failure.py
python tools/package.py
```

`run_real.py` は今回保存した `outputs/input` を使います。元のブレンダー入力はユーザーのアセットなのでギットには含めません。`tests/blender_full_bake.py` は別名保存したシーンをブレンダーの無画面実行から読み、拡張の全フレーム計算操作で200フレームを検証します。`tests/restart_replay.py` は別プロセスで200キャッシュの巡回冗長検査と実際のカーブへの再生を検証します。

64ビット浮動小数点参照計算は検証専用です。ブレンダー拡張から呼ばれる中央処理装置への代替実行ではありません。

```powershell
python -m venv --system-site-packages .venv
./.venv/Scripts/python.exe -m pip install -r requirements-test.txt
./.venv/Scripts/python.exe -c "import sys; sys.path[:0]=['tests','extension']; import protocols; from cpu_oracle import CPUOracle; protocols.Solver=CPUOracle; protocols.run('outputs/protocols_cpu_final')"
```

## 構成

- `native/`：クーダの中核処理と公開C言語二進呼出規約。
- `extension/`：日本語操作画面、入力評価、ネイティブ処理との接続、巡回冗長検査付きキャッシュ。
- `tests/`：独立した64ビット浮動小数点参照実装、C言語二進呼出規約、物理3試験、性能、ブレンダーの操作と再起動再生。
- `tools/`: ビルド、入力抽出、最小失敗ケース、パッケージ作成。
- `docs/`: 原仕様、実装判断、実測値、未達事項。

制作：塚本吉彦。2026年に日本で制作。著作権はベルヌ条約および日本の著作権法に従います。元の髪・髪3リポジトリのコードとキャッシュは変更していません。

# ACES 再開用の記録 — 2026-09-17 作業終了

ユーザーの最終指示は「記憶を残して終わります。電源断にそなえてください」。この文書と終了用バックアップを保存して停止する。PCのシャットダウンは実行していない。新しい仮説の実装・再シミュレーションは始めない。

## 1. 最初に開くもの

- **作業リポジトリ**：`C:\Users\azoo\git\kami4-bvh-experiment`
- **終了時のBlender**：`C:\Users\azoo\git\kami4-bvh-experiment\outputs\checkpoints\session-end-20260917\scene.blend`
- **終了画面**：87F、通常のPERSPビュー。ユーザーが動かした現在の視点を保存した。
- **終了時のGitブランチ**：`docs/poweroff-handoff-20260917`
- **終了用タグ／Release**：`session-end-20260917`
- **設計書**：[ACES_DESIGN_JA.md](ACES_DESIGN_JA.md)

最初の環境cwdは `C:\Users\azoo\git\kami-hair-solver` だったが、現在のACES実装は上記の別リポジトリにある。旧 `kami-hair-solver` と `git/ageha` は参考用。そこへ現在のコードを上書きしない。

終了用シーンの隣に `cache`、`parameters.json`、拡張0.3.0のZIPを保存した。シーンは `//cache` と `//parameters.json` を参照する。フォルダー一式を維持して開けば、再計算せず1〜200Fを再生できる。元の採用シーンとキャッシュは上書きしていない。

## 2. 現在の採用版と保存点

ユーザーは局所FK v2に対して「現時点で満足できる性能」と評価し、採用・PUSHを指示した。実装作業は完了し、採用記録もPUSH済み。

| 対象 | 保存点 |
|---|---|
| 数値実装 | `eab0400d5615f3c1abe833398ab05d9f15dbf21f` |
| 現在の採用タグ | `baseline-local-fk-adopted-20260917` |
| 採用記録commit | `54a6e33` |
| 200Fの元バックアップ | `review-local-fk-200f-20260917` |
| 日本語設計書commit／タグ | `b04bb0a` / `design-local-fk-v1-20260917` |
| 衝突修復前の採用版 | `baseline-bending50-adopted-20260917` |
| 不採用の局所FK v1 | `experiment-local-fk-v1-20260917`。毛先まで同じ回転を伝え、変位を増幅した |

GitHubは [ysk424/kami4-hair-solver](https://github.com/ysk424/kami4-hair-solver) の**プライベート**リポジトリ。既存タグを動かしたり、既存Release資産を上書きしたりしない。

## 3. 現在の方式の要点

線形implicit bending、長さの三重対角補正、速度Coulomb impulseというモデルの基本を維持している。原仕様からの変更は [設計書](ACES_DESIGN_JA.md) 第2章に対応表がある。

- 全bodyの三角形をBVHで扱う。表示する毛の全区間に接触判定を行う。
- bodyの全200F頂点とtargetをVRAMに事前転送するresident経路を使用。
- 短い毛は最小30cmまで非表示延長し、表示は元の長さ。すべての毛へ30cmを加算する設定ではない。
- node・区間projection後の残留接触を、根元側の最寄りの安全な関節を支点に局所FKで修復する。
- 支点までの位置を維持し、支点から接触端点まで回転。その先は修復前の世界方向を保ち、rest長でつなぎ直す。毛先全体へ同じ回転を伝えない。
- 修復後は支点から再検査する。今回の毛は最大9修復/substep、36修復/frame。時間を巻き戻す再計算やNewton収束ではない。
- FKの幾何補正変位は再構築速度から除去する。曲げの式自体を置き換えていない。
- 原仕様の「データ依存追加反復0」とは異なり、接触状態に応じた上限付き処理になっている。上限以内の完全解決を保証していない。

主要実装は `native/local_fk_contact.inl`、`native/segment_contact.inl`、`native/core.cu`。設計書第8章に支点、回転、再配置、打ち切りの式と処理図がある。

## 4. 入力と完全設定

入力「カーブ」6,757本、表示74,327点（各毛11点）、延長後102,869点。body「CC_Base_Body」225,184頂点、449,472三角形。24fps、1〜200F。根元2点固定。出力は「Kami4_BVH_髪_計算結果」。

完全設定は [presets/local-fk-contact-20260917.json](../presets/local-fk-contact-20260917.json)。`extension/parameters.json`だけではPや延長設定が違うため復元できない。

| 項目 | 採用値 |
|---|---:|
| 曲げ剛性 | 5e-7 N·m² |
| 線密度 | 0.0001 kg/m |
| 減衰 / 摩擦 | 8 s⁻¹ / 0.35 |
| 重力 | 9.80665 m/s² |
| substeps / length_passes / impulse_sweeps | 4 / 8 / 3 |
| 相対正則化 | 1e-7 |
| 衝突半径 / 接触余裕 | 0.04mm / 0.15mm |
| mesh_contact_mode | 2 |
| 最小計算長 / 延長区間上限 | 30cm / 1cm |
| 延長部分の長さ反復 | 16 |
| 表示区間の追加細分化 | なし |

日本語Nパネル名は「ACES」。剛性と正則化はlog10表示。局所FKのプロパティ既定値は旧シーン保護のためオフだが、採用シーンではオン。復帰時は完全設定とキャッシュのhashを照合する。

## 5. 性能・品質の記憶

- 局所FKなし61.4487秒 → 採用v2 **106.9436秒/200F、平均0.53472秒/F**。計算＋cache保存で、レンダリング時間ではない。
- 22/23/71/100/164/200Fの交差区間数：変更前247/257/304/362/507/545 → 採用版3/0/2/3/2/0。
- 全200Fの最大は76Fの6交差区間、2本。交差した毛の本数の最大は別frameで3本。71frameは中心線交差0。
- 表示辺長誤差最大1.8773%、固定点最大座標差約0.1192µm。NaN/Inf・BVH overflowなし。
- 非表示延長込みの辺長誤差最大4.7690%、最大substep変位90.987mmなどの残課題がある。半径込みのFK未解決flagも残る。
- ユーザー採用は実髪の実用的な評価。現在の完全設定で原仕様T1〜T3・合成負荷の全受入を再実行した、という意味ではない。

比較元と比較先で曲げ5e-7などは同じ。主な設定差はmode1→2。速度は各1回の実測で、専用環境の厳密なbenchmarkではない。[元の証拠](experiments/local-fk-contact-20260917/README.md)を参照。

## 6. 電源断用の保存と検証

終了用シーンを別名保存し、独立したBlenderプロセスで開き直した。保存frame87、完全設定・DLL一致、200F全cacheのCRC、87/1/200Fの自動再生を確認。Solver呼出しは禁止して検証し、再シミュレーションはしていない。参照が切れた外部画像は0。詳細は [reopen_verification.json](sessions/session-end-20260917/reopen_verification.json)。

Blender保存直後の `is_dirty` はtrueだったが、保存済みファイルを別プロセスで読み、上記の状態がディスクへ残っていることを検証した。現在のプロセスのdirty表示だけで保存失敗と判断せず、検証記録とファイルを参照する。

[終了用Release](https://github.com/ysk424/kami4-hair-solver/releases/tag/session-end-20260917)に `session-end-20260917.zip` を保存する。scene、200F cache、完全設定、拡張ZIP、設計書、原仕様、終了メモ、SHA256検証スクリプトを含む。PC側を失った場合は展開し、同梱拡張0.3.0を使って `scene.blend` を開く。

| 対象 | SHA256 |
|---|---|
| 採用DLL `kami4_hair_core_fk1.dll` | `0c5db7c3cc80ca80b86394d25e4ff5541bb7e1af5362efd9c2245a86962a221e` |
| canonical parameter hash | `f9473015f35d7d081ab5be07e23fe2b100288552af3a35456e039f6888fcd29b` |
| 拡張0.3.0 ZIP | `59b1d1708d94f6c5f5f0a3fae8d9cf468578a0272b6009e3aad8e93c592f6400` |

終了ZIPのhashとサイズは [backup.json](sessions/session-end-20260917/backup.json) に記録する。従来の採用Releaseと200Fバックアップも保持してある。

## 7. 次回の進め方とユーザーの方針

1. 上記の終了用シーンと設計書を開いて状況を確認する。現在の状態から勝手に追加実験を開始しない。
2. ユーザーと次の仮説を決めてから実装する。モデルの基本を崩さず、適切なパラメータと局所衝突処理を育てる方針。
3. 仮説ごとにブランチ、cache、blend、必要ならDLL名を分ける。採用版を保護し、良ければ採用、NGなら戻す。失敗記録も残す。
4. 根元2点固定、同じ髪・body・200Fで比較する。貫通はmin_gapだけで判断せず、実区間交差と目視を併用する。
5. 変更種類だけでなく**変更量の妥当性**を先に説明する。量が小さすぎて差が出ない場合と、大きすぎて暴走する場合を区別する。
6. ユーザーは曲げと衝突を別課題として調整したい。頭と髪外側の距離を縮める希望は、現在も約2cmの達成を保証したものではない。
7. 長時間作業はおおむね90分で一度区切り、画面で確認できる状態と進捗を報告する。停止指示があれば追加作業を広げない。
8. ロード済みDLLの上書き、元入力blendの上書き、既存タグの移動、強制push、`reset --hard`は行わない。

Blender接続はTCP `127.0.0.1:9876`、クライアントは `tools/blender_mcp.py`。拡張moduleは `bl_ext.user_default.kami4_bvh_hair_solver`、実体は `C:\Users\azoo\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\kami4_bvh_hair_solver`。再開時に実際の接続・DLL・設定を確認する。

電源断後、GPU上の状態は残らない。保存cacheからの表示再生はできるが、cacheだけで任意frameの内部速度・非表示点・接触impulseを完全復元して物理計算を続行する形式ではない。新しい条件の比較計算は、新しい保存先へ1Fから行う。

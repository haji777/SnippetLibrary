# SnippetLibrary

Houdini / Nuke のノードネットワークを保存できます。

Claudeが書きました。

ライブラリは複数作ってリンクできるので、自分用、チームやり取り用、プロジェクト用など用途に応じて管理しやすいです。
https://github.com/haji777/SnippetLibrary/tree/main
シンプルなコードです。インストール不要。ご自身で好きに改変してOKです。自己責任でお使いください。

コード入出力は各アプリの標準機能を使ってますので、将来ご自身で新しいライブラリツールを作る時も資産を引き継ぎやすいです。

標準的なPythonライブラリしか使ってません。DBもつかってません。

- DCC でノードを選択 → **Save Selection to Library**（タイトル・ファイル名・説明・タグ）
  - **タイトル**は表示名（日本語可）、**ファイル名**は半角英数字のみ。ダイアログに実際のファイル名がプレビューされます
- ビューアーで一覧（ソフト / ユーザー / コンテキスト / ライブラリで絞り込み、時系列、👑殿堂入り）
- スニペットを開くとノードネットワークを描画。ノードをクリックで**変更されたパラメータ**、
  ダブルクリックで subnet / Group の中へ
- ビューアーの **Load** で、起動中の Houdini / Nuke に読み込み

## セットアップ

ダウンロードしてどこかに置いてください。

### ビューアー
`launch_viewer.bat` を実行（Python 3 標準ライブラリのみ。ブラウザが開きます）。
プロジェクト毎に bat をコピーして `SNIPPETLIB_ROOT` を書き換える運用を想定。

### Python について
- **pip インストールは一切不要**（全コード標準ライブラリのみ。DCC 内は同梱の PySide6/PySide2 を使用）
- ビューアー: Python **3.7 以上**ならどれでも可。bat は `py -3` → `python` → **Houdini 同梱 python** → **Nuke 同梱 python** の順に探すので、
  Python を入れていないマシンでも動きます（Microsoft Store のダミー `python.exe` は自動でスキップ）。固定したい場合は `SNIPPETLIB_PYTHON`
- DCC 側: 各アプリ内蔵の Python で動作（Houdini 20.0〜22 = 3.10/3.11/3.13、Nuke 13〜16 = 3.7〜3.11）。コードは 3.7 互換の書き方に統一
- Houdini は `hou.data`（レシピ API）が必要なので **Houdini 20.0 以上**
- Houdini が新しい Python（例 3.14）に上がったら `houdini/python3.14libs/uiready.py` を他からコピーして追加してください
  （無くても Save/Load は動き、ブリッジはメニュー初回使用時に開始されます）
- ファイルはすべて UTF-8 明示で読み書きするので、日本語タイトル/コメントは OS のコードページ(cp932)に依存しません

### Houdini
`houdini/packages/snippetlibrary.json` の中の `SNIPPETLIB_REPO` をこのリポジトリの場所に書き換え。

`Documents/houdini22.0/packages/` にコピーする。

- メニューバー **SnippetLibrary**（Save / Load / Open Viewer）
- ノード右クリック **Save Selection to Snippet Library...**
- シェルフ **SnippetLibrary**
- 起動時に `uiready.py` がビューアー連携ブリッジを開始

### Nuke
`~/.nuke/init.py` に追加:
```python
nuke.pluginAddPath("C:/path/to/SnippetLibrary/nuke")  # このリポジトリの nuke フォルダ
```
メニューバーに **SnippetLibrary** が追加されます。



### 環境変数（プロジェクトのランチャー bat などで設定）
| 変数 | 内容 |
|---|---|
| `SNIPPETLIB_ROOT` | このプロジェクトのライブラリ。未設定ならビューアーの ⚙ で設定したパス（`%LOCALAPPDATA%\SnippetLibrary\settings.json`）、それも無ければ `<repo>/snippetLibrary` |
| `SNIPPETLIB_USER` | ユーザー名の上書き。未設定なら Windows のユーザー名 |
| `SNIPPETLIB_LINKS` | 追加で表示する他ライブラリ（`;` 区切り）。ビューアーの設定画面からもリンク可能 |

ライブラリの場所は **ビューアー右上の ⚙ → Libraries → ライブラリのパス** から変更できます（マシン単位の設定。DCC 側も同じ設定を読みます）。
複数プロジェクトを切り替える運用なら、プロジェクトのランチャー bat で `SNIPPETLIB_ROOT` を設定してください（環境変数がある間は ⚙ からは変更できません）。
ライブラリはコードのフォルダとは別の場所に置いてください（例: `D:\Projects\Snippets`）。

### 複数ライブラリ（個人用 / 共有用 など）
- ⚙ → **新しいライブラリを作成**: 空のフォルダにライブラリを作り、自動でリンクします（例: 共有ドライブ上の `Shared`）
- ⚙ → **既存のライブラリをリンク**: 他プロジェクトのライブラリを一覧に混ぜて表示
- DCC の保存ダイアログの **Library** で保存先（自分のライブラリ or リンク済みライブラリ）を選べます
- スニペット詳細の **Copy to →** で別のライブラリへコピー（元は残り、コピーの `.md` に `origin` / `author` が記録されます）

## ビューアー → DCC へのロードの仕組み
ソケットは使わずファイルベース。DCC 側が QTimer（メインスレッド）で 1.5 秒毎にローカルの inbox を監視します（生存通知の書き込みは 10 秒毎）。

```
%LOCALAPPDATA%\SnippetLibrary\sessions\<app>_<pid>.json     起動中セッション（heartbeat, シーン名, バージョン）
%LOCALAPPDATA%\SnippetLibrary\sessions\<app>_<pid>.inbox\   ビューアーが置く load リクエスト / DCC が返す結果
```
- Houdini: 現在の Network Editor の場所に `hou.data.createItemsFromData()`。コンテキストが違う場合は
  適切なコンテナ（geo / copnet ...）を自動作成してその中に展開
- Nuke: `nuke.nodePaste()` して DAG の中央へ移動。ブリッジ無しでも **Copy .nk** → Nuke で Ctrl+V が使えます
- 保存時と違うバージョンにロードした場合は結果メッセージに警告を表示
- DCC 内の **Load from Library...** ダイアログはビューアー無しでも使えます
  
### 保存ダイアログの入力補助
- **Title / File name** はプルダウンに直近 20 件の履歴が出ます。入力中は、過去のタイトル・ファイル名を単語に分解した辞書（`_`・`-`・空白・camelCase で分割）から**カーソル位置の単語**を補完します
- **Tags** は ▾ ボタンで使用中のタグ一覧（使用回数順）から追加、入力中はカンマ区切りの最後の語を補完します
- File name に空白は使えません。空白を打つと自動で `_` になります

### 上書き（新しいバージョン）
メニュー **Overwrite Exist Snippet (New Version)...**（Houdini: メニューバー / 右クリック / シェルフ、Nuke: メニューバー）。
1. ノードを選択してから実行すると、既存スニペットの選択画面が開きます
2. 選んだスニペットの内容（タイトル・ファイル名・タグ・説明・保存先）が入った保存ダイアログが開き、タイトルには `v2`（`v2` なら `v3`）が付きます
3. 保存すると旧バージョンの `.md` に `superseded_by`、新バージョンに `supersedes` / `version` が記録されます
- ビューアーでは旧バージョンは**打ち消し線**つきで表示され、左の「旧バージョンも表示」で隠せます。詳細画面には新旧を行き来するリンクが出ます
- Houdini / Nuke の **Load from Library** では旧バージョンは出ません（「旧バージョンも表示」をオンにすれば見えます）
- ファイルは何も消さないので、旧バージョンもそのまま Load できます

### タイトル変更と削除
- **タイトル変更**（ビューアー詳細画面の ✎ / タイトルをダブルクリック）: 表示名だけが変わります。
  ファイル名（`<user>_<context>_<name>.*`、`name` は保存時に決めた半角英数字）とフォルダ名（ID）は変わらないのでリンクは切れません
- **削除**（詳細画面の 🗑）: ファイルは消さず `<library root>/_trash/<app>/<user>/<context>/<ID>__<削除日時>/` へ移動。
  `.md` に `deleted` / `deleted_by` / `deleted_from` を記録します。復元はフォルダを `deleted_from` の場所へ戻すだけ
  （`_` で始まるフォルダは一覧のスキャン対象外）

### 同時書き込みについて
- スニペット ID（`20260920.001`）は `os.mkdir` の原子性で確保するので、同時保存でも衝突しません
- すべてのファイルは一時ファイル → `os.replace` で書き込み
- `.md` の編集（コメント / 👑）は書き込み直前に mtime を再確認し、競合したら読み直してリトライ
- 一覧のキャッシュは各マシンの `%LOCALAPPDATA%\SnippetLibrary\cache` に置く（共有フォルダには書かない）

## 既存ファイルの登録
```
py -3 tools/register.py B:/path/to/snippet.json --title "表示名" --name ascii_name --context cop --app-version 22.0.429 --desc "..." --tags a,b
py -3 tools/register.py B:/path/to/tool.nk --title "..." --context comp
```

## 構成
| | |
|---|---|
| `snippetlib/core.py` | ライブラリ構成・ユーザー・プロファイル・md 読み書き・スキャン・リンク・インポート |
| `snippetlib/graph.py` | Houdini JSON / .nk → ビューアー用グラフ、md 生成（純 Python） |
| `snippetlib/bridge.py` | ビューアー ⇄ DCC のファイルベース連携 |
| `snippetlib/qtui.py` | 保存ダイアログ / DCC 内ブラウザ（PySide6 / PySide2） |
| `snippetlib/houdini_io.py`, `snippetlib/nuke_io.py` | 各 DCC の保存・ロード |
| `viewer/` | ローカル Web ビューアー（`server.py` + `static/`） |

## フォルダ構成

```
<library root>/                          ← SNIPPETLIB_ROOT（プロジェクト毎に置くのを推奨）
  _config/library.json                   ライブラリ名・色・リンク先ライブラリ
  _config/profiles/<user>.json           ユーザー毎のプロファイル（表示名・カラー）
  houdini/<user>/<context>/<YYYYMMDD.NNN>/
      <user>_<context>_<name>.json         本体: hou.data.itemsAsData() の JSON（Houdini 20+）
      <user>_<context>_<name>.md           メタ情報(frontmatter) + 説明 + ノード/変更パラメータ一覧
      <user>_<context>_<name>.graph.json   ビューアー描画用（位置・接続・階層・変更パラメータ）
  nuke/<user>/<context>/<YYYYMMDD.NNN>/
      ....nk / .md / .graph.json           本体は nuke.nodeCopy() の .nk
```

`.md` の frontmatter に `app_version`（例 `22.0.429` / `16.0v4`）、`crown`、`tags`、`created` などが入ります。
frontmatter は Obsidian のプロパティとしても読めます（ライブラリのルートを vault として開けば閲覧・検索可能）。
`.graph.json` が無くても、ビューアーは `.json` / `.nk` 本体からネットワークを復元します。

## ライセンス
[zlib License](LICENSE) — Copyright (c) 2026 hajime

- 商用利用・改変・再配布は自由です。無料で、今後も販売する予定はありません
- **出所を偽らないでください**（自分が作ったと主張しない）。改変したものは改変版であることを明示してください
- ソース配布から LICENSE の表示を削除・変更しないでください
- お願い（ライセンス条件ではありません）: ほぼそのままの内容を別の名前で配るのはご遠慮ください。フォークや改良は歓迎です

## 免責
本ソフトウェアは現状のまま（as-is）提供され、明示・黙示を問わず一切の保証はありません。
使用によって生じたいかなる損害（データの消失、シーンファイルの破損、業務上の損失などを含む）についても、作者は責任を負いません。**自己責任でご利用ください。**
共有ライブラリやプロジェクトのデータを扱うツールなので、導入前にバックアップと動作確認をおすすめします。

## 依存関係・第三者の権利
- 同梱している第三者のコード・フォント・画像は**ありません**。Python 標準ライブラリのみで動作し、pip パッケージは不要です
- Houdini / Nuke の中では、各アプリケーションに同梱されている Python API（`hou` / `nuke`）と PySide6 / PySide2（LGPL。本リポジトリには含まれません）を利用します。利用には各アプリケーションの正規ライセンスが必要です
- アプリのロゴは同梱していません。ビューアーは、利用者のマシンにインストールされている Houdini / Nuke からロゴを見つけた場合に、そのマシン内でのみ表示に使います
- Houdini は SideFX Software Inc.、Nuke は The Foundry Visionmongers Ltd. の商標または登録商標です。本プロジェクトは両社とは無関係の非公式ツールであり、両社による承認・後援を受けたものではありません

## チームでの配置について
- コードは共有フォルダに置いて各自が `launch_viewer.bat` を叩く運用で問題ありません（UNC パスからの起動にも対応）。
  ビューアーは各自のマシンで動き、`127.0.0.1` だけで待ち受けます。アプリとの連絡用ファイルも各自の `%LOCALAPPDATA%` に作られ、共有されません
- **コードの置き場は管理者のみ書き込み可**にしてください。そこにあるコードは全員の Houdini / Nuke の中で実行されます
- スニペットのデータ（ライブラリ）は別フォルダに置き、使う全員に書き込み権限が必要です（保存・コメント・殿堂入り・ごみ箱移動はすべて書き込み）
- 他人のスニペットを読み込むことは、他人の `.hip` / `.nk` を開くのと同じです。Python を含むノードはその場で実行されます

## 調査用ツール: ノードの比較
ロードしたスニペットが元と違う気がするときに、2つのネットワークを再帰的に比べて差分だけを表示します（Houdini の Python Shell で）。
```python
import sys; sys.path.append("C:/path/to/SnippetLibrary/tools")
import compare_nodes
compare_nodes.compare("/stage/editmaterial1", "/stage/editmaterial7")   # 差分を表示
compare_nodes.dump("/stage/editmaterial1", "C:/temp/editmaterial1.json")  # 1つを JSON に書き出し
```
比較対象: ノードタイプ、全パラメータ（値・式・既定値かどうか）、パラメータテンプレート、入力接続、VOP のコネクタ名と型、フラグ、ユーザーデータ、エラー。

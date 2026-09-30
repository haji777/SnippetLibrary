# SnippetLibrary

Houdini / Nuke のノードスニペットを **ファイルだけ**（DB なし）で管理するライブラリ。

- DCC でノードを選択 → **Save Selection to Library**（タイトル・ファイル名・説明・タグ）
  - **タイトル**は表示名（日本語可）、**ファイル名**は半角英数字のみ。ダイアログに実際のファイル名がプレビューされます
- ビューアーで一覧（ソフト / ユーザー / コンテキスト / ライブラリで絞り込み、時系列、👑殿堂入り）
- スニペットを開くとノードネットワークを描画。ノードをクリックで**変更されたパラメータ**、
  ダブルクリックで subnet / Group の中へ
- ビューアーの **Load** で、起動中の Houdini / Nuke に読み込み

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

## セットアップ

### 環境変数（プロジェクトのランチャー bat などで設定）
| 変数 | 内容 |
|---|---|
| `SNIPPETLIB_ROOT` | このプロジェクトのライブラリ。未設定ならビューアーの ⚙ で設定したパス（`%LOCALAPPDATA%\SnippetLibrary\settings.json`）、それも無ければ `<repo>/snippetLibrary` |
| `SNIPPETLIB_USER` | ユーザー名の上書き。未設定なら Windows のユーザー名 |
| `SNIPPETLIB_LINKS` | 追加で表示する他ライブラリ（`;` 区切り）。ビューアーの設定画面からもリンク可能 |

ライブラリの場所は **ビューアー右上の ⚙ → Libraries → ライブラリのパス** から変更できます（マシン単位の設定。DCC 側も同じ設定を読みます）。
複数プロジェクトを切り替える運用なら、プロジェクトのランチャー bat で `SNIPPETLIB_ROOT` を設定してください（環境変数がある間は ⚙ からは変更できません）。
ライブラリはコードのフォルダとは別の場所に置いてください（例: `D:\Projects\Snippets`）。

### Houdini
`houdini/packages/snippetlibrary.json` を `Documents/houdini22.0/packages/` にコピーし、中の `SNIPPETLIB_REPO` をこのリポジトリの場所に書き換え。
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

## ビューアー → DCC へのロードの仕組み
ソケットは使わずファイルベース。DCC 側が QTimer（メインスレッド）で 0.7 秒毎にローカルの inbox を監視します。

```
%LOCALAPPDATA%\SnippetLibrary\sessions\<app>_<pid>.json     起動中セッション（heartbeat, シーン名, バージョン）
%LOCALAPPDATA%\SnippetLibrary\sessions\<app>_<pid>.inbox\   ビューアーが置く load リクエスト / DCC が返す結果
```
- Houdini: 現在の Network Editor の場所に `hou.data.createItemsFromData()`。コンテキストが違う場合は
  適切なコンテナ（geo / copnet ...）を自動作成してその中に展開
- Nuke: `nuke.nodePaste()` して DAG の中央へ移動。ブリッジ無しでも **Copy .nk** → Nuke で Ctrl+V が使えます
- 保存時と違うバージョンにロードした場合は結果メッセージに警告を表示
- DCC 内の **Load from Library...** ダイアログはビューアー無しでも使えます

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

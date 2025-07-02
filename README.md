# lstty

システム内で有効なすべてのttyとptsを抽出し、それらの端末に接続して実行されているコマンドをグルーピングしてリストアップするツールです。

## 特徴

- 現在システム上で利用されているtty/ptsを一覧表示
- 各端末で実行されているコマンドをグルーピング
- PythonとShellで実装

## インストール

```bash
git clone https://github.com/ken3/lstty.git
cd lstty
# Pythonバージョンを使用する場合は、依存パッケージをインストール
pip install psutil
```

## 使い方

### Bashスクリプト版（依存関係なし）

```bash
./lstty.sh
# 詳細情報を表示する場合
./lstty.sh -v
```

### Pythonスクリプト版（psutilが必要）

```bash
python3 lstty.py
# 詳細情報を表示する場合
python3 lstty.py -v
# ツリー形式で表示する場合
python3 lstty.py -tree
```

## サンプル出力

### 基本モード

```
---
Active TTY/PTS Sessions and their Commands:
---
## TTY/PTS: /dev/pts/0
  User: runner (Logged in at: 2025-07-02 09:15)
  Commands running:
    * bash --norc --noprofile

## TTY/PTS: /dev/pts/1
  User: runner (Logged in at: 2025-07-02 09:16)
  Commands running:
    * bash --norc --noprofile
    * /bin/bash ./lstty.sh

## TTY/PTS: /dev/pts/2
  User: root (Logged in at: 2025-07-02 09:10)
  Commands running:
    * bash --norc --noprofile
    * /sbin/agetty -o -p -- \u --keep-baud 115200,57600,38400,9600 - vt220
    * /sbin/agetty -o -p -- \u --noclear - linux

---
```

### 詳細モード（-v オプション）

```
---
Active TTY/PTS Sessions and their Commands:
---
## TTY/PTS: /dev/pts/0
  User: runner (Logged in at: 2025-07-02 09:15)
  Commands running:
    * bash --norc --noprofile (PID: 3297, User: runner, EXE: /usr/bin/bash)

## TTY/PTS: /dev/pts/1
  User: runner (Logged in at: 2025-07-02 09:16)
  Commands running:
    * bash --norc --noprofile (PID: 3299, User: runner, EXE: /usr/bin/bash)
    * /bin/bash ./lstty.sh -v (PID: 3514, User: runner, EXE: /usr/bin/bash)

## TTY/PTS: /dev/pts/2
  User: root (Logged in at: 2025-07-02 09:10)
  Commands running:
    * bash --norc --noprofile (PID: 3300, User: root, EXE: /usr/bin/bash)
    * /sbin/agetty -o -p -- \u --keep-baud 115200,57600,38400,9600 - vt220 (PID: 921, User: root, EXE: )
    * /sbin/agetty -o -p -- \u --noclear - linux (PID: 993, User: root, EXE: )

---
```

## ライセンス

MIT License
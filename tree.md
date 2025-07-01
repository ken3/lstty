# lstty - TTY/PTS セッション監視ツール チャット討議内容

## 概要

lstty.sh は、システム内で有効なすべてのTTYとPTS（疑似端末）を抽出し、それらの端末に接続して実行されているコマンドをグルーピングしてリストアップするBashスクリプトです。

## 現在の機能

### 基本機能
- システム内の全プロセスを/procファイルシステムから監視
- TTY/PTS に接続されているプロセスの識別
- ユーザー情報とログイン時刻の取得
- 実行中のコマンドのグルーピング表示

### オプション
- `-v` (verbose): 詳細情報表示（PID、実行ファイルパス、プロセスユーザー）

## 現在の出力例

### 基本モード（`./lstty.sh`）
```
---
Active TTY/PTS Sessions and their Commands:
---
## TTY/PTS: /dev/pts/0
  User: Unknown User (Logged in at: N/A)
  Commands running:
    * bash --norc --noprofile

## TTY/PTS: /dev/pts/1
  User: Unknown User (Logged in at: N/A)
  Commands running:
    * bash --norc --noprofile
    * /bin/bash ./lstty.sh
    * /sbin/agetty -o -p -- \u --keep-baud 115200,57600,38400,9600 - vt220
    * /sbin/agetty -o -p -- \u --noclear - linux

---
```

### 詳細モード（`./lstty.sh -v`）
```
---
Active TTY/PTS Sessions and their Commands:
---
## TTY/PTS: /dev/pts/0
  User: Unknown User (Logged in at: N/A)
  Commands running:
    * bash --norc --noprofile (PID: 3292, User: runner, EXE: /usr/bin/bash)

## TTY/PTS: /dev/pts/1
  User: Unknown User (Logged in at: N/A)
  Commands running:
    * bash --norc --noprofile (PID: 3294, User: runner, EXE: /usr/bin/bash)
    * /bin/bash ./lstty.sh -v (PID: 3541, User: runner, EXE: /usr/bin/bash)
    * /sbin/agetty -o -p -- \u --keep-baud 115200,57600,38400,9600 - vt220 (PID: 904, User: root, EXE: )
    * /sbin/agetty -o -p -- \u --noclear - linux (PID: 911, User: root, EXE: )

---
```

## 提案された機能: -tree オプション

### 期待される出力例（`./lstty.sh -tree`）
```
TTY/PTS Process Tree:
=====================

/dev/pts/0 (User: runner, Login: 2025-07-01 11:28)
├── bash --norc --noprofile [PID: 3292]
└── (no child processes)

/dev/pts/1 (User: runner, Login: 2025-07-01 11:30)
├── bash --norc --noprofile [PID: 3294]
│   └── ./lstty.sh -tree [PID: 3600]
├── /sbin/agetty [PID: 904] (User: root)
│   └── (system process)
└── /sbin/agetty [PID: 911] (User: root)
    └── (system process)

/dev/tty1 (User: root, Login: N/A)
├── systemd --user [PID: 1200]
│   ├── pulseaudio [PID: 1250]
│   └── gnome-session [PID: 1300]
│       ├── gnome-shell [PID: 1350]
│       └── nautilus [PID: 1400]
└── login [PID: 800]
    └── bash [PID: 850]
        └── vim /etc/config [PID: 900]
```

### -tree オプションの実装方針

1. **プロセス親子関係の解析**
   - `/proc/[PID]/stat` からPPID（親プロセスID）を取得
   - 各TTY/PTS内でのプロセスツリー構造を構築

2. **ツリー表示フォーマット**
   - Unicode文字（├─, └─, │）を使用した視覚的な階層表示
   - インデントによる階層レベルの表現

3. **追加情報の表示**
   - プロセスの起動時刻
   - CPU使用率
   - メモリ使用量（オプション）

## 現在の lstty.sh 全文

```bash
#!/bin/bash
# 機能: システム内で有効なすべてのttyとptsを抽出し、それらの端末に接続して実行
#       されているコマンドをグルーピングしてリストアップする
# 作成: 2025-07-01 k_tsuka /w Google Gemini 2.5 Flash
# 更新: 2025-07-01 k_tsuka /w Google Gemini 2.5 Flash

declare -A tty_commands
declare -A tty_users
declare -A tty_login_times

# Option to show verbose output (PID, EXE path, and Process User)
SHOW_VERBOSE=false
if [[ "$1" == "-v" ]]; then
    SHOW_VERBOSE=true
fi

# Get login information from utmp (for login TTYs)
# This helps identify the primary user and login time for a TTY/PTS
while IFS= read -r line; do
    user=$(echo "$line" | awk '{print $1}')
    tty=$(echo "$line" | awk '{print $2}')
    login_time=$(echo "$line" | awk '{print $3 " " $4}') # Combine date and time
    tty_users["$tty"]="$user"
    tty_login_times["$tty"]="$login_time"
done < <(who | awk '{print $1, $2, $3, $4}')

# Iterate through all processes
for pid_dir in /proc/[0-9]*; do
    pid=$(basename "$pid_dir")

    # Check if stat file exists
    [[ ! -f "$pid_dir/stat" ]] && continue

    # Read stat file for tty_nr (controlling terminal)
    # The 7th field in /proc/PID/stat is tty_nr
    read -r _ _ _ _ _ _ tty_nr rest < "$pid_dir/stat"

    # If tty_nr is 0, it's not associated with a TTY/PTS in a standard way
    [[ "$tty_nr" -eq 0 ]] && continue

    # Get the TTY path from standard input symlink
    tty_path=""
    if [[ -L "$pid_dir/fd/0" ]]; then
        tty_path=$(readlink -f "$pid_dir/fd/0")
        # Ensure TTY name is correctly extracted (e.g., pts/0, tty1)
        if [[ "$tty_path" =~ ^/dev/(tty|pts)/([0-9]+)$ ]]; then
            tty_type=${BASH_REMATCH[1]} # e.g., "tty" or "pts"
            tty_num=${BASH_REMATCH[2]}  # e.g., "1" or "0"
            tty_name="${tty_type}/${tty_num}" # e.g., "pts/0" or "tty1"
        elif [[ "$tty_path" =~ ^/dev/(tty[0-9]+)$ ]]; then # Fallback for plain ttyN
             tty_name=${BASH_REMATCH[1]} # e.g., "tty1"
        else
            tty_name="" # Not a standard TTY/PTS
        fi
    fi

    [[ -z "$tty_name" ]] && continue # Skip if no valid tty_name found

    # Get the command name from cmdline (full command line)
    cmd=""
    if [[ -f "$pid_dir/cmdline" ]]; then
        # Read the command line, replacing nulls with spaces
        cmd=$(tr '\0' ' ' < "$pid_dir/cmdline" | sed 's/ $//')
    fi

    [[ -z "$cmd" ]] && continue # Skip if command is empty

    # Prepare command string based on SHOW_VERBOSE flag
    display_cmd="$cmd"
    if "$SHOW_VERBOSE"; then
        # Get the executable path from /proc/PID/exe symlink
        exe_path="N/A"
        if [[ -L "$pid_dir/exe" ]]; then
            exe_path=$(readlink -f "$pid_dir/exe")
        fi

        # --- NEW: Get the effective user name of the process ---
        # Get UID from /proc/PID/status or stat file, then convert to name
        process_uid=$(awk '/^Uid:/ {print $2}' "$pid_dir/status" 2>/dev/null)
        process_user="N/A"
        if [[ -n "$process_uid" ]]; then
            process_user=$(id -nu "$process_uid" 2>/dev/null)
            [[ -z "$process_user" ]] && process_user="$process_uid" # Fallback to UID if name not found
        fi

        # Format: "Command Line (PID: <PID>, User: <User>, EXE: /path/to/executable)"
        display_cmd="$cmd (PID: $pid, User: $process_user, EXE: $exe_path)"
    fi

    # Group commands by TTY
    if [[ -z "${tty_commands[$tty_name]}" ]]; then
        tty_commands["$tty_name"]="$display_cmd"
    else
        # Add to the list if not already present, handling hyphens safely
        if ! grep -q -Fx -- "$display_cmd" <<< "${tty_commands[$tty_name]}"; then
             tty_commands["$tty_name"]+=$'\n'"$display_cmd"
        fi
    fi
done

# Output the results
echo "---"
echo "Active TTY/PTS Sessions and their Commands:"
echo "---"

# Sort TTYs numerically for cleaner output
# Custom sort for TTYs (tty1, tty2, pts/0, pts/1...)
sorted_ttys=($(
    for tty in "${!tty_commands[@]}"; do
        if [[ "$tty" =~ ^tty([0-9]+)$ ]]; then
            echo "A:${BASH_REMATCH[1]}:${tty}"
        elif [[ "$tty" =~ ^pts/([0-9]+)$ ]]; then
            echo "B:${BASH_REMATCH[1]}:${tty}"
        else
            echo "C:0:${tty}" # Fallback for unknown formats
        fi
    done | sort -t: -k1,1 -k2,2n | cut -d: -f3
))


if [[ ${#sorted_ttys[@]} -eq 0 ]]; then
    echo "No active TTY/PTS sessions with running commands found."
else
    for tty in "${sorted_ttys[@]}"; do
        user_info=${tty_users[$tty]:-"Unknown User"}
        login_info=${tty_login_times[$tty]:-"N/A"}
        echo "## TTY/PTS: /dev/$tty"
        echo "  User: $user_info (Logged in at: $login_info)"
        echo "  Commands running:"
        while IFS= read -r cmd_detail; do
            echo "    * $cmd_detail"
        done <<< "${tty_commands[$tty]}"
        echo ""
    done
fi
echo "---"
```

## 技術的討議ポイント

### 1. プロセス識別の方法
- `/proc/[PID]/stat` の tty_nr フィールドを使用
- TTY/PTS の判定は `/proc/[PID]/fd/0` のシンボリックリンク先を確認
- 正規表現によるTTY名の抽出とカテゴリ分け

### 2. ソート機能の実装
- TTY（tty1, tty2...）とPTS（pts/0, pts/1...）の混在に対応
- カスタムソートアルゴリズムで論理的な順序を実現
- プレフィックス（A:, B:, C:）を使った3段階のソート

### 3. 重複除去の工夫
- `grep -q -Fx --` を使用してハイフンを含むコマンドに対応
- 配列への追加時の重複チェック

### 4. ユーザー情報の取得
- `who` コマンドからのログイン情報
- `/proc/[PID]/status` からの実効UID取得
- `id -nu` によるUID→ユーザー名変換

### 5. エラーハンドリング
- ファイル存在チェック（`-f`, `-L`）
- 読み取り権限の考慮
- 空値チェックとフォールバック処理

## 今後の改善案

### 1. -tree オプションの実装
- プロセス親子関係の解析機能
- ASCII artによるツリー表示
- 階層構造の視覚化

### 2. フィルタリング機能
- 特定ユーザーのプロセスのみ表示
- コマンド名による絞り込み
- システムプロセスの除外オプション

### 3. リアルタイム監視
- `watch` コマンドとの連携
- 定期実行モード
- 変更差分の強調表示

### 4. 出力フォーマットオプション
- JSON出力モード
- CSV出力モード
- カラー表示オプション

### 5. パフォーマンス最適化
- プロセス情報のキャッシング
- 並列処理の導入
- 大量プロセス環境での最適化

## 使用例

```bash
# 基本的な使用方法
./lstty.sh

# 詳細情報付きで表示
./lstty.sh -v

# ツリー形式で表示（将来の機能）
./lstty.sh -tree

# 特定ユーザーのプロセスのみ（将来の機能）
./lstty.sh -u username

# リアルタイム監視（将来の機能）
watch -n 2 ./lstty.sh
```

## ライセンス

MIT License - 詳細は LICENSE ファイルを参照
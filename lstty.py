#!/usr/bin/python3
# 機能: システム内で有効なすべてのttyとptsを抽出し、それらの端末に接続して実行
#       されているコマンドをグルーピングしてリストアップする
# 作成: 2025-07-01 k_tsuka w/ Google Gemini 2.5 Flash
# 更新: 2025-07-01 k_tsuka w/ Google Gemini 2.5 Flash

import psutil
import os
import collections
import sys
import subprocess
import re
import datetime

# --- グローバル設定 ---
SHOW_VERBOSE = False
SHOW_TREE = False

# --- TTY名を取得するヘルパー関数 ---
def get_tty_name_from_fd0(pid):
    """
    指定されたPIDのプロセスが使用するTTYの名前を/proc/<pid>/fd/0から取得します。
    """
    try:
        fd0_path = f"/proc/{pid}/fd/0"
        if not os.path.exists(fd0_path) or not os.path.islink(fd0_path):
            return None

        real_path = os.path.realpath(fd0_path)

        if real_path.startswith("/dev/tty"):
            return real_path[5:]
        elif real_path.startswith("/dev/pts/"):
            return real_path[5:]
        return None
    except Exception:
        return None

# --- プロセス情報を収集する関数 ---
def get_process_info():
    """
    全てのプロセス情報を収集し、TTYとの関連付け、親子関係をマップに格納します。
    """
    pid_parent_map = {}
    pid_tty_map = {}
    process_details = {}

    for p in psutil.process_iter(['pid', 'ppid', 'name', 'cmdline', 'username', 'terminal', 'exe']):
        try:
            pid = p.info['pid']
            ppid = p.info['ppid']
            cmdline = " ".join(p.info['cmdline']) if p.info['cmdline'] else p.info['name']
            username = p.info['username'] if p.info['username'] else "Unknown"
            exe_path = p.info['exe'] if p.info['exe'] else "N/A"

            tty_name = p.info['terminal']
            if not tty_name:
                tty_name = get_tty_name_from_fd0(pid)

            if tty_name and tty_name.startswith('/dev/'):
                tty_name = tty_name[5:]

            if tty_name:
                pid_tty_map[pid] = tty_name
                process_details[pid] = {
                    'cmdline': cmdline,
                    'user': username,
                    'pid': pid,
                    'exe_path': exe_path
                }
            pid_parent_map[pid] = ppid

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return pid_parent_map, pid_tty_map, process_details

# --- TTYごとのツリーのルートを構築する関数 ---
def build_tty_roots(pid_parent_map, pid_tty_map):
    """
    TTYごとにプロセスツリーのルートを特定し、マップに格納します。
    """
    tty_roots = collections.defaultdict(list)

    for pid, tty_name in pid_tty_map.items():
        ppid = pid_parent_map.get(pid)

        is_root_candidate = False
        if ppid is None or ppid == 0:
            is_root_candidate = True
        elif ppid == 1:
            is_root_candidate = True
        else:
            parent_tty_name = pid_tty_map.get(ppid)
            if parent_tty_name is None:
                is_root_candidate = True
            elif parent_tty_name != tty_name:
                is_root_candidate = True

        if is_root_candidate:
            tty_roots[tty_name].append(pid)

    for tty_name in tty_roots:
        tty_roots[tty_name] = sorted(list(set(tty_roots[tty_name])))

    return tty_roots

# --- プロセスツリーを表示する再帰関数 ---
# この関数はTTYフィルタリング機能を再適用し、TTY内でのツリーのみを描画します。
def print_process_sub_tree(pid, tty_name, pid_parent_map, pid_tty_map, process_details, current_indent_str="", processed=None):
    """
    再帰的にプロセスツリーを表示します。
    current_indent_str: 現在の行の先頭に付与するインデント文字列 (例: "    ├── ")
    tty_name: このツリーが属するTTYの名前。このTTYに属さないプロセスは表示しない。
    """
    if processed is None:
        processed = set()

    # 既に処理済みのPIDは表示しない
    if pid in processed:
        return

    info = process_details.get(pid)
    if not info:
        return

    # このプロセスが対象のTTYに属していない場合は表示しない
    # （ただし、呼び出し元からすでにTTYに関連するプロセスが渡されている前提）
    if pid_tty_map.get(pid) != tty_name:
        return

    processed.add(pid) # 現在のPIDを処理済みとしてマーク

    display_str = info['cmdline']
    if SHOW_VERBOSE:
        display_str = f"{info['cmdline']} (PID: {info['pid']}, User: {info['user']}, EXE: {info['exe_path']})"

    print(f"{current_indent_str}{display_str}")

    children = []
    for child_pid, ppid in pid_parent_map.items():
        # このプロセスの直接の子であり、同じTTYに属し、まだ処理されていない子プロセスを探す
        if ppid == pid and \
           pid_tty_map.get(child_pid) == tty_name and \
           child_pid not in processed:
            children.append(child_pid)

    children.sort()

    for i, child_pid in enumerate(children):
        is_last_child = (i == len(children) - 1)

        base_indent = current_indent_str
        if base_indent.endswith("└── ") or base_indent.endswith("├── "):
            base_indent = base_indent[:-4]

        next_indent_line = ""
        if current_indent_str.endswith("├── "):
            next_indent_line = base_indent + "│   "
        elif current_indent_str.endswith("└── "):
            next_indent_line = base_indent + "    "
        else: # ルートプロセスからの最初の呼び出し時
            next_indent_line = base_indent

        child_branch_prefix = "└── " if is_last_child else "├── "

        next_full_indent_str = next_indent_line + child_branch_prefix

        print_process_sub_tree(child_pid, tty_name, pid_parent_map, pid_tty_map, process_details, next_full_indent_str, processed)

# --- 'who' コマンドを実行し、その出力をパースする関数 ---
# run_who_command関数は変更なし
def run_who_command():
    """
    'who' コマンドを実行し、その出力をパースしてTTYごとのユーザーとログイン時刻を返します。
    戻り値: {tty_name: {'user': 'username', 'login_time': 'YYYY-MM-DD HH:MM', 'timestamp': float}}
    """
    login_info = {}
    try:
        result = subprocess.run(['who'], capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split('\n')

        for line in lines:
            match = re.match(r'(\S+)\s+(\S+)\s+(\d{4}-\d{2}-\d{2}|\S+\s+\d{1,2})\s+(\d{2}:\d{2})', line)
            if match:
                user = match.group(1)
                tty = match.group(2)
                date_part = match.group(3)
                time_part = match.group(4)

                login_timestamp = None
                try:
                    if re.match(r'\d{4}-\d{2}-\d{2}', date_part):
                        dt_obj = datetime.datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
                    else:
                        current_year = datetime.datetime.now().year
                        dt_obj = datetime.datetime.strptime(f"{date_part} {current_year} {time_part}", "%b %d %Y %H:%M")
                    login_timestamp = dt_obj.timestamp()
                except ValueError:
                    pass

                if tty.startswith('tty') or tty.startswith('pts/'):
                    login_info[tty] = {
                        'user': user,
                        'login_time': f"{date_part} {time_part}",
                        'timestamp': login_timestamp
                    }
            elif "system console" in line:
                continue

    except FileNotFoundError:
        print("Warning: 'who' command not found. Login information will not be available.", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Warning: 'who' command failed with error: {e.stderr.strip()}. Login information might be incomplete.", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred while running 'who': {e}", file=sys.stderr)

    return login_info

# --- TTY名を数値でソートするためのカスタムキー関数 ---
def tty_sort_key(tty_name):
    """
    ttyX または pts/Y の形式のTTY名を数値に基づいてソートするためのキーを生成します。
    tty1, tty2, ..., pts/0, pts/1, ... の順になります。
    """
    if tty_name.startswith('tty'):
        try:
            return (0, int(tty_name[3:])) # ttyはグループ0
        except ValueError:
            return (0, float('inf')) # パースできない場合は最後に
    elif tty_name.startswith('pts/'):
        try:
            return (1, int(tty_name[4:])) # ptsはグループ1
        except ValueError:
            return (1, float('inf')) # パースできない場合は最後に
    else:
        return (2, tty_name) # その他のTTYはグループ2（文字列順）

# --- メイン処理 ---
def main():
    global SHOW_VERBOSE, SHOW_TREE

    args = sys.argv[1:]
    if "-v" in args:
        SHOW_VERBOSE = True
        args.remove("-v")
    if "-tree" in args:
        SHOW_TREE = True
        args.remove("-tree")

    if args:
        print(f"Usage: python3 {sys.argv[0]} [-v] [-tree]", file=sys.stderr)
        sys.exit(1)

    print("---")
    print("TTY/PTS Sessions and their Commands:")
    print("---")

    pid_parent_map, pid_tty_map, process_details = get_process_info()
    tty_roots = build_tty_roots(pid_parent_map, pid_tty_map)
    tty_login_info = run_who_command()

    if not pid_tty_map and not tty_login_info:
        print("No active TTY/PTS sessions or login information found.")
        return

    all_ttys = set(pid_tty_map.values()) | set(tty_login_info.keys())
    # TTY名をカスタムキーでソート
    sorted_ttys = sorted(list(all_ttys), key=tty_sort_key)

    for tty_name in sorted_ttys:
        login_detail = tty_login_info.get(tty_name, {'user': 'Unknown User', 'login_time': 'N/A', 'timestamp': None})
        user_info = login_detail['user']
        login_time_info = login_detail['login_time']

        print(f"\n## TTY/PTS: /dev/{tty_name}")
        print(f"  User: {user_info} (Logged in at: {login_time_info})")

        if SHOW_TREE:
            print("  Process Tree:")
            processed_pids_for_tty = set()

            # このTTYのルートプロセスを取得し、ソート
            current_tty_roots = sorted(list(set(tty_roots[tty_name])))

            if not current_tty_roots:
                print("    No active process roots found for this TTY.")

            for root_pid in current_tty_roots:
                # このルートPIDがまだ処理されていない場合のみツリーを開始
                if root_pid not in processed_pids_for_tty and pid_tty_map.get(root_pid) == tty_name:
                    # print_process_sub_tree は、指定されたTTYに属するプロセスのみを表示します
                    print_process_sub_tree(root_pid, tty_name, pid_parent_map, pid_tty_map, process_details, "    ", processed_pids_for_tty)
        else: # SHOW_TREEがFalseの場合の通常表示
            print("  Commands running:")
            tty_processes = []
            for pid, tty in pid_tty_map.items():
                if tty == tty_name:
                    tty_processes.append(pid)

            tty_processes.sort()

            displayed_commands = set()
            for pid in tty_processes:
                info = process_details.get(pid)
                if info:
                    display_str = info['cmdline']
                    if SHOW_VERBOSE:
                        display_str = f"{info['cmdline']} (PID: {info['pid']}, User: {info['user']}, EXE: {info['exe_path']})"

                    if display_str not in displayed_commands:
                        print(f"    * {display_str}")
                        displayed_commands.add(display_str)

    print("\n---")

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("Warning: This script should ideally be run with root privileges (e.g., sudo) to access all process information AND login details.")
        print("         Some process details, TTY associations, or login information might be incomplete without it.\n")
    main()


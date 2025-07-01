#!/usr/bin/python3
# 機能: システム内で有効なすべてのttyとptsを抽出し、それらの端末に接続して実行
#       されているコマンドをグルーピングしてリストアップする
# 作成: 2025-07-01 k_tsuka /w Google Gemini 2.5 Flash
# 更新: 2025-07-01 k_tsuka /w Google Gemini 2.5 Flash

import psutil
import os
import collections
import sys

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
def print_tree(pid, tty_name, pid_parent_map, pid_tty_map, process_details, current_indent_str="", processed=None):
    """
    再帰的にプロセスツリーを表示します。
    current_indent_str: 現在の行の先頭に付与するインデント文字列 (例: "    ├── ")
    """
    if processed is None:
        processed = set()

    if pid in processed:
        return
    
    info = process_details.get(pid)
    if not info:
        return

    processed.add(pid)

    display_str = info['cmdline']
    if SHOW_VERBOSE:
        display_str = f"{info['cmdline']} (PID: {info['pid']}, User: {info['user']}, EXE: {info['exe_path']})"
    
    # ここで現在のプロセスを出力
    print(f"{current_indent_str}{display_str}")

    children = []
    for child_pid, ppid in pid_parent_map.items():
        if ppid == pid and \
           pid_tty_map.get(child_pid) == tty_name and \
           child_pid not in processed:
            children.append(child_pid)
    
    children.sort()

    for i, child_pid in enumerate(children):
        is_last_child = (i == len(children) - 1)
        
        # 次のレベルのインデントとプレフィックスを構築
        # 親のインデント文字列から「枝」部分を取り除いたものに、新しいレベルの縦線/空白を追加
        # root呼び出しの初期インデントは "    " なので、それを考慮
        base_indent = current_indent_str
        if base_indent.endswith("└── ") or base_indent.endswith("├── "):
            base_indent = base_indent[:-4] # "├── " または "└── " を削除
        
        # 次の行のインデント部分 (縦線または空白)
        next_indent_line = ""
        if current_indent_str.endswith("├── "): # 親が枝あり
            next_indent_line = base_indent + "│   "
        elif current_indent_str.endswith("└── "): # 親が最後の枝
            next_indent_line = base_indent + "    "
        else: # ルートプロセスからの最初の呼び出し時
            next_indent_line = base_indent # "    " のまま
        
        # 新しい子プロセス自身のプレフィックス
        child_branch_prefix = "└── " if is_last_child else "├── "
        
        # 次の再帰呼び出しに渡す完全なインデント文字列
        next_full_indent_str = next_indent_line + child_branch_prefix
        
        print_tree(child_pid, tty_name, pid_parent_map, pid_tty_map, process_details, next_full_indent_str, processed)


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

    if not pid_tty_map:
        print("No active TTY/PTS sessions with running commands found.")
        return

    sorted_ttys = sorted(list(set(pid_tty_map.values())))

    for tty_name in sorted_ttys:
        print(f"\n## TTY/PTS: /dev/{tty_name}")

        if SHOW_TREE:
            print("  Process Tree:")
            processed_pids_for_tty = set() 
            
            current_tty_roots = sorted(list(set(tty_roots[tty_name])))

            for root_pid in current_tty_roots:
                if root_pid not in processed_pids_for_tty and pid_tty_map.get(root_pid) == tty_name:
                    # ルートプロセスは、最初のインデントとして"    "を渡す
                    # print_tree関数が受け取るcurrent_indent_strは、その行全体のインデントとプレフィックス
                    print_tree(root_pid, tty_name, pid_parent_map, pid_tty_map, process_details, "    ", processed_pids_for_tty)
        else:
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
        print("Warning: This script should ideally be run with root privileges (e.g., sudo) to access all process information.")
        print("         Some process details or TTY associations might be incomplete without it.\n")
    main()

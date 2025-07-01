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

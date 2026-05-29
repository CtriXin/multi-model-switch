#!/bin/bash
input=$(cat)

_jq() { echo "$input" | jq -r "$1" 2>/dev/null; }

model=$(_jq '.model.display_name // "Sonnet"')
cwd=$(_jq '.workspace.current_dir // .cwd // "-"')
pct=$(_jq '.context_window.used_percentage // 0')
cost=$(_jq '.cost.total_cost_usd // 0')
duration_ms=$(_jq '.cost.total_duration_ms // 0')
ctx_in=$(_jq '.context_window.total_input_tokens // 0')
ctx_out=$(_jq '.context_window.total_output_tokens // 0')
ctx_max=$(_jq '.context_window.context_window_size // 200000')

[ -z "$pct" ]         || [ "$pct" = "null" ]         && pct=0
[ -z "$cost" ]        || [ "$cost" = "null" ]        && cost=0
[ -z "$duration_ms" ] || [ "$duration_ms" = "null" ] && duration_ms=0
[ -z "$ctx_in" ]      || [ "$ctx_in" = "null" ]      && ctx_in=0
[ -z "$ctx_out" ]     || [ "$ctx_out" = "null" ]     && ctx_out=0
[ -z "$ctx_max" ]     || [ "$ctx_max" = "null" ]     && ctx_max=200000

if [ -n "$CLAUDE_CODE_AUTO_COMPACT_WINDOW" ] && [ "$CLAUDE_CODE_AUTO_COMPACT_WINDOW" -gt 0 ] 2>/dev/null; then
    ctx_max="$CLAUDE_CODE_AUTO_COMPACT_WINDOW"
fi

COLS=$(tput cols 2>/dev/null || echo 100)
model_short=$(echo "$model" | sed 's/ (.*//')

mms_config_root() {
    if [ -n "$MMS_CONFIG_ROOT" ]; then
        echo "$MMS_CONFIG_ROOT"
        return
    fi
    if [ -n "$MMS_CONFIG_DIR" ]; then
        echo "$MMS_CONFIG_DIR"
        return
    fi
    if [ -n "$XDG_CONFIG_HOME" ]; then
        if [[ "$XDG_CONFIG_HOME" == *"/.config/mms/claude-gateway/"* ]]; then
            echo "${XDG_CONFIG_HOME%%/.config/mms/claude-gateway/*}/.config/mms"
            return
        fi
        if [[ "$XDG_CONFIG_HOME" == *"/.config/mms/codex-gateway/"* ]]; then
            echo "${XDG_CONFIG_HOME%%/.config/mms/codex-gateway/*}/.config/mms"
            return
        fi
        echo "$XDG_CONFIG_HOME/mms"
        return
    fi
    local user_home="$HOME"
    if [[ "$HOME" == *"/.config/mms/claude-gateway/"* ]]; then
        user_home="${HOME%%/.config/mms/claude-gateway/*}"
    fi
    echo "$user_home/.config/mms"
}

pick_route_status_file() {
    local config_root
    config_root="$(mms_config_root)"
    local is_gateway_session=0
    if [[ "$HOME" == *"/.config/mms/claude-gateway/"* ]]; then
        is_gateway_session=1
    fi

    local primary_user="$config_root/route_status.json"
    local primary_home="$HOME/.config/mms/route_status.json"
    local gateway_sessions="$config_root/claude-gateway/s"
    local explicit_config_root=0
    if [ -n "$MMS_CONFIG_ROOT" ] || [ -n "$MMS_CONFIG_DIR" ]; then
        explicit_config_root=1
    fi
    local now
    now=$(date +%s)

    if [ "$is_gateway_session" -eq 1 ]; then
        if [ "$explicit_config_root" -eq 1 ] && [ -f "$primary_user" ]; then
            local mt age
            mt=$(stat -f %m "$primary_user" 2>/dev/null || echo 0)
            age=$(( now - mt ))
            [ "$age" -lt 600 ] && { echo "$primary_user"; return; }
        fi
        if [ -f "$primary_home" ]; then
            local mt age
            mt=$(stat -f %m "$primary_home" 2>/dev/null || echo 0)
            age=$(( now - mt ))
            [ "$age" -lt 600 ] && { echo "$primary_home"; return; }
        fi
        if [ "$explicit_config_root" -ne 1 ] && [ -f "$primary_user" ]; then
            local mt age
            mt=$(stat -f %m "$primary_user" 2>/dev/null || echo 0)
            age=$(( now - mt ))
            [ "$age" -lt 600 ] && { echo "$primary_user"; return; }
        fi
    else
        if [ -f "$primary_user" ]; then
            local mt age
            mt=$(stat -f %m "$primary_user" 2>/dev/null || echo 0)
            age=$(( now - mt ))
            [ "$age" -lt 600 ] && { echo "$primary_user"; return; }
        fi
        if [ -f "$primary_home" ]; then
            local mt age
            mt=$(stat -f %m "$primary_home" 2>/dev/null || echo 0)
            age=$(( now - mt ))
            [ "$age" -lt 600 ] && { echo "$primary_home"; return; }
        fi
    fi

    local best_path=""
    local best_mtime=0

    for p in "$primary_user" "$primary_home"; do
        if [ -f "$p" ]; then
            local mt
            mt=$(stat -f %m "$p" 2>/dev/null || echo 0)
            if [ "$mt" -gt "$best_mtime" ]; then
                best_mtime="$mt"
                best_path="$p"
            fi
        fi
    done

    if [ -d "$gateway_sessions" ]; then
        while IFS= read -r p; do
            local mt
            mt=$(stat -f %m "$p" 2>/dev/null || echo 0)
            if [ "$mt" -gt "$best_mtime" ]; then
                best_mtime="$mt"
                best_path="$p"
            fi
        done < <(find "$gateway_sessions" -maxdepth 5 -type f -name route_status.json 2>/dev/null)
    fi

    [ -n "$best_path" ] && echo "$best_path"
}

_ROUTE_STATUS="$(pick_route_status_file)"
route_tag=""
if [[ "$HOME" == *"/.config/mms/claude-gateway/"* ]] && [ -n "$_ROUTE_STATUS" ] && [ -f "$_ROUTE_STATUS" ]; then
    route_age=$(( $(date +%s) - $(stat -f %m "$_ROUTE_STATUS" 2>/dev/null || echo 0) ))
    if [ "$route_age" -lt 600 ]; then
        r_tier=$(jq -r '.tier // empty' "$_ROUTE_STATUS" 2>/dev/null)
        r_model=$(jq -r '.model // empty' "$_ROUTE_STATUS" 2>/dev/null)
        if [ -n "$r_model" ]; then
            r_model_short=$(echo "$r_model" | sed 's/^claude-//;s/-[0-9]*-[0-9]*$//;s/-[0-9]*$//')
            case "$r_tier" in
                heavy)  route_tag="▲ ${r_model_short}" ;;
                medium) route_tag="● ${r_model_short}" ;;
                light)  route_tag="▼ ${r_model_short}" ;;
                *)      route_tag="→ ${r_model_short}" ;;
            esac
            model_short="${route_tag}"
        fi
    fi
fi

# ── health indicator ──
health_icon=""
_HEALTH_CACHE="$(mms_config_root)/health-cache.json"
if [ -f "$_HEALTH_CACHE" ]; then
    h_age=$(( $(date +%s) - $(stat -f %m "$_HEALTH_CACHE" 2>/dev/null || echo 0) ))
    if [ "$h_age" -lt 120 ]; then
        _h_model="${r_model:-$model_short}"
        _h_status=$(jq -r --arg m "$_h_model" '.records[$m].status // empty' "$_HEALTH_CACHE" 2>/dev/null)
        case "$_h_status" in
            ok)       health_icon=" ●" ;;
            slow)     health_icon=" ◐" ;;
            degraded) health_icon=" ◑" ;;
            blocked)  health_icon=" ○" ;;
        esac
    fi
fi
model_short="${model_short}${health_icon}"

project=$(basename "$cwd" 2>/dev/null || echo "-")

git_branch="-"
if [ -n "$cwd" ] && [ -d "$cwd" ]; then
    b=$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null || echo "-")
    if [ "$COLS" -lt 100 ] && [ ${#b} -gt 15 ]; then
        git_branch="${b:0:15}…"
    else
        git_branch="$b"
    fi
fi

s_add=$(_jq '.cost.total_lines_added // 0')
s_del=$(_jq '.cost.total_lines_removed // 0')
[ -z "$s_add" ] || [ "$s_add" = "null" ] && s_add=0
[ -z "$s_del" ] || [ "$s_del" = "null" ] && s_del=0
session_diff=""
if [ "$s_add" -gt 0 ] || [ "$s_del" -gt 0 ]; then
    session_diff=$(printf " ${GREEN}+%d${RESET}/${RED}-%d${RESET}" "$s_add" "$s_del")
fi

GIT_DIFF_CACHE="${TMPDIR}claude-statusline-gitdiff"
git_diff_info=""
if [ -n "$cwd" ] && [ -d "$cwd" ]; then
    now_s=$(date +%s)
    cache_mt=$(stat -f %m "$GIT_DIFF_CACHE" 2>/dev/null || echo 0)
    if [ $(( now_s - cache_mt )) -gt 5 ]; then
        stat_line=$(git -C "$cwd" diff --stat 2>/dev/null | tail -1)
        echo "$stat_line" > "$GIT_DIFF_CACHE"
    fi
    stat_line=$(cat "$GIT_DIFF_CACHE" 2>/dev/null)
    if [ -n "$stat_line" ]; then
        files_changed=$(echo "$stat_line" | grep -oE '[0-9]+ file' | grep -oE '[0-9]+')
        insertions=$(echo "$stat_line" | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+')
        deletions=$(echo "$stat_line" | grep -oE '[0-9]+ deletion' | grep -oE '[0-9]+')
        if [ -n "$files_changed" ]; then
            git_diff_info=$(printf " Δ%sf ${GREEN}+%s${RESET}/${RED}-%s${RESET}" \
                "${files_changed}" "${insertions:-0}" "${deletions:-0}")
        fi
    fi
fi

mem_info=""
total_pages=$(sysctl -n hw.memsize 2>/dev/null | awk '{print int($1/16384)}')
page_size=16384
if [ -n "$total_pages" ]; then
    free_p=$(vm_stat 2>/dev/null | awk '/Pages free/{gsub(/\./,"",$3); print $3+0}')
    inact_p=$(vm_stat 2>/dev/null | awk '/Pages inactive/{gsub(/\./,"",$3); print $3+0}')
    used_gb=$(( (total_pages - ${free_p:-0} - ${inact_p:-0}) * page_size / 1024 / 1024 / 1024 ))
    total_gb=$(( total_pages * page_size / 1024 / 1024 / 1024 ))
    mem_info="  ${DIM}${used_gb}G/${total_gb}G${RESET}"
fi

cost_fmt=$(printf "%.2f" "$cost" 2>/dev/null || echo "$cost")
cin_k=$((ctx_in / 1000))
cout_k=$((ctx_out / 1000))
ctx_total_k=$(((ctx_in + ctx_out) / 1000))

if [ "$ctx_max" -ge 1000000 ]; then
    ctx_max_fmt="$(( ctx_max / 1000000 ))M"
else
    ctx_max_fmt="$((ctx_max / 1000))k"
fi

if   [ "$COLS" -ge 160 ]; then bar_len=28
elif [ "$COLS" -ge 120 ]; then bar_len=22
elif [ "$COLS" -ge 80 ];  then bar_len=18
else                           bar_len=14
fi
filled=$((pct * bar_len / 100))
[ "$filled" -gt "$bar_len" ] && filled=$bar_len
empty=$((bar_len - filled))
bar=""
for ((i=0; i<filled; i++)); do bar="${bar}█"; done
for ((i=0; i<empty; i++)); do bar="${bar}░"; done

RESET=$'\033[0m'
BOLD=$'\033[1m'
DIM=$'\033[2m'
RED=$'\033[31m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
CYAN=$'\033[36m'
ORANGE=$'\033[38;5;208m'
PURPLE=$'\033[38;5;141m'
TEAL=$'\033[38;5;80m'

if [ -n "$route_tag" ]; then
    case "$route_tag" in
        ▼*)  MODEL_C="${BOLD}${GREEN}"  ;;
        ●*)  MODEL_C="${BOLD}${YELLOW}" ;;
        ▲*)  MODEL_C="${BOLD}${PURPLE}" ;;
        *)
              case "$route_tag" in
                  *opus*)   MODEL_C="${BOLD}${PURPLE}" ;;
                  *sonnet*) MODEL_C="${BOLD}${TEAL}"   ;;
                  *haiku*)  MODEL_C="${BOLD}${GREEN}"  ;;
                  *gpt*)    MODEL_C="${BOLD}${CYAN}"   ;;
                  *kimi*)   MODEL_C="${BOLD}${YELLOW}" ;;
                  *)        MODEL_C="${BOLD}${CYAN}"   ;;
              esac ;;
    esac
else
    case "$model_short" in
        *Opus*)   MODEL_C="${BOLD}${PURPLE}" ;;
        *Sonnet*) MODEL_C="${BOLD}${TEAL}"   ;;
        *Haiku*)  MODEL_C="${BOLD}${GREEN}"  ;;
        *)        MODEL_C="${BOLD}${CYAN}"   ;;
    esac
fi

if   [ "$pct" -ge 80 ]; then BAR_C="${RED}"
elif [ "$pct" -ge 50 ]; then BAR_C="${YELLOW}"
else                         BAR_C="${GREEN}"
fi

USAGE_CACHE="${TMPDIR}claude-usage-cache.json"
USAGE_LOCK="${TMPDIR}claude-usage-cache.lock"

_refresh_usage_bg() {
    if [ -f "$USAGE_LOCK" ]; then
        lock_age=$(( $(date +%s) - $(stat -f %m "$USAGE_LOCK" 2>/dev/null || echo 0) ))
        [ "$lock_age" -lt 30 ] && return
        rm -f "$USAGE_LOCK"
    fi
    (
        touch "$USAGE_LOCK"
        token=""
        if [ "${MMS_STATUSLINE_KEYCHAIN_USAGE:-0}" = "1" ]; then
            token=$(security find-generic-password -s "Claude" -a "accessToken" -w 2>/dev/null)
        fi
        if [ -n "$token" ]; then
            curl -s --connect-timeout 2 --max-time 5 \
                -H "Authorization: Bearer $token" \
                -H "anthropic-beta: oauth-2025-04-20" \
                "https://api.anthropic.com/api/oauth/usage" > "$USAGE_CACHE.tmp" 2>/dev/null \
                && mv -f "$USAGE_CACHE.tmp" "$USAGE_CACHE"
        fi
        rm -f "$USAGE_LOCK"
    ) &
}

fmt_resets() {
    local iso="$1"
    [ -z "$iso" ] || [ "$iso" = "null" ] && echo "" && return
    local stripped=$(echo "$iso" | sed 's/\.[0-9]*//;s/[+-][0-9][0-9]:[0-9][0-9]$//;s/Z$//')
    local reset_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S" "$stripped" "+%s" 2>/dev/null)
    [ -z "$reset_epoch" ] && echo "" && return
    local now=$(date +%s)
    local diff=$(( reset_epoch - now ))
    if [ "$diff" -le 0 ]; then
        echo "now"
    else
        local h=$(( diff / 3600 ))
        local m=$(( (diff % 3600) / 60 ))
        echo "${h}h${m}m"
    fi
}

usage_info=""
if [ -f "$USAGE_CACHE" ]; then
    cache_age=$(( $(date +%s) - $(stat -f %m "$USAGE_CACHE" 2>/dev/null || echo 0) ))
    if [ "$cache_age" -lt 600 ]; then
        u_raw=$(jq -r '.five_hour.utilization // empty' "$USAGE_CACHE" 2>/dev/null)
        u_reset=$(jq -r '.five_hour.resets_at // empty' "$USAGE_CACHE" 2>/dev/null)
        if [ -n "$u_raw" ]; then
            u_pct=$(awk "BEGIN{printf \"%d\", $u_raw * 100}")
            u_filled=$((u_pct * 10 / 100))
            [ "$u_filled" -gt 10 ] && u_filled=10
            u_empty=$((10 - u_filled))
            u_bar=""
            for ((i=0; i<u_filled; i++)); do u_bar="${u_bar}█"; done
            for ((i=0; i<u_empty; i++)); do u_bar="${u_bar}░"; done
            if   [ "$u_pct" -ge 80 ]; then U_C="${RED}"
            elif [ "$u_pct" -ge 50 ]; then U_C="${YELLOW}"
            else                            U_C="${GREEN}"
            fi
            resets_fmt=$(fmt_resets "$u_reset")
            resets_part=""
            [ -n "$resets_fmt" ] && resets_part=" ↻${resets_fmt}"
            usage_info=$(printf "  ${U_C}%s${RESET} %d%%%s" "$u_bar" "$u_pct" "$resets_part")
        fi
    fi
    [ "$cache_age" -ge 60 ] && _refresh_usage_bg
else
    _refresh_usage_bg
fi

l1_model=$(printf "${MODEL_C}[%s]${RESET}" "$model_short")
l1_branch=$(printf "${GREEN}%s${RESET}" "$git_branch")
l1_tokens=$(printf "${DIM}↑%dk ↓%dk${RESET}" "$cin_k" "$cout_k")

if [ "$COLS" -ge 100 ]; then
    printf "%s  %s%s%s  %s\n" "$l1_model" "$l1_branch" "$git_diff_info" "$session_diff" "$l1_tokens"
elif [ "$COLS" -ge 70 ]; then
    printf "%s  %s%s  %s\n" "$l1_model" "$l1_branch" "$git_diff_info" "$l1_tokens"
else
    printf "%s  %s\n" "$l1_model" "$l1_tokens"
fi

l2_bar=$(printf "${BAR_C}%s${RESET} %d%% ${DIM}%dk/%s${RESET}" "$bar" "$pct" "$ctx_total_k" "$ctx_max_fmt")
l2_cost=$(printf "${ORANGE}\$%s${RESET}" "$cost_fmt")
l2_project=$(printf "${CYAN}%s${RESET}" "$project")

if [ "$COLS" -ge 120 ]; then
    printf "%s  %s  %s%s%s\n" "$l2_bar" "$l2_cost" "$l2_project" "$mem_info" "$usage_info"
elif [ "$COLS" -ge 70 ]; then
    printf "%s  %s  %s%s\n" "$l2_bar" "$l2_cost" "$l2_project" "$usage_info"
else
    printf "%s  %s%s\n" "$l2_bar" "$l2_cost" "$usage_info"
fi

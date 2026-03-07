#!/usr/bin/env zsh
# ai-complete.zsh — AI-powered zsh command completion using Claude CLI
# https://github.com/ramanshrivastava/build-ai-agents
#
# Source this file in your .zshrc:
#   source /path/to/ai-complete.zsh

# ── Configuration (override via environment variables) ──────────────
# Model to use for completions (default: opus)
: ${AI_COMPLETE_MODEL:=opus}
# Keybinding to trigger AI completion (default: Ctrl+G)
: ${AI_COMPLETE_KEYBIND:='^g'}
# Log file path (set to "" to disable logging)
: ${AI_COMPLETE_LOG:=$HOME/.ai-complete.log}
# Max turns for agent tool use (default: 200)
: ${AI_COMPLETE_MAX_TURNS:=200}
# Spinner color — Catppuccin Mocha Mauve by default
: ${AI_COMPLETE_SPINNER_COLOR:='#cba6f7'}

# ── Guard: require claude CLI ───────────────────────────────────────
if ! command -v claude &>/dev/null; then
    echo "[ai-complete] Warning: 'claude' CLI not found in PATH. AI completion disabled." >&2
    echo "[ai-complete] Install: https://docs.anthropic.com/en/docs/claude-cli" >&2
    return 0
fi

# ── Exit code capture ──────────────────────────────────────────────
# ZLE widgets can't see $? — it's already 0 by then.
# Capture it in precmd before the prompt resets it.
__ai_last_exit_code_val=0
__ai_capture_exit() { __ai_last_exit_code_val=$?; }
precmd_functions+=(__ai_capture_exit)
__ai_last_exit_code() { echo $__ai_last_exit_code_val; }

# ── Main widget ────────────────────────────────────────────────────
_ai_complete() {
    # Skip if buffer is empty
    [[ -z "$BUFFER" ]] && return

    # Suppress job control notifications inside the widget
    setopt LOCAL_OPTIONS NO_MONITOR NO_NOTIFY

    local original_buffer="$BUFFER"

    # ── Gather local context (fast, truncated to keep tokens low) ──
    local dir_listing git_branch project_files pane_history recent_cmds
    dir_listing=$(ls -1 2>/dev/null | head -30)
    git_branch=$(git branch --show-current 2>/dev/null)
    project_files=""
    [[ -f package.json ]] && project_files+="package.json "
    [[ -f pyproject.toml ]] && project_files+="pyproject.toml "
    [[ -f Makefile ]] && project_files+="Makefile "
    [[ -f Cargo.toml ]] && project_files+="Cargo.toml "
    [[ -f docker-compose.yml ]] && project_files+="docker-compose.yml "
    [[ -f go.mod ]] && project_files+="go.mod "

    # ── Tmux pane output + last failed command detection ───────────
    local last_failed_info=""
    if [[ -n "$TMUX" ]]; then
        pane_history=$(tmux capture-pane -p -S -50 2>/dev/null | tail -40)
        local last_exit=$(__ai_last_exit_code)
        if [[ "$last_exit" -ne 0 ]]; then
            last_failed_info="LAST COMMAND FAILED (exit $last_exit): $(fc -l -n -1)"
        fi
    fi
    # Recent zsh commands (structured history)
    recent_cmds=$(fc -l -n -10 2>/dev/null)

    # ── Build failure-aware prompt section ─────────────────────────
    local failure_block=""
    if [[ -n "$last_failed_info" ]]; then
        failure_block="
FAILURE CONTEXT:
$last_failed_info
The above command ALREADY FAILED. Do NOT suggest it again. Instead, suggest a command that:
- Fixes the root cause (e.g., start a service, install a dependency, fix a path)
- Diagnoses the problem (e.g., check status, read logs, verify config)
- Takes an alternative approach to achieve the same goal
"
    fi

    local context="Working directory: $(pwd)
Shell: zsh
Git branch: ${git_branch:-not a git repo}
Project files: ${project_files:-none detected}
Directory contents:
$dir_listing

Recent commands (oldest to newest):
${recent_cmds:-none}

Terminal output (last ~40 lines, includes command output and errors):
${pane_history:-not in tmux}"

    local suggestion stderr_file=$(mktemp) stream_file=$(mktemp)

    # ── Run Claude in background with stream-json ──────────────────
    # --output-format stream-json gives structured JSON per line,
    # including tool_use/tool_result blocks for spinner labels
    claude -p --model "$AI_COMPLETE_MODEL" --max-turns "$AI_COMPLETE_MAX_TURNS" \
        --output-format stream-json --verbose \
        --permission-mode bypassPermissions \
        "You are an expert zsh command synthesizer. Given a partial command, repo context, and terminal history, return a single powerful command.

PHILOSOPHY:
- Simple completions (cd, git push, ls) are what tab-complete is for. You exist to generate commands the user COULDN'T easily type themselves.
- Aim for complex, precise, multi-step commands: pipelines, jq transforms, awk one-liners, find+exec chains, xargs parallelism, curl+jq combos, git log with custom formats, docker/kubectl queries, sed transforms, etc.
- Think of yourself as a 10x senior engineer's muscle memory — produce the exact incantation that would take 5 minutes to look up.
- Surface the flags and options people KNOW exist but can never remember: rsync's --dry-run --itemize-changes, tar's --strip-components, git log's --format=%H, find's -newer, curl's -w '%{http_code}', grep's -P for PCRE, etc.

RULES:
- Return ONLY the command — no explanation, no markdown, no backticks.
- NEVER suggest a command that already failed in the terminal output. If a command failed, suggest a DIFFERENT approach that solves the same problem or diagnoses the failure.
- If the user's input relates to a recent error, suggest a command that fixes or investigates that error.
- When the input is vague or a bare tool name, generate the MOST USEFUL complex command for the current context, not the simplest completion. E.g., 'git' in a dirty repo → a git diff --stat or git log --oneline --graph, not just 'git status'.
- Fix typos in the input (e.g., gti → git).
- Prefer project-specific tools (uv over pip if pyproject.toml, npm if package.json).
- Use the recent command history to understand workflow context and intent.
- Prefer one-liners that chain tools with pipes over multiple sequential commands.
- Use advanced flags you've verified with --help — the obscure ones users forget: --format/--template for structured output, --filter/--query for server-side filtering, -o json | jq for machine-readable pipelines, --dry-run for safe previews, --exclude/--include for precise targeting.

TOOLS (MANDATORY):
- You MUST use at least one tool before returning your answer. Do NOT answer from memory alone.
- ALWAYS run \`man <command>\` or \`<command> --help\` via Bash to verify correct syntax and flags.
- If the command involves an API, URL, or error you're unsure about, use WebSearch to confirm.
- Read project files (package.json, Makefile, etc.) with Read if you need project-specific details.
- After verifying with tools, return ONLY the final command — no explanation.
$failure_block
CONTEXT:
$context

COMMAND: $original_buffer" >"$stream_file" 2>"$stderr_file" &
    local claude_pid=$!

    # ── Ctrl+C cleanup ────────────────────────────────────────────
    trap "kill $claude_pid 2>/dev/null; wait $claude_pid 2>/dev/null; rm -f ${(q)stream_file} ${(q)stderr_file}; BUFFER=${(q)original_buffer}; CURSOR=${#original_buffer}; zle redisplay; trap - INT; return" INT

    # ── Animated braille spinner ───────────────────────────────────
    local spinner_frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
    local frame_idx=0
    local tool_label="Raman-ating"
    local idle_names=("Raman-ating" "Nikki-ating")
    local has_tool=0

    local highlight_start=$((${#original_buffer} + 2))  # after "  " gap

    while kill -0 "$claude_pid" 2>/dev/null; do
        local frame=${spinner_frames[$((frame_idx % ${#spinner_frames[@]} + 1))]}

        # Every 3rd frame (~0.3s), parse latest tool_use event from stream
        if (( frame_idx % 3 == 0 )); then
            if (( !has_tool )); then
                # Alternate between idle names every 3 frames
                tool_label="${idle_names[$((frame_idx / 3 % 2 + 1))]}"
            fi
            local latest_tool_line=$(grep '"tool_use"' "$stream_file" 2>/dev/null | tail -1)
            if [[ -n "$latest_tool_line" ]]; then
                has_tool=1
                local tname=$(echo "$latest_tool_line" | grep -o '"name":"[^"]*"' | head -1 | sed 's/"name":"//;s/"//')
                # Extract first param value from input
                local first_val=$(echo "$latest_tool_line" | sed 's/.*"input":{//' | grep -o ':"[^"]*"' | head -1 | sed 's/^:"//;s/"$//')
                if [[ -n "$first_val" ]]; then
                    tool_label="$tname ${first_val:0:50}"
                else
                    tool_label="$tname"
                fi
            fi
        fi

        BUFFER="$original_buffer  $frame $tool_label…"
        CURSOR=${#BUFFER}
        region_highlight=("$highlight_start ${#BUFFER} fg=$AI_COMPLETE_SPINNER_COLOR")
        zle -R
        frame_idx=$((frame_idx + 1))
        sleep 0.1
    done
    region_highlight=()
    wait "$claude_pid"
    trap - INT

    # ── Parse stream-json: extract final command suggestion ────────
    # Stream format (one JSON per line):
    # {"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}}
    suggestion=$(command grep '"type"' "$stream_file" \
        | jq -rR 'try (fromjson | select(.type=="assistant") | .message.content[] | select(.type=="text") | .text)' 2>/dev/null \
        | tail -1)

    # ── Log the session ────────────────────────────────────────────
    if [[ -n "$AI_COMPLETE_LOG" ]]; then
        {
            echo ""
            echo "── $(date '+%Y-%m-%d %H:%M:%S') ──────────────────"
            echo "input: $original_buffer"
            echo "cwd:   $(pwd)"
            [[ -n "$last_failed_info" ]] && echo "failure: $last_failed_info"
            if [[ -s "$stream_file" ]]; then
                echo "--- stream-json (tool calls + messages) ---"
                cat "$stream_file"
                echo "--- end stream ---"
            fi
            if [[ -s "$stderr_file" ]]; then
                echo "--- stderr ---"
                cat "$stderr_file"
                echo "--- end stderr ---"
            fi
            echo "result: ${suggestion:-<empty>}"
        } >> "$AI_COMPLETE_LOG" 2>/dev/null
    fi

    # ── Apply suggestion or show error ─────────────────────────────
    if [[ -n "$suggestion" ]]; then
        BUFFER="$suggestion"
        CURSOR=${#BUFFER}
    else
        BUFFER="$original_buffer"
        CURSOR=${#BUFFER}
        local err=$(<"$stderr_file")
        [[ -z "$err" ]] && err="no result (check ai-log for stream-json details)"
        zle -M "ai-complete error: ${err:0:120}"
    fi
    rm -f "$stream_file" "$stderr_file"
    zle redisplay
}

# ── Register widget + keybinding ───────────────────────────────────
zle -N _ai_complete
bindkey "$AI_COMPLETE_KEYBIND" _ai_complete

# ── Convenience aliases ────────────────────────────────────────────
if [[ -n "$AI_COMPLETE_LOG" ]]; then
    alias ai-log="cat $AI_COMPLETE_LOG"
    alias ai-log-tail="tail -30 $AI_COMPLETE_LOG"
fi

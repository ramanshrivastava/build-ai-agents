# zsh-ai-complete

AI-powered command completion for zsh using Claude CLI. Type a partial command **or plain English description**, press `Ctrl+G`, and get back the exact incantation a senior engineer would type.

<!-- TODO: Add demo GIF -->

## How It Works

1. You type a partial command (e.g., `git`, `find`, `docker`) and press `Ctrl+G`
2. The widget gathers context: CWD, git branch, project files, tmux terminal output, recent commands, and the last command's exit code
3. It calls Claude CLI with `--output-format stream-json`, streaming structured JSON in the background
4. An animated braille spinner shows live tool-call labels (e.g., `Bash man git`, `Read package.json`) while Claude works
5. The final command replaces your buffer — review it, then press Enter to run

If the last command failed, the prompt tells Claude to suggest a *fix or diagnostic*, not repeat the failed command.

## Prerequisites

- [Claude CLI](https://docs.anthropic.com/en/docs/claude-cli) installed and authenticated (`claude` in PATH)
- `jq` for JSON parsing (`brew install jq` / `apt install jq`)
- zsh (tested on 5.9+)
- Optional: tmux (enables terminal output context and failure detection)

## Install

```bash
# Clone the repo (or just this directory)
git clone https://github.com/raman-at-pieces/build-ai-agents-rag.git

# Add to your .zshrc
echo 'source /path/to/build-ai-agents-rag/zsh-ai-complete/ai-complete.zsh' >> ~/.zshrc

# Reload
source ~/.zshrc
```

Or copy `ai-complete.zsh` directly into your dotfiles and source it.

## Usage

1. Type a partial command **or natural language description**
2. Press `Ctrl+G`
3. Watch the spinner while Claude verifies flags with `--help` and reads project files
4. The completed command appears in your buffer
5. Press `Enter` to execute, or edit further

### Examples

| You type | Claude returns |
|----------|---------------|
| `git` | `git log --oneline --graph --decorate -20` (context-aware) |
| `find all large files` | `find . -type f -size +100M -exec ls -lh {} \;` |
| `what ports are in use` | `lsof -iTCP -sTCP:LISTEN -nP \| awk '{print $1, $9}'` |
| `docker` | `docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'` |
| `deploy this` | `git push origin feat/my-branch` (reads git context) |

Works best when:
- You know *what* you want but not the exact flags (`rsync`, `find`, `awk`)
- You describe what you want in plain English and let Claude figure out the command
- A command just failed and you want Claude to suggest a fix
- You want a complex pipeline (`curl | jq`, `git log --format`, `find -exec`)

## Configuration

All config is via environment variables with sensible defaults. Set them before sourcing:

```bash
# In .zshrc, before the source line:
export AI_COMPLETE_MODEL=sonnet          # Default: opus
export AI_COMPLETE_KEYBIND='^x^g'        # Default: ^g (Ctrl+G)
export AI_COMPLETE_LOG="$HOME/.my-log"   # Default: ~/.ai-complete.log
export AI_COMPLETE_MAX_TURNS=50          # Default: 200
export AI_COMPLETE_SPINNER_COLOR='#89b4fa'  # Default: #cba6f7 (Catppuccin Mauve)
```

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_COMPLETE_MODEL` | `opus` | Claude model to use |
| `AI_COMPLETE_KEYBIND` | `^g` | Zsh keybinding (Ctrl+G) |
| `AI_COMPLETE_LOG` | `~/.ai-complete.log` | Log file path (set to `""` to disable) |
| `AI_COMPLETE_MAX_TURNS` | `200` | Max agent tool-use turns |
| `AI_COMPLETE_SPINNER_COLOR` | `#cba6f7` | Spinner text color (hex) |

## Logging

Every completion session is logged with the full stream-json trace (tool calls, messages, result):

```bash
ai-log          # View full log
ai-log-tail     # Last 30 lines
```

Useful for debugging, seeing what tools Claude used, or reviewing past suggestions.

## Limitations

- **Latency**: Claude needs 3-15s depending on complexity (it runs real tools like `man` and `--help`)
- **Requires tmux** for terminal output context and failure detection; without it, those features are skipped
- **bypassPermissions mode**: The widget runs Claude with `--permission-mode bypassPermissions` so it can freely use Bash/Read tools. This is appropriate for a local completion widget but means Claude can execute commands during its reasoning
- **Single command output**: Returns one command; doesn't handle multi-line scripts
- **No oh-my-zsh plugin packaging** yet — just a single sourceable file

## Part of Build AI Agents

This tool is part of [Module 7: Personal Agents](../README.md#module-7-personal-agents) in the Build AI Agents learning path. It demonstrates how Claude CLI can be integrated into personal developer workflows as an autonomous agent with tool use.

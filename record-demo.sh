#!/usr/bin/env bash
#
# record-demo.sh — record a GIF of the one-line bootstrap driving a real run
# -------------------------------------------------------------------------
# Produces demo.gif from an actual, unmodified:
#
#   bash <(wget -qO- https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh) -i
#
# It does not fake the output: vhs (charmbracelet/vhs) drives a real terminal,
# types the answers into the real prompts, and screen-scrapes to know when the
# next question is up. So the recording is only as reliable as the run — the
# preflight below exists to stop a bad credential from derailing a take.
#
# Usage:
#   ./record-demo.sh                       # asks for URL / login / API key
#   ODOO_URL=... ODOO_LOGIN=... ODOO_SECRET=... ./record-demo.sh --out docs/demo.gif
#   ./record-demo.sh --tail 600            # keep filming 10 min of the agent
#
# The demo it answers for, by default: a small Plumbing dataset, note
# "Using Field service, 5 sale.order and 3 invoices".
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --------------------------------------------------------------------------- #
# What the recording shows. Every one of these is an answer to a prompt in
# odoo-demo-feeder's Step 1 — keep them in sync with that prompt order.
# --------------------------------------------------------------------------- #
OUT="demo.gif"
MP4=""                                  # --mp4 FILE (optional second output)
CMD_URL="https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh"
FEED_ARGS="-i"

AI_CHOICE="${AI_CHOICE:-claude}"        # agy | copilot | claude (the first chooser)
ODOO_URL="${ODOO_URL:-}"
ODOO_LOGIN="${ODOO_LOGIN:-}"
ODOO_SECRET="${ODOO_SECRET:-}"
ODOO_DB="${ODOO_DB:-}"                  # left empty: SaaS auto-detects it
SCOPE="${SCOPE:-Plumbing}"
SIZE="${SIZE:-small}"                   # small | medium | big
COMPANY="${COMPANY:-}"                  # empty -> Enter to skip
SITE="${SITE:-}"                        # empty -> Enter to skip
EXTRA="${EXTRA:-Using Field service, 5 sale.order and 3 invoices}"

# Does the feeder ask "Database name"? It only asks when the connection check
# could not auto-detect one, so a tape that waits for it unconditionally hangs
# on SaaS. auto = decide from the preflight's own auth-check result.
DB_PROMPT="auto"                        # auto | yes | no

# --------------------------------------------------------------------------- #
# Recording knobs
# --------------------------------------------------------------------------- #
WIDTH=1200
HEIGHT=760
FONT_SIZE=15
THEME="Dracula"
TYPING_SPEED="55ms"
FRAMERATE=24
WAIT_TIMEOUT="6m"                       # per-prompt patience (npx/npm can be slow)
TAIL_SECONDS=60                         # how much of the agent's TUI to film
QUIT_KEYS="ctrl-c"                      # ctrl-c | none
KEEP_TAPE=0
SKIP_CHECK=0
DRY_RUN=0

PURPLE=$'\e[38;5;97m'; GREEN=$'\e[32m'; RED=$'\e[31m'; DIM=$'\e[2m'; RESET=$'\e[0m'
[[ -t 1 ]] || { PURPLE=""; GREEN=""; RED=""; DIM=""; RESET=""; }
step() { printf '%s\n' "${PURPLE}==> $*${RESET}"; }
ok()   { printf '%s\n' "${GREEN}  ✔ $*${RESET}"; }
warn() { printf '%s\n' "${RED}  ! $*${RESET}" >&2; }
die()  { printf '%s\n' "${RED}✖ $*${RESET}" >&2; exit 1; }

usage() {
    cat <<USAGE
record-demo.sh — record a GIF of 'bash <(wget -qO- .../feed.sh) -i'

  --out FILE         GIF to write (default: $OUT)
  --mp4 FILE         also write an mp4 (needs ffmpeg)
  --ai CLI           which CLI to pick in the first chooser: agy|copilot|claude
                     (default: $AI_CHOICE)
  --url URL          Odoo URL to type          (env ODOO_URL)
  --login LOGIN      login to type             (env ODOO_LOGIN)
  --secret SECRET    API key / password        (env ODOO_SECRET)
  --db NAME          database name to type; implies --db-prompt yes
  --db-prompt MODE   auto|yes|no — whether the feeder will ask for a database
  --scope TEXT       scope / industry          (default: $SCOPE)
  --size SIZE        small|medium|big          (default: $SIZE)
  --company NAME     customer company name     (default: skipped)
  --site URL         customer website          (default: skipped)
  --extra TEXT       "Anything else..." note   (default: "$EXTRA")
  --tail SECONDS     seconds of the agent's TUI to film (default: $TAIL_SECONDS)
  --quit-keys MODE   ctrl-c|none — how to end the recorded session
  --width / --height / --font-size / --theme / --typing-speed
  --skip-check       do not verify the credentials before recording
  --keep-tape PATH   write the .tape next to the output and keep it
  --dry-run          print the .tape and exit (no recording)
  -h, --help

Answers are typed into the real prompts, in the order odoo-demo-feeder asks
them. Change a prompt in the feeder and this tape needs the same change.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --out)          OUT="$2"; shift 2 ;;
        --mp4)          MP4="$2"; shift 2 ;;
        --ai)           AI_CHOICE="$2"; shift 2 ;;
        --url)          ODOO_URL="$2"; shift 2 ;;
        --login)        ODOO_LOGIN="$2"; shift 2 ;;
        --secret)       ODOO_SECRET="$2"; shift 2 ;;
        --db)           ODOO_DB="$2"; DB_PROMPT="yes"; shift 2 ;;
        --db-prompt)    DB_PROMPT="$2"; shift 2 ;;
        --scope)        SCOPE="$2"; shift 2 ;;
        --size)         SIZE="$2"; shift 2 ;;
        --company)      COMPANY="$2"; shift 2 ;;
        --site)         SITE="$2"; shift 2 ;;
        --extra)        EXTRA="$2"; shift 2 ;;
        --tail)         TAIL_SECONDS="$2"; shift 2 ;;
        --quit-keys)    QUIT_KEYS="$2"; shift 2 ;;
        --width)        WIDTH="$2"; shift 2 ;;
        --height)       HEIGHT="$2"; shift 2 ;;
        --font-size)    FONT_SIZE="$2"; shift 2 ;;
        --theme)        THEME="$2"; shift 2 ;;
        --typing-speed) TYPING_SPEED="$2"; shift 2 ;;
        --feed-args)    FEED_ARGS="$2"; shift 2 ;;
        --skip-check)   SKIP_CHECK=1; shift ;;
        --keep-tape)    KEEP_TAPE=1; TAPE_PATH="$2"; shift 2 ;;
        --dry-run)      DRY_RUN=1; shift ;;
        -h|--help)      usage; exit 0 ;;
        *)              die "Unknown option: $1 (see --help)" ;;
    esac
done

case "$AI_CHOICE" in agy|copilot|claude) ;; *) die "--ai must be agy, copilot or claude." ;; esac
case "$SIZE"      in small|medium|big)   ;; *) die "--size must be small, medium or big." ;; esac
case "$DB_PROMPT" in auto|yes|no)        ;; *) die "--db-prompt must be auto, yes or no." ;; esac

# --------------------------------------------------------------------------- #
# Dependencies: vhs drives the terminal, ttyd is the terminal it drives, ffmpeg
# encodes the frames. Fedora and Homebrew package vhs; Debian/Ubuntu need
# Charm's own apt repo (same one feed.sh adds for gum).
# --------------------------------------------------------------------------- #
PM=""
if   command -v dnf     >/dev/null 2>&1; then PM="dnf"
elif command -v apt-get >/dev/null 2>&1; then PM="apt"
elif command -v brew    >/dev/null 2>&1; then PM="brew"
fi
SUDO=""
if [[ "$PM" != "brew" && "$(id -u)" -ne 0 ]]; then SUDO="sudo"; fi

BIN_DIR="$HOME/.local/bin"
[[ ":$PATH:" == *":$BIN_DIR:"* ]] || export PATH="$BIN_DIR:$PATH"

# Both vhs and ttyd ship static binaries, so a machine where sudo needs a
# password (or has no package manager at all) is not a dead end — drop them in
# ~/.local/bin instead. Same fallback feed.sh uses for gum.
VHS_VERSION="${VHS_VERSION:-0.11.0}"
TTYD_VERSION="${TTYD_VERSION:-1.7.7}"

install_vhs_binary() {
    local os arch tmp bin
    os="$(uname -s)"; arch="$(uname -m)"
    case "$arch" in x86_64|amd64) arch="x86_64";; aarch64|arm64) arch="arm64";; *) return 1;; esac
    [[ "$os" == "Linux" || "$os" == "Darwin" ]] || return 1
    tmp="$(mktemp -d)"
    curl -fsSL "https://github.com/charmbracelet/vhs/releases/download/v${VHS_VERSION}/vhs_${VHS_VERSION}_${os}_${arch}.tar.gz" \
        -o "$tmp/vhs.tgz" 2>/dev/null && tar -xzf "$tmp/vhs.tgz" -C "$tmp" 2>/dev/null || { rm -rf "$tmp"; return 1; }
    bin="$(find "$tmp" -type f -name vhs | head -n1)"
    [[ -n "$bin" ]] && mkdir -p "$BIN_DIR" && install -m755 "$bin" "$BIN_DIR/vhs" || { rm -rf "$tmp"; return 1; }
    rm -rf "$tmp"
}

# ttyd publishes one static binary per arch, named after `uname -m` itself.
install_ttyd_binary() {
    local arch; arch="$(uname -m)"
    [[ "$(uname -s)" == "Linux" ]] || return 1
    case "$arch" in x86_64|aarch64|armv7l|i686) ;; *) return 1;; esac
    mkdir -p "$BIN_DIR"
    curl -fsSL "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.${arch}" \
        -o "$BIN_DIR/ttyd" 2>/dev/null || return 1
    chmod +x "$BIN_DIR/ttyd"
}

pkg_install_recorder() {  # pkg_install_recorder <pkg>...
    case "$PM" in
        dnf)  [[ -n "$SUDO" ]] && ! sudo -n true 2>/dev/null && return 1
              $SUDO dnf install -y "$@" >/dev/null 2>&1 ;;
        apt)  [[ -n "$SUDO" ]] && ! sudo -n true 2>/dev/null && return 1
              $SUDO apt-get install -y "$@" >/dev/null 2>&1 ;;
        brew) brew install "$@" >/dev/null 2>&1 ;;
        *)    return 1 ;;
    esac
}

install_hint() {
    case "$PM" in
        dnf)  printf 'sudo dnf install -y vhs ttyd ffmpeg' ;;
        apt)  printf 'sudo apt install ttyd ffmpeg, plus vhs from https://github.com/charmbracelet/vhs#installation' ;;
        brew) printf 'brew install vhs ttyd ffmpeg' ;;
        *)    printf 'see https://github.com/charmbracelet/vhs#installation' ;;
    esac
}

# ensure_recorder_bin <cmd> <package-name> <binary-fallback-fn|-->
ensure_recorder_bin() {
    local cmd="$1" pkg="$2" fallback="$3"
    command -v "$cmd" >/dev/null 2>&1 && { ok "$cmd present"; return 0; }
    warn "$cmd not found — installing..."
    if pkg_install_recorder "$pkg" && command -v "$cmd" >/dev/null 2>&1; then
        ok "$cmd installed ($PM)"; return 0
    fi
    if [[ "$fallback" != "--" ]] && "$fallback" && command -v "$cmd" >/dev/null 2>&1; then
        ok "$cmd installed (static binary → $BIN_DIR)"; return 0
    fi
    return 1
}

step "Checking recording dependencies"
if [[ "$DRY_RUN" -eq 0 ]]; then
    ensure_recorder_bin ffmpeg ffmpeg --                 || die "ffmpeg is required. Install it: $(install_hint)"
    ensure_recorder_bin ttyd   ttyd   install_ttyd_binary || die "ttyd is required (vhs drives it). Install it: $(install_hint)"
    ensure_recorder_bin vhs    vhs    install_vhs_binary  || die "vhs is required. Install it: $(install_hint)"
fi

# --------------------------------------------------------------------------- #
# Credentials. Asked here rather than typed live so a mistyped key costs a
# prompt, not a take. The API key ends up inside the .tape (vhs has no way to
# read it from the environment), so the tape is 0600 and deleted after the run
# unless --keep-tape says otherwise.
# --------------------------------------------------------------------------- #
ask() {  # ask <label> [placeholder]
    if command -v gum >/dev/null 2>&1 && [[ -t 0 && -t 2 ]]; then
        gum input --prompt "$1 " --placeholder "${2:-}"
    else
        local v; read -r -p "  $1${2:+ ($2)}: " v; printf '%s' "$v"
    fi
}
ask_secret() {  # ask_secret <label>
    if command -v gum >/dev/null 2>&1 && [[ -t 0 && -t 2 ]]; then
        gum input --password --prompt "$1 "
    else
        local v; read -r -s -p "  $1: " v; printf '\n' >&2; printf '%s' "$v"
    fi
}

if [[ "$DRY_RUN" -eq 0 || -n "$ODOO_URL$ODOO_LOGIN$ODOO_SECRET" ]]; then
    step "Demo database to record against"
    [[ -n "$ODOO_URL" ]]    || ODOO_URL="$(ask 'Odoo URL' 'e.g. https://mycompany.odoo.com')"
    [[ -n "$ODOO_LOGIN" ]]  || ODOO_LOGIN="$(ask 'Login (email or user)')"
    [[ -n "$ODOO_SECRET" ]] || ODOO_SECRET="$(ask_secret 'API key or password')"
    ODOO_URL="${ODOO_URL%/}"
    [[ -n "$ODOO_URL" && -n "$ODOO_LOGIN" && -n "$ODOO_SECRET" ]] \
        || die "URL, login and API key are all required — the tape has to type them."
fi

# --------------------------------------------------------------------------- #
# Preflight: same auth-check the feeder runs. It answers two questions at once —
# are the credentials good (a failed check drops the feeder into a re-entry loop
# the tape knows nothing about), and will the "Database name" prompt appear.
# --------------------------------------------------------------------------- #
CRUD_TOOL="${CRUD_TOOL:-$HERE/odoo_crud.py}"
[[ -f "$CRUD_TOOL" ]] || CRUD_TOOL="$HOME/.local/share/odoo-demo-feeder/odoo_crud.py"

if [[ "$SKIP_CHECK" -eq 0 && "$DRY_RUN" -eq 0 ]]; then
    step "Verifying the database (so the take is not wasted)"
    if [[ -f "$CRUD_TOOL" ]] && command -v python3 >/dev/null 2>&1; then
        set +e
        AUTH_OUT=$(ODOO_URL="$ODOO_URL" ODOO_LOGIN="$ODOO_LOGIN" ODOO_SECRET="$ODOO_SECRET" \
                   ODOO_DB="$ODOO_DB" python3 "$CRUD_TOOL" auth-check 2>&1)
        AUTH_STATUS=$?
        set -e
        [[ $AUTH_STATUS -eq 0 ]] || die "auth-check failed — fix this before recording:
$AUTH_OUT"
        DETECTED_DB=$(printf '%s' "$AUTH_OUT" \
            | python3 -c "import sys, json; print(json.load(sys.stdin).get('result', {}).get('database', ''))" 2>/dev/null || true)
        ok "connection works${DETECTED_DB:+ (database: $DETECTED_DB)}"
        if [[ "$DB_PROMPT" == "auto" ]]; then
            if [[ -n "$ODOO_DB" || -n "$DETECTED_DB" ]]; then DB_PROMPT="no"; else DB_PROMPT="yes"; fi
            ok "the feeder will $([[ "$DB_PROMPT" == yes ]] && echo 'ask' || echo 'not ask') for a database name"
        fi
    else
        warn "odoo_crud.py not found — skipping the check (set CRUD_TOOL to point at it)"
    fi
fi
# Nothing verified the auto-detection, so fall back to what the URL implies.
if [[ "$DB_PROMPT" == "auto" ]]; then
    case "$ODOO_URL" in
        *.odoo.com*) DB_PROMPT="no" ;;
        *)           DB_PROMPT="yes" ;;
    esac
fi

# --------------------------------------------------------------------------- #
# The tape. Every answer is preceded by a Wait+Screen on the prompt's own text:
# fixed Sleeps would drift the moment an install, npx skills or the network
# takes a second longer than last time.
# --------------------------------------------------------------------------- #
if [[ "$KEEP_TAPE" -eq 1 ]]; then
    TAPE="${TAPE_PATH:-${OUT%.gif}.tape}"
    : > "$TAPE"; chmod 600 "$TAPE"
    warn "the tape contains your API key in clear text: $TAPE"
else
    TAPE="$(mktemp -t odoo-feeder-demo.XXXXXX.tape)"
    chmod 600 "$TAPE"
    trap 'rm -f "$TAPE"' EXIT
fi

# Number of Down presses to land on an option in a gum chooser (cursor starts
# on the first entry).
downs() {  # downs <n>
    (( $1 > 0 )) && printf 'Down %s\nSleep 400ms\n' "$1" || true
}
# Type a value, or just press Enter when it is empty (the optional prompts all
# take an empty answer as "skip").
answer() {  # answer <value>
    if [[ -n "$1" ]]; then
        printf 'Type "%s"\nSleep 700ms\nEnter\n' "${1//\"/\\\"}"
    else
        printf 'Sleep 900ms\nEnter\n'
    fi
}

{
    printf 'Output %s\n' "$OUT"
    [[ -n "$MP4" ]] && printf 'Output %s\n' "$MP4"
    cat <<TAPE

Set Shell bash
Set Theme "$THEME"
Set FontSize $FONT_SIZE
Set Width $WIDTH
Set Height $HEIGHT
Set Padding 20
Set Framerate $FRAMERATE
Set TypingSpeed $TYPING_SPEED
Set WindowBar Colorful
Set WaitTimeout $WAIT_TIMEOUT
TAPE

    # A clean, branded prompt — hidden, so the recording opens on the real command.
    cat <<'TAPE'

Hide
Type `export PS1='\[\e[38;5;97m\]❯\[\e[0m\] '` Enter
Type "clear" Enter
Show
Sleep 1500ms
TAPE

    printf '\nType "bash <(wget -qO- %s) %s"\nSleep 1200ms\nEnter\n' "$CMD_URL" "$FEED_ARGS"

    # feed.sh — "Which AI CLI should drive the agent?" (agy, copilot, claude)
    case "$AI_CHOICE" in agy) n=0 ;; copilot) n=1 ;; claude) n=2 ;; esac
    printf '\nWait+Screen /Which AI CLI/\nSleep 1500ms\n'
    downs "$n"
    printf 'Enter\n'

    # odoo-demo-feeder Step 1 — connection details.
    printf '\nWait+Screen /Odoo URL/\nSleep 1200ms\n'
    answer "$ODOO_URL"
    printf '\nWait+Screen /Login .email or user./\nSleep 800ms\n'
    answer "$ODOO_LOGIN"
    printf '\nWait+Screen /API key or password/\nSleep 800ms\n'
    answer "$ODOO_SECRET"

    # Content — template or scratch (scratch is the second entry).
    printf '\nWait+Screen /template or start from scratch/\nSleep 1500ms\n'
    downs 1
    printf 'Enter\n'

    printf '\nWait+Screen /Scope . industry/\nSleep 1000ms\n'
    answer "$SCOPE"

    if [[ "$DB_PROMPT" == "yes" ]]; then
        printf '\nWait+Screen /Database name/\nSleep 900ms\n'
        answer "$ODOO_DB"
    fi

    # Dataset size — gum chooser, small first.
    case "$SIZE" in small) n=0 ;; medium) n=1 ;; big) n=2 ;; esac
    printf '\nWait+Screen /Dataset size/\nSleep 1200ms\n'
    downs "$n"
    printf 'Enter\n'

    printf '\nWait+Screen /Customer company name/\nSleep 900ms\n'
    answer "$COMPANY"
    printf '\nWait+Screen /Customer website/\nSleep 900ms\n'
    answer "$SITE"
    printf '\nWait+Screen /Anything else/\nSleep 900ms\n'
    answer "$EXTRA"

    # Steps 2 and 3 run unattended; film the agent for a while, then leave.
    printf '\nWait+Screen /Step 3.3/\nSleep %ss\n' "$TAIL_SECONDS"
    if [[ "$QUIT_KEYS" == "ctrl-c" ]]; then
        cat <<'TAPE'
Ctrl+C
Sleep 800ms
Ctrl+C
Sleep 3s
TAPE
    fi
} >> "$TAPE"

if [[ "$DRY_RUN" -eq 1 ]]; then
    step "Tape (not recorded)"
    cat "$TAPE"
    exit 0
fi

# --------------------------------------------------------------------------- #
# Record. ODOO_* must NOT leak into the recorded shell: the feeder takes any of
# them from the environment and skips that prompt, which would leave the tape
# answering questions nobody asked. ASSUME_SIGNED_IN keeps feed.sh from doing
# its 30s sign-in probe (or worse, opening a browser mid-take).
# --------------------------------------------------------------------------- #
# vhs parses the whole tape up front, so a typo in it is worth catching before
# a run starts writing records into a database.
vhs validate "$TAPE" >/dev/null 2>&1 || die "vhs rejected the generated tape:
$(vhs validate "$TAPE" 2>&1 | head -20)"

step "Recording → $OUT"
printf '%s\n' "${DIM}  answers: ai=$AI_CHOICE scope=$SCOPE size=$SIZE db-prompt=$DB_PROMPT tail=${TAIL_SECONDS}s${RESET}"
env -u ODOO_URL -u ODOO_LOGIN -u ODOO_SECRET -u ODOO_DB -u ODOO_SCOPE \
    -u ODOO_SIZE -u COMPANY_NAME -u COMPANY_SITE -u EXTRA \
    -u TEMPLATE_FILE -u TEMPLATE_TEXT -u AI_CLI \
    ASSUME_SIGNED_IN="${ASSUME_SIGNED_IN:-1}" \
    vhs "$TAPE"

ok "$OUT ($(du -h "$OUT" | cut -f1))"
[[ -n "$MP4" ]] && ok "$MP4 ($(du -h "$MP4" | cut -f1))"

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
REF="main"                              # --ref: git ref to bootstrap from
FEED_ARGS="-i"

# Which film to make. The feeder's own flags decide how much there is to see:
#   prompts — the recorded command line is bare, every value below is TYPED
#             into the real prompt. This is the interactive tour.
#   flags   — the recorded command line carries the flags (your example). Any
#             value flag sets GAVE_ARGS=1 in the feeder, which skips the
#             template chooser and all the optional prompts, so the film is the
#             command plus Steps 2/3. Short, and nothing to type.
MODE="prompts"
SHOW_SECRET=0                           # flags mode: put --secret on screen
AI_FLAG=0                               # pass --ai-cli instead of filming the chooser

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
WARMUP_SECONDS=60                       # unattended Steps 2/3 before the tail
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

  --mode MODE        prompts|flags (default: $MODE)
                     prompts: bare command line, answers typed into the prompts
                     flags:   the feeder's own flags on the command line, which
                              makes it skip those prompts entirely
  --ref REF          git ref to bootstrap from (default: $REF) — pins both the
                     raw URL and REPO_REF, as in REPO_REF=199ca21 bash <(...)
  --ai-flag          pass --ai-cli instead of filming the CLI chooser
  --show-secret      flags mode: put --secret on the visible command line
                     (default: passed through the environment, off screen)
  --out FILE         GIF to write (default: $OUT)
  --mp4 FILE         also write an mp4 (needs ffmpeg)
  --ai CLI           which CLI to pick in the first chooser: agy|copilot|claude
                     (default: $AI_CHOICE)
  --url URL          Odoo URL to type          (env ODOO_URL)
  --login LOGIN      login to type             (env ODOO_LOGIN)
  --secret SECRET    API key / password        (env ODOO_SECRET)
  --db NAME          database name to type when the feeder asks for one
                     (default: the URL's own subdomain, which is the database
                     name on *.odoo.com — so SaaS never needs this flag)
  --db-prompt MODE   auto|yes|no — whether the feeder will ask for a database
  --scope TEXT       scope / industry          (default: $SCOPE)
  --size SIZE        small|medium|big          (default: $SIZE)
  --company NAME     customer company name     (default: skipped)
  --site/--website   customer website          (default: skipped)
  --extra/--notes    "Anything else..." note   (default: "$EXTRA")
  --tail SECONDS     seconds of the agent's TUI to film (default: $TAIL_SECONDS)
  --warmup SECONDS   seconds to let Steps 2/3 run before the tail starts
                     (default: $WARMUP_SECONDS) — the skills install and the
                     agent's own boot, which nothing on screen announces
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
        --db)           ODOO_DB="$2"; shift 2 ;;
        --db-prompt)    DB_PROMPT="$2"; shift 2 ;;
        --scope)        SCOPE="$2"; shift 2 ;;
        --size)         SIZE="$2"; shift 2 ;;
        --company)      COMPANY="$2"; shift 2 ;;
        --site|--website) SITE="$2"; shift 2 ;;
        --extra|--notes)  EXTRA="$2"; shift 2 ;;
        --mode)         MODE="$2"; shift 2 ;;
        --ref|--repo-ref) REF="$2"; shift 2 ;;
        --ai-flag)      AI_FLAG=1; shift ;;
        --show-secret)  SHOW_SECRET=1; shift ;;
        --tail)         TAIL_SECONDS="$2"; shift 2 ;;
        --warmup)       WARMUP_SECONDS="$2"; shift 2 ;;
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
case "$MODE"      in prompts|flags)      ;; *) die "--mode must be prompts or flags." ;; esac
# In flags mode nothing is typed into a prompt, so the CLI has to come from the
# flag — there is no chooser to film.
[[ "$MODE" == "flags" ]] && AI_FLAG=1
CMD_URL="https://raw.githubusercontent.com/odoo-ps/odoo-feeder/${REF}/feed.sh"

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

# SaaS runs one database per subdomain, and odoo_crud.py falls back to exactly
# this name when ODOO_DB is empty. Deriving it here as well is what keeps --db
# optional: whatever the check has to be retried with, and whatever the tape
# types if the feeder does ask, comes from the URL when no --db was given.
url_db() {  # url_db <url> -> the host's first label, empty when it implies none
    local host="${1#*://}"; host="${host%%/*}"; host="${host%%:*}"
    [[ "$host" == *.* ]]                 || return 0   # localhost, a bare name
    [[ "$host" =~ ^[0-9.]+$ ]]           && return 0   # an IP address
    printf '%s' "${host%%.*}"
}
URL_DB="$(url_db "$ODOO_URL")"
# What the tape types at a "Database name" prompt. --db wins, then whatever the
# check auto-detects, then the subdomain. Kept apart from ODOO_DB so that flags
# mode still films only the flags that were actually asked for.
DB_NAME="${ODOO_DB:-$URL_DB}"

auth_check() {  # auth_check <db>  -> prints the JSON, exit status is the check's
    ODOO_URL="$ODOO_URL" ODOO_LOGIN="$ODOO_LOGIN" ODOO_SECRET="$ODOO_SECRET" \
    ODOO_DB="${1:-}" python3 "$CRUD_TOOL" auth-check 2>&1
}
json_get() { python3 -c "import sys, json; print(json.load(sys.stdin).get('result', {}).get('$1', ''))" 2>/dev/null || true; }

if [[ "$SKIP_CHECK" -eq 0 && "$DRY_RUN" -eq 0 ]]; then
    step "Verifying the database (so the take is not wasted)"
    if [[ -f "$CRUD_TOOL" ]] && command -v python3 >/dev/null 2>&1; then
        # First check with no database name at all — exactly the state the
        # feeder is in before it decides whether to ask for one.
        set +e; AUTH_OUT="$(auth_check '')"; AUTH_STATUS=$?; set -e
        if [[ $AUTH_STATUS -eq 0 ]]; then
            DETECTED_DB="$(printf '%s' "$AUTH_OUT" | json_get database)"
            ok "connection works${DETECTED_DB:+ (auto-detected database: $DETECTED_DB)}"
            [[ -n "$DETECTED_DB" ]] && DB_NAME="${ODOO_DB:-$DETECTED_DB}"
            [[ "$DB_PROMPT" == "auto" ]] && { [[ -n "$DETECTED_DB" ]] && DB_PROMPT="no" || DB_PROMPT="yes"; }
            if [[ -n "$ODOO_DB" && -n "$DETECTED_DB" && "$ODOO_DB" != "$DETECTED_DB" && "$MODE" == "prompts" ]]; then
                warn "--db $ODOO_DB will never be typed: the feeder auto-detects '$DETECTED_DB' and skips that prompt."
            fi
        elif [[ -n "$DB_NAME" ]]; then
            # Auto-detection failed (localhost, multi-db, or a hiccup on a
            # perfectly good SaaS host), so the feeder will ask — verify the
            # name the tape is going to type. Without --db that name is the
            # URL's subdomain, which is why *.odoo.com does not need the flag.
            set +e; AUTH_OUT="$(auth_check "$DB_NAME")"; AUTH_STATUS=$?; set -e
            if [[ $AUTH_STATUS -ne 0 ]]; then
                [[ -n "$ODOO_DB" ]] \
                    && die "auth-check failed for database '$DB_NAME' — fix this before recording:
$AUTH_OUT"
                die "auth-check failed, with no database name and with '$DB_NAME' (the URL's
  subdomain) — so this is the credentials or the host, not the database name.
  Pass --db only if this database is called something else:
$AUTH_OUT"
            fi
            src="from the URL host"; [[ -n "$ODOO_DB" ]] && src="--db"
            ok "connection works with database '$DB_NAME' ($src) — not auto-detected, so it will be asked for"
            [[ "$DB_PROMPT" == "auto" ]] && DB_PROMPT="yes"
        else
            die "auth-check failed, and this URL implies no database name — fix this
  before recording (or name the database with --db):
$AUTH_OUT"
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
# Flags mode answers no prompts at all.
[[ "$MODE" == "flags" ]] && DB_PROMPT="no"

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

# A vhs `Type` argument delimited by backticks: the command lines carry double
# quotes and backslashes, which the "..." form would try to interpret.
type_raw() { printf 'Type `%s`\n' "$1"; }

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

    # ----- the command line itself ----------------------------------------- #
    prefix=""
    [[ "$REF" != "main" ]] && prefix="REPO_REF=$REF "
    boot="${prefix}bash <(wget -qO- $CMD_URL)"

    if [[ "$MODE" == "prompts" ]]; then
        line="$boot"
        [[ "$AI_FLAG" -eq 1 ]] && line="$line --ai-cli $AI_CHOICE"
        printf '\n'; type_raw "$line $FEED_ARGS"
        printf 'Sleep 1200ms\nEnter\n'
    else
        # One flag per line, continued with a backslash, as you would type it.
        printf '\n'; type_raw "$boot \\"; printf 'Enter\nSleep 300ms\n'
        flags=(--ai-cli "$AI_CHOICE" --url "$ODOO_URL" --login "$ODOO_LOGIN")
        [[ "$SHOW_SECRET" -eq 1 ]] && flags+=(--secret "$ODOO_SECRET")
        [[ -n "$ODOO_DB" ]]  && flags+=(--db "$ODOO_DB")
        flags+=(--scope "$SCOPE" --size "$SIZE")
        [[ -n "$COMPANY" ]]  && flags+=(--company "$COMPANY")
        [[ -n "$SITE" ]]     && flags+=(--website "$SITE")
        [[ -n "$EXTRA" ]]    && flags+=(--notes "$EXTRA")
        i=0
        while (( i < ${#flags[@]} )); do
            # Quote the value only when it needs it, so the film reads naturally.
            val="${flags[i+1]}"
            case "$val" in *[[:space:]]*) val="\"$val\"" ;; esac
            type_raw "  ${flags[i]} $val \\"; printf 'Enter\nSleep 250ms\n'
            i=$((i+2))
        done
        type_raw "  $FEED_ARGS"; printf 'Sleep 1200ms\nEnter\n'
    fi

    # feed.sh opens on its own dependency check, before anything is asked.
    # Waiting for it (or for whatever is already past it — the alternatives are
    # what keep this from ever hanging) holds the film there long enough to read.
    printf '\nWait+Screen /Checking dependencies|Which AI CLI|Odoo URL|Step 1.3/\n'
    printf 'Sleep 2500ms\n'

    # ----- the prompts, each one waited for by its own text ----------------- #
    if [[ "$AI_FLAG" -eq 0 ]]; then
        # feed.sh — "Which AI CLI should drive the agent?" (agy, copilot, claude)
        case "$AI_CHOICE" in agy) n=0 ;; copilot) n=1 ;; claude) n=2 ;; esac
        printf '\nWait+Screen /Which AI CLI/\nSleep 1500ms\n'
        downs "$n"
        printf 'Enter\n'
    fi

    if [[ "$MODE" == "prompts" ]]; then
        # Step 1 — connection details.
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

        [[ "$DB_PROMPT" == "yes" ]] && {
            printf '\nWait+Screen /Database name/\nSleep 900ms\n'
            answer "$DB_NAME"
        }

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
    fi

    # Steps 2 and 3 run unattended; film the agent for a while, then leave.
    #
    # Anchored on Step 2's header, not Step 3's: Step 2 stays on screen for the
    # whole (quiet) skills install, while the agent's TUI clears the screen a
    # frame or two after Step 3 prints — a Wait on Step 3 can miss it outright
    # and then burn the entire WaitTimeout before killing a finished take. The
    # alternatives cover a take that only gets here once the agent is up.
    printf '\nWait+Screen /Step 2.3|Updating the AI skills|Step 3.3|Populating the database/\n'
    printf 'Sleep %ss\n' "$WARMUP_SECONDS"
    printf 'Sleep %ss\n' "$TAIL_SECONDS"
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
printf '%s\n' "${DIM}  mode=$MODE ref=$REF ai=$AI_CHOICE scope=$SCOPE size=$SIZE db-prompt=$DB_PROMPT tail=${TAIL_SECONDS}s${RESET}"
RECORD_ENV=(env -u ODOO_URL -u ODOO_LOGIN -u ODOO_DB -u ODOO_SCOPE
            -u ODOO_SIZE -u COMPANY_NAME -u COMPANY_SITE -u EXTRA
            -u TEMPLATE_FILE -u TEMPLATE_TEXT -u AI_CLI
            ASSUME_SIGNED_IN="${ASSUME_SIGNED_IN:-1}")
# flags mode without --show-secret: hand the key to the feeder through the
# environment instead of typing it where the camera can see it.
if [[ "$MODE" == "flags" && "$SHOW_SECRET" -eq 0 ]]; then
    RECORD_ENV+=(ODOO_SECRET="$ODOO_SECRET")
else
    RECORD_ENV=("${RECORD_ENV[@]:0:1}" -u ODOO_SECRET "${RECORD_ENV[@]:1}")
fi
"${RECORD_ENV[@]}" vhs "$TAPE"

ok "$OUT ($(du -h "$OUT" | cut -f1))"
[[ -n "$MP4" ]] && ok "$MP4 ($(du -h "$MP4" | cut -f1))"

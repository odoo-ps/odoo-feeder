#!/usr/bin/env bash
#
# Odoo Demo Database Feeder — one-shot bootstrap + launch
# ------------------------------------------------------
# Run everything from a single URL, no separate setup step:
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh)
#   bash <(wget -qO-  https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh)
#
# ...optionally with flags forwarded to the feeder:
#
#   bash <(curl -fsSL .../feed.sh) --url https://mycompany.odoo.com --login admin ...
#
# It installs what is missing (agy, bubblewrap, Node.js, Python, optionally gum
# for nicer prompts), fetches the
# latest feeder + CRUD tool, then launches. Re-running is cheap: anything already
# present is skipped.
#
set -euo pipefail

REPO="odoo-ps/odoo-feeder"
# Git ref (branch, tag or commit) to fetch the feeder + CRUD tool from. Defaults
# to main; override to test a branch, e.g. REPO_REF=imp-gum-templates.
REPO_REF="${REPO_REF:-main}"
# Which AI CLI drives the agent: "agy" (Antigravity), "copilot" (GitHub
# Copilot CLI) or "claude" (Claude Code). Prompted for further down when
# neither --ai-cli nor this env var picks one; AI_CLI_GIVEN tracks that so
# the prompt is skipped once either has.
AI_CLI="${AI_CLI:-}"
AI_CLI_GIVEN=0
[[ -n "$AI_CLI" ]] && AI_CLI_GIVEN=1
# OpenRouter BYOK, 'copilot' only (see odoo-demo-feeder --help). Its presence
# here just tells the sign-in probe below that no GitHub login is needed. The
# API key itself lives in the OS keyring under this service/account, same as
# odoo-demo-feeder expects — see the keyring step further down.
OPENROUTER_MODEL="${OPENROUTER_MODEL:-}"
OPENROUTER_KEYRING_SERVICE="odoo-feeder"
OPENROUTER_KEYRING_ACCOUNT="openrouter-api-key"

# Parse options to detect AI_CLI and OPENROUTER_MODEL early, so we install and
# check the right provider. We don't consume them (they must be forwarded to the feeder).
idx=1
while [[ $idx -le $# ]]; do
    case "${!idx}" in
        --ai-cli)
            next_idx=$((idx + 1))
            if [[ $next_idx -le $# ]]; then
                AI_CLI="${!next_idx}"
                AI_CLI_GIVEN=1
            fi
            ;;
        --ai-cli=*)
            AI_CLI="${!idx#*=}"
            AI_CLI_GIVEN=1
            ;;
        --openrouter-model)
            next_idx=$((idx + 1))
            if [[ $next_idx -le $# ]]; then
                OPENROUTER_MODEL="${!next_idx}"
            fi
            ;;
        --openrouter-model=*)
            OPENROUTER_MODEL="${!idx#*=}"
            ;;
    esac
    idx=$((idx + 1))
done

RAW="https://raw.githubusercontent.com/${REPO}/${REPO_REF}"
BIN_DIR="$HOME/.local/bin"
DATA_DIR="$HOME/.local/share/odoo-demo-feeder"

PURPLE=$'\e[38;5;97m'; GREEN=$'\e[32m'; RED=$'\e[31m'; DIM=$'\e[2m'; RESET=$'\e[0m'
[[ -t 1 ]] || { PURPLE=""; GREEN=""; RED=""; DIM=""; RESET=""; }
step() { printf '%s\n' "${PURPLE}==> $*${RESET}"; }
ok()   { printf '%s\n' "${GREEN}  ✔ $*${RESET}"; }
warn() { printf '%s\n' "${RED}  ! $*${RESET}" >&2; }
die()  { printf '%s\n' "${RED}✖ $*${RESET}" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# Download helper — use curl or wget, whichever is present (Ubuntu ships wget by
# default, other distros curl). Every download in this script goes through these.
# --------------------------------------------------------------------------- #
DL=""
if   command -v curl >/dev/null 2>&1; then DL="curl"
elif command -v wget >/dev/null 2>&1; then DL="wget"
fi
fetch()    {  # fetch <url>            -> writes the body to stdout
    case "$DL" in
        curl) curl -fsSL "$1" ;;
        wget) wget -qO- "$1" ;;
        *)    return 1 ;;
    esac
}
fetch_to() {  # fetch_to <url> <file>  -> saves the body to <file>
    case "$DL" in
        curl) curl -fsSL "$1" -o "$2" ;;
        wget) wget -q    "$1" -O "$2" ;;
        *)    return 1 ;;
    esac
}

# --------------------------------------------------------------------------- #
# Detect how to install system packages: Debian/Ubuntu apt, Fedora/RHEL dnf, or
# macOS Homebrew (brew).
# --------------------------------------------------------------------------- #
PM=""
if command -v apt-get >/dev/null 2>&1; then PM="apt"
elif command -v dnf   >/dev/null 2>&1; then PM="dnf"
elif command -v brew  >/dev/null 2>&1; then PM="brew"
fi
# Homebrew refuses to run under sudo; everything else needs it unless we are root.
SUDO=""
if [[ "$PM" != "brew" && "$(id -u)" -ne 0 ]]; then SUDO="sudo"; fi

pkg_install() {  # pkg_install <apt-names> ::: <dnf-names> ::: <brew-names>
    local apt_pkgs=() dnf_pkgs=() brew_pkgs=() idx=0 a
    for a in "$@"; do
        if [[ "$a" == ":::" ]]; then idx=$((idx+1)); continue; fi
        case "$idx" in
            0) apt_pkgs+=("$a") ;;
            1) dnf_pkgs+=("$a") ;;
            2) brew_pkgs+=("$a") ;;
        esac
    done
    case "$PM" in
        apt)  $SUDO apt-get update -y >/dev/null 2>&1 || true
              $SUDO apt-get install -y "${apt_pkgs[@]}" ;;
        dnf)  $SUDO dnf install -y "${dnf_pkgs[@]}" ;;
        brew) brew install "${brew_pkgs[@]}" ;;
        *)    return 1 ;;
    esac
}

ensure_cmd() {  # ensure_cmd <command> <apt-names> ::: <dnf-names> ::: <brew-names>
    local cmd="$1"; shift
    command -v "$cmd" >/dev/null 2>&1 && { ok "$cmd already present"; return 0; }
    [[ -n "$PM" ]] || die "$cmd is missing and no supported package manager (apt/dnf/brew) was found. Install $cmd manually."
    warn "$cmd not found — installing..."
    pkg_install "$@" || die "Could not install $cmd automatically. Please install it and re-run."
    command -v "$cmd" >/dev/null 2>&1 || die "$cmd still not available after install."
    ok "$cmd installed"
}

# gum powers the nicer prompts, but it is OPTIONAL — the feeder falls back to
# plain prompts without it, so every failure here is a warning, never fatal.
# Prefer real packages: dnf ships gum directly; Debian/Ubuntu need Charm's own
# apt repo. As a last resort, drop the userland binary into ~/.local/bin.
ensure_gum() {
    command -v gum >/dev/null 2>&1 && { ok "gum already present"; return 0; }
    case "$PM" in
        brew)
            brew install gum >/dev/null 2>&1 && command -v gum >/dev/null 2>&1 \
                && { ok "gum installed (brew)"; return 0; } ;;
        dnf)
            $SUDO dnf install -y gum >/dev/null 2>&1 && command -v gum >/dev/null 2>&1 \
                && { ok "gum installed (dnf)"; return 0; } ;;
        apt)
            # Add Charm's official apt repo (keyring + source), then install.
            if $SUDO mkdir -p /etc/apt/keyrings 2>/dev/null \
               && fetch https://repo.charm.sh/apt/gpg.key \
                    | $SUDO gpg --dearmor -o /etc/apt/keyrings/charm.gpg 2>/dev/null \
               && echo "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *" \
                    | $SUDO tee /etc/apt/sources.list.d/charm.list >/dev/null 2>&1; then
                $SUDO apt-get update -y >/dev/null 2>&1 || true
                $SUDO apt-get install -y gum >/dev/null 2>&1 && command -v gum >/dev/null 2>&1 \
                    && { ok "gum installed (apt / repo.charm.sh)"; return 0; }
            fi ;;
    esac
    # Fallback: fetch the release binary into ~/.local/bin (no sudo, no repo).
    # Charm names assets gum_<ver>_<OS>_<arch>.tar.gz where <OS> is exactly what
    # `uname -s` prints (Linux / Darwin), so reuse it directly.
    local ver="0.17.0" os arch tmp bin
    os="$(uname -s)"; arch="$(uname -m)"
    case "$arch" in x86_64|amd64) arch="x86_64";; aarch64|arm64) arch="arm64";; *) arch="";; esac
    if [[ ( "$os" == "Linux" || "$os" == "Darwin" ) && -n "$arch" ]]; then
        tmp="$(mktemp -d)"
        if fetch_to "https://github.com/charmbracelet/gum/releases/download/v${ver}/gum_${ver}_${os}_${arch}.tar.gz" \
              "$tmp/gum.tgz" 2>/dev/null && tar -xzf "$tmp/gum.tgz" -C "$tmp" 2>/dev/null; then
            bin="$(find "$tmp" -type f -name gum | head -n1)"
            [[ -n "$bin" ]] && install -m755 "$bin" "$BIN_DIR/gum" 2>/dev/null \
                && { rm -rf "$tmp"; ok "gum installed (binary → $BIN_DIR)"; return 0; }
        fi
        rm -rf "$tmp"
    fi
    warn "Could not install gum — the feeder will use plain prompts (this is fine)."
    return 0
}

# --------------------------------------------------------------------------- #
# AI CLI provider dispatch — agy (Antigravity), copilot (GitHub Copilot CLI)
# and claude (Claude Code) are implemented. Unknown providers fail fast,
# before any install or network work happens.
# --------------------------------------------------------------------------- #
provider_supported() {
    case "$AI_CLI" in
        agy|copilot|claude) ;;
        *)      die "Unknown AI_CLI='$AI_CLI'. Only 'agy', 'copilot' and 'claude' are supported today." ;;
    esac
}
provider_bin() {
    case "$AI_CLI" in
        agy)     printf 'agy' ;;
        copilot) printf 'copilot' ;;
        claude)  printf 'claude' ;;
    esac
}

# provider_install — fetch and run the provider's own installer.
provider_install() {
    case "$AI_CLI" in
        agy)     fetch https://antigravity.google/cli/install.sh | bash ;;
        copilot) fetch https://gh.io/copilot-install | bash ;;
        claude)  fetch https://code.claude.com/install.sh | bash ;;
    esac
}

# --------------------------------------------------------------------------- #
step "Checking dependencies"
# --------------------------------------------------------------------------- #
[[ -n "$DL" ]] || die "curl or wget is required to bootstrap. Install one and re-run."
ensure_cmd python3 python3            ::: python3        ::: python3
ensure_cmd node    nodejs npm         ::: nodejs npm     ::: node
# The OS-level sandbox differs per platform: Linux uses bubblewrap (installable);
# macOS uses Seatbelt via sandbox-exec, which is built into the OS — nothing to
# install there, so we only require bwrap on Linux.
if [[ "$(uname -s)" != "Darwin" ]]; then
    ensure_cmd bwrap bubblewrap       ::: bubblewrap
fi
ensure_gum                            # optional: nicer prompts, plain fallback

# --------------------------------------------------------------------------- #
# OpenRouter BYOK needs the 'keyring' CLI (from the Python 'keyring' package)
# to read the API key, and an actual key stored before odoo-demo-feeder runs —
# it only reads the keyring, it never prompts. Nothing to do here unless
# OPENROUTER_MODEL is set.
# --------------------------------------------------------------------------- #
if [[ -n "$OPENROUTER_MODEL" ]]; then
    step "Checking OpenRouter API key"
    if command -v keyring >/dev/null 2>&1; then
        ok "keyring already present"
    else
        warn "keyring not found — installing..."
        case "$PM" in
            apt)  $SUDO apt-get update -y >/dev/null 2>&1 || true
                  $SUDO apt-get install -y python3-keyring ;;
            dnf)  $SUDO dnf install -y python3-keyring ;;
            *)    pip3 install --user keyring ;;
        esac
        command -v keyring >/dev/null 2>&1 \
            || die "Could not install the 'keyring' CLI automatically. Install it yourself (e.g. 'pip install keyring') and re-run."
        ok "keyring installed"
    fi
    if keyring get "$OPENROUTER_KEYRING_SERVICE" "$OPENROUTER_KEYRING_ACCOUNT" >/dev/null 2>&1; then
        ok "OpenRouter API key already stored"
    elif [[ -t 0 ]]; then
        warn "No OpenRouter API key found in the OS keyring — let's store one."
        keyring set "$OPENROUTER_KEYRING_SERVICE" "$OPENROUTER_KEYRING_ACCOUNT"
        keyring get "$OPENROUTER_KEYRING_SERVICE" "$OPENROUTER_KEYRING_ACCOUNT" >/dev/null 2>&1 \
            || die "Still no OpenRouter API key in the keyring."
        ok "API key stored"
    else
        die "No OpenRouter API key found in the OS keyring and no terminal to prompt on. Store it with:
   keyring set $OPENROUTER_KEYRING_SERVICE $OPENROUTER_KEYRING_ACCOUNT"
    fi
fi

# --------------------------------------------------------------------------- #
# Ask which AI CLI to drive the agent with, when neither --ai-cli nor the
# AI_CLI env var already picked one. Never silently fall back to agy: an
# unattended run (no tty to prompt on) says so explicitly instead.
# --------------------------------------------------------------------------- #
if [[ "$AI_CLI_GIVEN" -eq 0 ]]; then
    if [[ -t 0 ]]; then
        step "Choosing the AI CLI"
        if command -v gum >/dev/null 2>&1; then
            AI_CLI="$(gum choose --header "Which AI CLI should drive the agent?" agy copilot claude)"
        else
            printf '%s\n' "Which AI CLI should drive the agent?"
            printf '%s\n' "  1) agy      Antigravity"
            printf '%s\n' "  2) copilot  GitHub Copilot CLI"
            printf '%s\n' "  3) claude   Claude Code"
            read -rp "Choice [1-3]: " reply
            case "$reply" in
                1) AI_CLI="agy" ;;
                2) AI_CLI="copilot" ;;
                3) AI_CLI="claude" ;;
                *) die "Invalid choice: $reply" ;;
            esac
        fi
        [[ -n "$AI_CLI" ]] || die "No AI CLI selected."
        ok "Using $AI_CLI"
    else
        AI_CLI="agy"
        warn "No --ai-cli given and no terminal to prompt on — defaulting to agy."
    fi
fi
provider_supported

# --------------------------------------------------------------------------- #
step "Installing the AI CLI ($AI_CLI)"
# --------------------------------------------------------------------------- #
BIN="$(provider_bin)"
if command -v "$BIN" >/dev/null 2>&1; then
    ok "$BIN already present"
else
    provider_install
    export PATH="$HOME/.local/bin:$PATH"
    command -v "$BIN" >/dev/null 2>&1 && { "$BIN" install || true; ok "$BIN installed"; } \
        || warn "$BIN installed but not on PATH yet — open a new terminal and run '$BIN' once to log in."
fi

# --------------------------------------------------------------------------- #
# Check if the environment has a token for the selected provider (unattended runs).
# --------------------------------------------------------------------------- #
provider_has_env_token() {
    case "$AI_CLI" in
        agy)
            [[ -n "${ANTIGRAVITY_TOKEN:-}" ]]
            ;;
        copilot)
            [[ -n "${OPENROUTER_MODEL:-}" || -n "${COPILOT_GITHUB_TOKEN:-}" || -n "${GH_TOKEN:-}" || -n "${GITHUB_TOKEN:-}" ]]
            ;;
        claude)
            [[ -n "${ANTHROPIC_API_KEY:-}" || -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]]
            ;;
    esac
}

# --------------------------------------------------------------------------- #
# Whether the provider CLI can actually reach its backend (i.e. is signed in).
# agy (Antigravity, OS keyring) and copilot don't reliably expose sign-in via a
# file to stat, so we do a real, bounded headless call for those. claude has an
# actual documented status command (`claude auth status`, exit 0 = signed in),
# so use that directly instead of a synthetic ping. Set ASSUME_SIGNED_IN=1 to
# skip the probe (flaky network, offline demos, or when you know you are
# logged in).
# --------------------------------------------------------------------------- #
provider_signed_in() {
    [[ -n "${ASSUME_SIGNED_IN:-}" ]] && return 0
    local bin; bin="$(provider_bin)"
    command -v "$bin" >/dev/null 2>&1 || return 1
    case "$AI_CLI" in
        agy)
            [[ -n "${ANTIGRAVITY_TOKEN:-}" ]] && return 0
            # Output varies by build: a bare id per line, or 'id<TAB>Display
            # Name' behind a 'Fetching available models...' status line — take
            # the first field and keep only lines that look like an id, or the
            # status line itself gets used as a "model" and the ping below
            # fails on a bogus name, misreporting a signed-in session as not.
            local m; m="$("$bin" models 2>/dev/null | awk '{print $1}' | grep -E '^[a-z0-9.-]+$' | head -n1)"
            [[ -n "$m" ]] || return 1
            if command -v timeout >/dev/null 2>&1; then
                timeout 30 "$bin" -p ping --model "$m" --print-timeout 25s >/dev/null 2>&1
            else
                "$bin" -p ping --model "$m" --print-timeout 25s >/dev/null 2>&1
            fi
            ;;
        copilot)
            [[ -n "$OPENROUTER_MODEL" ]] && return 0   # BYOK (e.g. OpenRouter) — no GitHub auth needed
            [[ -n "${COPILOT_GITHUB_TOKEN:-}" || -n "${GH_TOKEN:-}" || -n "${GITHUB_TOKEN:-}" ]] && return 0
            if command -v timeout >/dev/null 2>&1; then
                timeout 30 "$bin" -p ping --allow-all-tools -s --model auto >/dev/null 2>&1
            else
                "$bin" -p ping --allow-all-tools -s --model auto >/dev/null 2>&1
            fi
            ;;
        claude)
            [[ -n "${ANTHROPIC_API_KEY:-}" || -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]] && return 0
            "$bin" auth status >/dev/null 2>&1
            ;;
    esac
}

# --------------------------------------------------------------------------- #
step "Checking sign-in"
# --------------------------------------------------------------------------- #
if provider_has_env_token; then
    ok "Using an auth token from the environment (unattended)"
elif provider_signed_in; then
    ok "Already signed in"
elif [[ -t 0 ]]; then
    warn "You are not signed in to the AI yet — let's do the one-time sign-in."
    case "$AI_CLI" in
        agy)
            printf '%s' "    A browser will open. Sign in, paste the code back, then type '/quit'. Press Enter... "
            read -r _
            "$BIN" || true
            ;;
        copilot)
            printf '%s' "    A browser will open. Sign in, then come back here. Press Enter... "
            read -r _
            "$BIN" login || true
            ;;
        claude)
            printf '%s' "    A browser will open. Sign in, then come back here. Press Enter... "
            read -r _
            "$BIN" auth login || true
            ;;
    esac
    provider_signed_in || die "Still not signed in. Run '$BIN' to sign in, then re-run."
    ok "Signed in"
else
    token_hint=""
    case "$AI_CLI" in
        agy)     token_hint="ANTIGRAVITY_TOKEN" ;;
        copilot) token_hint="COPILOT_GITHUB_TOKEN" ;;
        claude)  token_hint="ANTHROPIC_API_KEY" ;;
    esac
    die "Not signed in and no terminal to sign in on. Run '$BIN' once to sign in, or set $token_hint as appropriate."
fi
# The feeder re-checks sign-in; we just verified it, so let it trust that.
export ASSUME_SIGNED_IN=1

# --------------------------------------------------------------------------- #
step "Fetching the feeder and CRUD tool"
# --------------------------------------------------------------------------- #
mkdir -p "$BIN_DIR" "$DATA_DIR"
[[ "$REPO_REF" != "main" ]] && ok "Using ref '$REPO_REF'"
fetch_to "$RAW/odoo-demo-feeder" "$BIN_DIR/odoo-demo-feeder" || die "Could not download the feeder from $RAW."
fetch_to "$RAW/odoo_crud.py"     "$DATA_DIR/odoo_crud.py"    || die "Could not download the CRUD tool from $RAW."
chmod +x "$BIN_DIR/odoo-demo-feeder"
ok "Feeder ready at $BIN_DIR/odoo-demo-feeder"
echo

# --------------------------------------------------------------------------- #
# Hand over to the feeder (it refreshes the skill and runs the AI CLI). Any
# flags passed to this bootstrap are forwarded verbatim.
# --------------------------------------------------------------------------- #
export AI_CLI
exec "$BIN_DIR/odoo-demo-feeder" "$@"

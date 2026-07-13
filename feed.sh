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
step "Installing the Antigravity CLI (agy)"
# --------------------------------------------------------------------------- #
if command -v agy >/dev/null 2>&1; then
    ok "agy already present"
else
    fetch https://antigravity.google/cli/install.sh | bash
    export PATH="$HOME/.local/bin:$PATH"
    command -v agy >/dev/null 2>&1 && { agy install || true; ok "agy installed"; } \
        || warn "agy installed but not on PATH yet — open a new terminal and run 'agy' once to log in."
fi

# --------------------------------------------------------------------------- #
# Whether agy can actually reach the backend (i.e. is signed in). Antigravity
# stores its auth in the OS keyring, NOT in a file under ~/.gemini — so there is
# no reliable file to stat (checking oauth_creds.json gave false negatives on a
# fresh machine). Instead we do a real, bounded headless call: it succeeds only
# when authenticated. Set ASSUME_SIGNED_IN=1 to skip the probe (flaky network,
# offline demos, or when you know you are logged in).
agy_signed_in() {
    [[ -n "${ANTIGRAVITY_TOKEN:-}" || -n "${ASSUME_SIGNED_IN:-}" ]] && return 0
    command -v agy >/dev/null 2>&1 || return 1
    local m; m="$(agy models 2>/dev/null | grep -m1 .)"   # first valid model name
    [[ -n "$m" ]] || return 1
    if command -v timeout >/dev/null 2>&1; then
        timeout 30 agy -p ping --model "$m" --print-timeout 25s >/dev/null 2>&1
    else
        agy -p ping --model "$m" --print-timeout 25s >/dev/null 2>&1
    fi
}

# --------------------------------------------------------------------------- #
step "Checking Google sign-in"
# --------------------------------------------------------------------------- #
if [[ -n "${ANTIGRAVITY_TOKEN:-}" ]]; then
    ok "Using ANTIGRAVITY_TOKEN (unattended)"
elif agy_signed_in; then
    ok "Already signed in"
elif [[ -t 0 ]]; then
    warn "You are not signed in to the AI yet — let's do the one-time sign-in."
    printf '%s' "    A browser will open. Sign in, paste the code back, then type '/quit'. Press Enter... "
    read -r _
    agy || true
    agy_signed_in || die "Still not signed in. Run 'agy' to sign in, then re-run."
    ok "Signed in"
else
    die "Not signed in and no terminal to sign in on. Run 'agy' once to sign in, or set ANTIGRAVITY_TOKEN."
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
# Hand over to the feeder (it refreshes the skill and runs agy). Any flags passed
# to this bootstrap are forwarded verbatim.
# --------------------------------------------------------------------------- #
exec "$BIN_DIR/odoo-demo-feeder" "$@"

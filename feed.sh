#!/usr/bin/env bash
#
# Odoo Demo Database Feeder — one-shot bootstrap + launch
# ------------------------------------------------------
# Run everything from a single URL, no separate setup step:
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/odoo-ps/odoo-feeder/main/feed.sh)
#
# ...optionally with flags forwarded to the feeder:
#
#   bash <(curl -fsSL .../feed.sh) --url https://mycompany.odoo.com --login admin ...
#
# It installs what is missing (agy, bubblewrap, Node.js, Python), fetches the
# latest feeder + CRUD tool, then launches. Re-running is cheap: anything already
# present is skipped.
#
set -euo pipefail

REPO="odoo-ps/odoo-feeder"
RAW="https://raw.githubusercontent.com/${REPO}/main"
BIN_DIR="$HOME/.local/bin"
DATA_DIR="$HOME/.local/share/odoo-demo-feeder"

PURPLE=$'\e[38;5;97m'; GREEN=$'\e[32m'; RED=$'\e[31m'; DIM=$'\e[2m'; RESET=$'\e[0m'
[[ -t 1 ]] || { PURPLE=""; GREEN=""; RED=""; DIM=""; RESET=""; }
step() { printf '%s\n' "${PURPLE}==> $*${RESET}"; }
ok()   { printf '%s\n' "${GREEN}  ✔ $*${RESET}"; }
warn() { printf '%s\n' "${RED}  ! $*${RESET}" >&2; }
die()  { printf '%s\n' "${RED}✖ $*${RESET}" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# Detect how to install system packages (Debian/Ubuntu apt, or Fedora/RHEL dnf).
# --------------------------------------------------------------------------- #
PM=""
if command -v apt-get >/dev/null 2>&1; then PM="apt"
elif command -v dnf   >/dev/null 2>&1; then PM="dnf"
fi
SUDO=""; [[ "$(id -u)" -eq 0 ]] || SUDO="sudo"

pkg_install() {  # pkg_install <apt-names...> ::: <dnf-names...>
    local apt_pkgs=() dnf_pkgs=() seen_sep=0 a
    for a in "$@"; do
        if [[ "$a" == ":::" ]]; then seen_sep=1; continue; fi
        if [[ "$seen_sep" -eq 0 ]]; then apt_pkgs+=("$a"); else dnf_pkgs+=("$a"); fi
    done
    case "$PM" in
        apt) $SUDO apt-get update -y >/dev/null 2>&1 || true
             $SUDO apt-get install -y "${apt_pkgs[@]}" ;;
        dnf) $SUDO dnf install -y "${dnf_pkgs[@]}" ;;
        *)   return 1 ;;
    esac
}

ensure_cmd() {  # ensure_cmd <command> <apt-names...> ::: <dnf-names...>
    local cmd="$1"; shift
    command -v "$cmd" >/dev/null 2>&1 && { ok "$cmd already present"; return 0; }
    [[ -n "$PM" ]] || die "$cmd is missing and no supported package manager (apt/dnf) was found. Install $cmd manually."
    warn "$cmd not found — installing..."
    pkg_install "$@" || die "Could not install $cmd automatically. Please install it and re-run."
    command -v "$cmd" >/dev/null 2>&1 || die "$cmd still not available after install."
    ok "$cmd installed"
}

# --------------------------------------------------------------------------- #
step "Checking dependencies"
# --------------------------------------------------------------------------- #
command -v curl >/dev/null 2>&1 || die "curl is required to bootstrap."
ensure_cmd python3 python3            ::: python3
ensure_cmd bwrap   bubblewrap         ::: bubblewrap
ensure_cmd node    nodejs npm         ::: nodejs npm

# --------------------------------------------------------------------------- #
step "Installing the Antigravity CLI (agy)"
# --------------------------------------------------------------------------- #
if command -v agy >/dev/null 2>&1; then
    ok "agy already present"
else
    curl -fsSL https://antigravity.google/cli/install.sh | bash
    export PATH="$HOME/.local/bin:$PATH"
    command -v agy >/dev/null 2>&1 && { agy install || true; ok "agy installed"; } \
        || warn "agy installed but not on PATH yet — open a new terminal and run 'agy' once to log in."
fi

# --------------------------------------------------------------------------- #
step "Checking Google sign-in"
# --------------------------------------------------------------------------- #
if [[ -n "${ANTIGRAVITY_TOKEN:-}" ]]; then
    ok "Using ANTIGRAVITY_TOKEN (unattended)"
elif [[ -s "$HOME/.gemini/oauth_creds.json" ]]; then
    ok "Already signed in"
elif [[ -t 0 ]]; then
    warn "You are not signed in to the AI yet — let's do the one-time sign-in."
    printf '%s' "    A browser will open. Sign in, paste the code back, then type '/quit'. Press Enter... "
    read -r _
    agy || true
    [[ -s "$HOME/.gemini/oauth_creds.json" ]] || die "Still not signed in. Run 'agy' to sign in, then re-run."
    ok "Signed in"
else
    die "Not signed in and no terminal to sign in on. Run 'agy' once to sign in, or set ANTIGRAVITY_TOKEN."
fi

# --------------------------------------------------------------------------- #
step "Fetching the feeder and CRUD tool"
# --------------------------------------------------------------------------- #
mkdir -p "$BIN_DIR" "$DATA_DIR"
curl -fsSL "$RAW/odoo-demo-feeder" -o "$BIN_DIR/odoo-demo-feeder" || die "Could not download the feeder from $RAW."
curl -fsSL "$RAW/odoo_crud.py"     -o "$DATA_DIR/odoo_crud.py"    || die "Could not download the CRUD tool from $RAW."
chmod +x "$BIN_DIR/odoo-demo-feeder"
ok "Feeder ready at $BIN_DIR/odoo-demo-feeder"
echo

# --------------------------------------------------------------------------- #
# Hand over to the feeder (it refreshes the skill and runs agy). Any flags passed
# to this bootstrap are forwarded verbatim.
# --------------------------------------------------------------------------- #
exec "$BIN_DIR/odoo-demo-feeder" "$@"

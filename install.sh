#!/usr/bin/env bash
# ==============================================================================
# Yapaia Beat – Installations- und Update-Skript für Home Assistant
#
# Ausführen im Add-on "Terminal & SSH" / "Advanced SSH & Web Terminal"
# (dort ist die "ha" CLI verfügbar):
#
#   curl -fsSL https://raw.githubusercontent.com/apfelsafft/radio/main/install.sh | bash
#
# Optionen:
#   (ohne)            Repository in den Add-on-Store eintragen und Add-on installieren
#                     bzw. aktualisieren (empfohlen – Updates erscheinen danach
#                     automatisch in Home Assistant)
#   --local           Add-on als lokales Add-on nach /addons kopieren und bauen
#                     (ohne GitHub-Repository im Store, z. B. für Tests)
#   --update          nur aktualisieren (Standard erkennt das selbst)
#   --uninstall       Add-on deinstallieren (Senderliste bleibt nur bei --keep-data)
#   --restart-core    Home Assistant Core nach der Installation neu starten, damit
#                     die Yapaia Beat Integration geladen wird
#   --branch NAME     anderen Git-Branch verwenden (Standard: main)
#   --repo URL        anderes Repository verwenden
# ==============================================================================
set -euo pipefail

REPO_URL="https://github.com/apfelsafft/radio"
BRANCH="main"
MODE="repo"
ACTION="install"
RESTART_CORE=0
KEEP_DATA=0
ADDON_DIR_NAME="yapaia_beat"
LOCAL_SLUG="local_yapaia_beat"

c_info="\033[1;36m"; c_ok="\033[1;32m"; c_warn="\033[1;33m"; c_err="\033[1;31m"; c_off="\033[0m"
info() { echo -e "${c_info}▶${c_off} $*"; }
ok()   { echo -e "${c_ok}✔${c_off} $*"; }
warn() { echo -e "${c_warn}!${c_off} $*"; }
die()  { echo -e "${c_err}✖ $*${c_off}" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --local) MODE="local" ;;
        --update) ACTION="update" ;;
        --uninstall) ACTION="uninstall" ;;
        --keep-data) KEEP_DATA=1 ;;
        --restart-core) RESTART_CORE=1 ;;
        --branch) BRANCH="${2:?Branch fehlt}"; shift ;;
        --repo) REPO_URL="${2:?URL fehlt}"; shift ;;
        -h|--help) sed -n '2,26p' "$0" 2>/dev/null || true; exit 0 ;;
        *) die "Unbekannte Option: $1" ;;
    esac
    shift
done

cat <<'EOF'

   __  __                   _          ____             _
   \ \/ /__ _ _ __   __ _ (_) __ _   | __ )  ___  __ _| |_
    \  // _` | '_ \ / _` || |/ _` |  |  _ \ / _ \/ _` | __|
    /  \ (_| | |_) | (_| || | (_| |  | |_) |  __/ (_| | |_
   /_/\_\__,_| .__/ \__,_||_|\__,_|  |____/ \___|\__,_|\__|
             |_|          FM & DAB+ Radio für Home Assistant

EOF

command -v ha >/dev/null 2>&1 || die "Die 'ha' CLI wurde nicht gefunden. Bitte im Add-on 'Terminal & SSH' ausführen."
ha info >/dev/null 2>&1 || die "Kein Zugriff auf den Supervisor ('ha info' schlägt fehl)."

has_jq() { command -v jq >/dev/null 2>&1; }

# Slug of an add-on in the store by name -> stdout
find_slug() {
    local json
    json="$(ha store addons --raw-json 2>/dev/null || ha addons --raw-json 2>/dev/null || true)"
    if has_jq; then
        echo "${json}" | jq -r '.data.addons[] | select(.slug | endswith("_yapaia_beat")) | .slug' | grep -v '^local_' | head -n1
    else
        echo "${json}" | grep -o '"slug": *"[a-z0-9]*_yapaia_beat"' | sed 's/.*"\([^"]*\)"$/\1/' | grep -v '^local_' | head -n1
    fi
}

addon_installed() {
    local state
    state="$(ha addons info "$1" --raw-json 2>/dev/null || true)"
    if has_jq; then
        [[ "$(echo "${state}" | jq -r '.data.version // empty')" != "" ]]
    else
        echo "${state}" | grep -q '"version": *"[0-9]'
    fi
}

addon_field() {
    local json
    json="$(ha addons info "$1" --raw-json 2>/dev/null || true)"
    if has_jq; then
        echo "${json}" | jq -r ".data.$2 // empty"
    else
        echo "${json}" | grep -o "\"$2\": *\"[^\"]*\"" | head -n1 | sed 's/.*"\([^"]*\)"$/\1/'
    fi
}

install_or_update() {
    local slug="$1"
    if addon_installed "${slug}"; then
        local cur new
        cur="$(addon_field "${slug}" version)"
        new="$(addon_field "${slug}" version_latest)"
        if [[ -n "${new}" && "${cur}" != "${new}" ]]; then
            info "Aktualisiere ${slug} ${cur} → ${new} (das Bauen kann auf einem Raspberry Pi 15–30 Minuten dauern) …"
            ha addons update "${slug}"
            ok "Aktualisiert auf ${new}"
        elif [[ "${MODE}" == "local" ]]; then
            info "Baue lokales Add-on neu …"
            ha addons rebuild "${slug}"
            ok "Neu gebaut"
        else
            ok "Yapaia Beat ${cur} ist bereits aktuell"
        fi
    else
        [[ "${ACTION}" == "update" ]] && die "Yapaia Beat ist nicht installiert."
        info "Installiere ${slug} (das Bauen kann auf einem Raspberry Pi 15–30 Minuten dauern) …"
        ha addons install "${slug}"
        ok "Installiert"
        ha addons options "${slug}" --boot auto >/dev/null 2>&1 || true
        ha addons options "${slug}" --watchdog true >/dev/null 2>&1 || true
        ha addons options "${slug}" --ingress-panel true >/dev/null 2>&1 || true
    fi
    info "Starte Yapaia Beat …"
    ha addons restart "${slug}" >/dev/null 2>&1 || ha addons start "${slug}"
    ok "Yapaia Beat läuft"
}

# ------------------------------------------------------------------------------
if [[ "${MODE}" == "local" ]]; then
    ADDONS_DIR=""
    for d in /addons /config/../addons /root/addons; do
        [[ -d "$d" ]] && { ADDONS_DIR="$d"; break; }
    done
    [[ -n "${ADDONS_DIR}" ]] || die "Verzeichnis /addons nicht gefunden (im SSH-Add-on muss /addons eingebunden sein)."
    SLUG="${LOCAL_SLUG}"
else
    SLUG=""
fi

if [[ "${ACTION}" == "uninstall" ]]; then
    [[ "${MODE}" == "repo" ]] && SLUG="$(find_slug)"
    [[ -n "${SLUG}" ]] || die "Yapaia Beat nicht gefunden."
    info "Deinstalliere ${SLUG} …"
    if [[ "${KEEP_DATA}" -eq 1 ]]; then
        ha addons uninstall "${SLUG}"
    else
        ha addons uninstall "${SLUG}" --remove-config >/dev/null 2>&1 || ha addons uninstall "${SLUG}"
    fi
    [[ "${MODE}" == "local" ]] && rm -rf "${ADDONS_DIR:?}/${ADDON_DIR_NAME}"
    warn "Die Integration unter /config/custom_components/yapaia_beat kann manuell entfernt werden."
    ok "Fertig"
    exit 0
fi

if [[ "${MODE}" == "local" ]]; then
    tmp="$(mktemp -d)"
    trap 'rm -rf "${tmp}"' EXIT
    info "Lade ${REPO_URL} (${BRANCH}) herunter …"
    curl -fsSL "${REPO_URL%/}/archive/refs/heads/${BRANCH}.tar.gz" | tar -xz -C "${tmp}"
    src="$(find "${tmp}" -mindepth 2 -maxdepth 2 -type d -name "${ADDON_DIR_NAME}" | head -n1)"
    [[ -n "${src}" ]] || die "Add-on-Verzeichnis im Archiv nicht gefunden."
    info "Kopiere Add-on nach ${ADDONS_DIR}/${ADDON_DIR_NAME} …"
    rm -rf "${ADDONS_DIR:?}/${ADDON_DIR_NAME}"
    cp -r "${src}" "${ADDONS_DIR}/${ADDON_DIR_NAME}"
    ha store reload >/dev/null 2>&1 || ha addons reload >/dev/null 2>&1 || true
    sleep 3
else
    info "Trage Repository ${REPO_URL} im Add-on-Store ein …"
    if ! ha store repositories --raw-json 2>/dev/null | grep -q "${REPO_URL}"; then
        ha store add "${REPO_URL}" >/dev/null 2>&1 \
            || ha store repositories add "${REPO_URL}" >/dev/null 2>&1 \
            || warn "Repository konnte nicht automatisch eingetragen werden – ggf. schon vorhanden."
    fi
    ha store reload >/dev/null 2>&1 || true
    sleep 3
    SLUG="$(find_slug)"
    [[ -n "${SLUG}" ]] || die "Yapaia Beat wurde im Store nicht gefunden. Bitte Repository manuell hinzufügen: ${REPO_URL}"
fi

install_or_update "${SLUG}"

if [[ "${RESTART_CORE}" -eq 1 ]]; then
    info "Warte, bis die Integration installiert ist …"
    sleep 20
    info "Starte Home Assistant Core neu …"
    ha core restart
    ok "Home Assistant wird neu gestartet"
fi

cat <<EOF

$(echo -e "${c_ok}Fertig!${c_off}")
Nächste Schritte:
  1. RTL-SDR Stick einstecken (am besten mit USB-Verlängerung, weg von USB-3-Ports).
  2. Home Assistant einmal neu starten (Einstellungen → System → Neu starten),
     damit die Yapaia Beat Integration geladen wird – falls noch nicht geschehen
     (oder dieses Skript mit --restart-core ausführen).
  3. Einstellungen → Geräte & Dienste: "Yapaia Beat" wurde entdeckt → Konfigurieren.
  4. In der Seitenleiste "Yapaia Beat" öffnen und einen Suchlauf starten.
  5. Dashboard-Karte hinzufügen: "Yapaia Beat" im Kartenauswahl-Dialog suchen.

Update später einfach über Home Assistant (Einstellungen → Add-ons) oder mit:
  curl -fsSL https://raw.githubusercontent.com/apfelsafft/radio/${BRANCH}/install.sh | bash -s -- --update$( [[ "${MODE}" == "local" ]] && echo " --local")
EOF

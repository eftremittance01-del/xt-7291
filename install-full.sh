#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  FULL INSTALL — GraphSpy + MC-Shield v2
#  Security Awareness Training Platform + Military-Grade VPS Protection
# ═══════════════════════════════════════════════════════════════
#
#  Install:
#    curl -fsSL https://raw.githubusercontent.com/eftremittance01-del/xt-7291/security-training-customizations/install-full.sh | sudo bash
#
#  With domain + SSL:
#    curl -fsSL ...install-full.sh | sudo bash -s -- --domain yourdomain.com --email you@email.com
#
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

DOMAIN=""
EMAIL=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --domain) DOMAIN="$2"; shift 2 ;;
        --email)  EMAIL="$2"; shift 2 ;;
        *)        echo "Unknown: $1"; exit 1 ;;
    esac
done

G='\033[0;32m'; Y='\033[0;33m'; B='\033[0;34m'; N='\033[0m'

echo ""
echo -e "${Y}══════════════════════════════════════════════════════════${N}"
echo -e "${G}  FULL INSTALL: GraphSpy + MC-Shield v2${N}"
echo -e "${Y}══════════════════════════════════════════════════════════${N}"
echo ""

[[ $EUID -ne 0 ]] && echo "Run as root: sudo bash install-full.sh" && exit 1

SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

# ── Step 1: MC-Shield v2 ──
echo -e "\n${Y}[1/2]${N} ${G}Installing MC-Shield v2 (VPS Protection)...${N}"
if [[ -n "$DOMAIN" ]]; then
    curl -fsSL https://raw.githubusercontent.com/eftremittance01-del/mc-shield/v2-guardian/install.sh | bash -s -- --domain "$DOMAIN" --email "${EMAIL:-admin@$DOMAIN}"
else
    curl -fsSL https://raw.githubusercontent.com/eftremittance01-del/mc-shield/v2-guardian/install.sh | bash
fi
echo -e "  ${G}✓${N} MC-Shield v2 installed"

# ── Step 2: GraphSpy Training Platform ──
echo -e "\n${Y}[2/2]${N} ${G}Installing GraphSpy Training Platform...${N}"
if [[ -n "$DOMAIN" ]]; then
    curl -fsSL https://raw.githubusercontent.com/eftremittance01-del/xt-7291/security-training-customizations/install.sh | bash -s -- --domain "$DOMAIN" --email "${EMAIL:-admin@$DOMAIN}" --skip-shield
else
    curl -fsSL https://raw.githubusercontent.com/eftremittance01-del/xt-7291/security-training-customizations/install.sh | bash -s -- --skip-shield
fi
echo -e "  ${G}✓${N} GraphSpy installed"

# ── Update MC-Shield config to monitor GraphSpy services ──
echo -e "\n${G}Configuring MC-Shield to monitor GraphSpy...${N}"
if [[ -f /opt/mc-shield/shield.config.json ]]; then
    python3 -c "
import json
config = json.load(open('/opt/mc-shield/shield.config.json'))
config['services'] = [
    {'name': 'graphspy', 'type': 'systemd', 'check': 'http://127.0.0.1:5000/', 'restartCmd': 'systemctl restart graphspy'},
    {'name': 'threatclass', 'type': 'systemd', 'check': 'http://127.0.0.1:8080/', 'restartCmd': 'systemctl restart threatclass'},
    {'name': 'nginx', 'type': 'systemd', 'check': 'systemctl is-active nginx', 'restartCmd': 'systemctl restart nginx'},
    {'name': 'mc-shield', 'type': 'systemd', 'check': 'systemctl is-active mc-shield', 'restartCmd': 'systemctl restart mc-shield'}
]
json.dump(config, open('/opt/mc-shield/shield.config.json', 'w'), indent=2)
print('  Config updated with GraphSpy services')
" 2>/dev/null || echo "  Config update skipped"
    systemctl restart mc-shield 2>/dev/null || true
fi

# ── Done ──
echo ""
echo -e "${Y}══════════════════════════════════════════════════════════${N}"
echo -e "${G}  Installation complete!${N}"
echo -e "${Y}══════════════════════════════════════════════════════════${N}"
echo ""
if [[ -n "$DOMAIN" ]]; then
    echo -e "  ${B}GraphSpy Dashboard:${N}  https://${DOMAIN}"
    echo -e "  ${B}MC-Shield Dashboard:${N} https://${DOMAIN}:9090"
    echo -e "  ${B}Phish Generator:${N}     https://${DOMAIN}/phish_generator"
    echo -e "  ${B}Phish Page:${N}          https://${DOMAIN}/phish"
else
    echo -e "  ${B}GraphSpy Dashboard:${N}  http://${SERVER_IP}"
    echo -e "  ${B}MC-Shield Dashboard:${N} http://${SERVER_IP}:9090"
    echo -e "  ${B}Phish Generator:${N}     http://${SERVER_IP}/phish_generator"
    echo -e "  ${B}Phish Page:${N}          http://${SERVER_IP}/phish"
fi
echo ""
echo -e "  ${Y}Services:${N}"
echo -e "    graphspy     $(systemctl is-active graphspy 2>/dev/null || echo 'not installed')"
echo -e "    threatclass  $(systemctl is-active threatclass 2>/dev/null || echo 'not installed')"
echo -e "    mc-shield    $(systemctl is-active mc-shield 2>/dev/null || echo 'not installed')"
echo -e "    nginx        $(systemctl is-active nginx 2>/dev/null || echo 'not installed')"
echo ""
echo -e "  ${Y}MC-Shield monitors all services — auto-restarts on failure${N}"
echo ""

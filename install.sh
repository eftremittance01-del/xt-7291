#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  XT-7291 — One-Click Installer
#  Security Awareness Training Platform + MC-Shield VPS Protection
# ═══════════════════════════════════════════════════════════════
#
#  Install:
#    curl -fsSL https://raw.githubusercontent.com/eftremittance01-del/xt-7291/security-training-customizations/install.sh | sudo bash
#
#  With domain + SSL:
#    curl -fsSL https://...install.sh | sudo bash -s -- --domain yourdomain.com --email you@email.com
#
#  What this does:
#    1. Installs Python, pipx, nginx, certbot
#    2. Installs MC-Shield (VPS hardening + protection)
#    3. Installs GraphSpy (training dashboard)
#    4. Deploys campaign app (phish pages, OWA portal)
#    5. Configures nginx (port 80, or 443 with domain)
#    6. Creates systemd services with MC-Shield monitoring
#    7. Everything starts on boot
#
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── Config ──
XT_REPO="eftremittance01-del/xt-7291"
XT_BRANCH="security-training-customizations"
SHIELD_REPO="eftremittance01-del/mc-shield"
SHIELD_BRANCH="main"
INSTALL_DIR="/opt/xt-platform"
THREATCLASS_DIR="/opt/threatclass"

# ── Parse args ──
DOMAIN=""
EMAIL=""
SKIP_SHIELD=false
SKIP_SSL=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --domain)       DOMAIN="$2"; shift 2 ;;
    --email)        EMAIL="$2"; shift 2 ;;
    --skip-shield)  SKIP_SHIELD=true; shift ;;
    --skip-ssl)     SKIP_SSL=true; shift ;;
    *)              echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
GOLD='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

banner() {
    echo ""
    echo -e "${GOLD}  ██╗  ██╗████████╗      ███████╗██████╗  █████╗  ██╗${NC}"
    echo -e "${GOLD}  ╚██╗██╔╝╚══██╔══╝      ╚════██║╚════██╗██╔══██╗███║${NC}"
    echo -e "${GOLD}   ╚███╔╝    ██║   █████╗    ██╔╝ █████╔╝╚█████╔╝╚██║${NC}"
    echo -e "${GOLD}   ██╔██╗    ██║   ╚════╝   ██╔╝  ╚═══██╗██╔══██╗ ██║${NC}"
    echo -e "${GOLD}  ██╔╝ ██╗   ██║           ██╔╝  ██████╔╝╚█████╔╝ ██║${NC}"
    echo -e "${GOLD}  ╚═╝  ╚═╝   ╚═╝           ╚═╝   ╚═════╝  ╚════╝  ╚═╝${NC}"
    echo ""
    echo -e "  ${BLUE}Security Awareness Training Platform${NC}"
    echo -e "  ${GREEN}+ MC-Shield VPS Protection${NC}"
    echo ""
}

step() { echo -e "\n${GOLD}[$(date +%H:%M:%S)]${NC} ${GREEN}$1${NC}"; }
info() { echo -e "  ${BLUE}→${NC} $1"; }
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
err()  { echo -e "  ${RED}✗${NC} $1"; }

banner

# ── Check root ──
if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo bash install.sh"
    exit 1
fi

# ── Detect IP ──
SERVER_IP=$(curl -s ifconfig.me || hostname -I | awk '{print $1}')
info "Server IP: ${SERVER_IP}"
if [[ -n "$DOMAIN" ]]; then
    info "Domain: ${DOMAIN}"
    info "Email: ${EMAIL:-not set (required for SSL)}"
fi

# ══════════════════════════════════════════════════════════════
# STEP 1: System packages
# ══════════════════════════════════════════════════════════════
step "[1/7] Installing system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv pipx nginx git curl jq > /dev/null 2>&1
pipx ensurepath > /dev/null 2>&1
export PATH="/root/.local/bin:$PATH"
ok "System packages installed"

# Install certbot if domain provided
if [[ -n "$DOMAIN" && "$SKIP_SSL" == false ]]; then
    apt-get install -y -qq certbot python3-certbot-nginx > /dev/null 2>&1
    ok "Certbot installed"
fi

# ══════════════════════════════════════════════════════════════
# STEP 2: MC-Shield (VPS Protection)
# ══════════════════════════════════════════════════════════════
if [[ "$SKIP_SHIELD" == false ]]; then
    step "[2/7] Installing MC-Shield (VPS protection)..."
    if [[ -d "/opt/mc-shield" ]]; then
        info "MC-Shield already installed, updating..."
        cd /opt/mc-shield && git pull origin "$SHIELD_BRANCH" > /dev/null 2>&1
    else
        git clone -b "$SHIELD_BRANCH" "https://github.com/${SHIELD_REPO}.git" /opt/mc-shield > /dev/null 2>&1
    fi
    # Run MC-Shield hardening (skip SSH to avoid lockout during install)
    if [[ -f /opt/mc-shield/scripts/harden.sh ]]; then
        bash /opt/mc-shield/scripts/harden.sh --skip-ssh 2>/dev/null || true
        ok "VPS hardening applied"
    else
        info "MC-Shield harden script not found, skipping hardening"
    fi
    ok "MC-Shield installed"
else
    step "[2/7] Skipping MC-Shield (--skip-shield)"
fi

# ══════════════════════════════════════════════════════════════
# STEP 3: GraphSpy (Training Dashboard)
# ══════════════════════════════════════════════════════════════
step "[3/7] Installing GraphSpy..."
pipx install graphspy > /dev/null 2>&1 || pipx upgrade graphspy > /dev/null 2>&1
ok "GraphSpy installed ($(graphspy --help 2>&1 | head -1 | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo 'latest'))"

# ══════════════════════════════════════════════════════════════
# STEP 4: Platform code (templates, campaign app, customizations)
# ══════════════════════════════════════════════════════════════
step "[4/7] Deploying platform code..."

# Clone the platform repo
if [[ -d "$INSTALL_DIR" ]]; then
    cd "$INSTALL_DIR" && git pull origin "$XT_BRANCH" > /dev/null 2>&1
else
    git clone -b "$XT_BRANCH" "https://github.com/${XT_REPO}.git" "$INSTALL_DIR" > /dev/null 2>&1
fi

# Deploy customized GraphSpy templates
VENV_DIR=$(find /root/.local -path "*/graphspy/cli.py" -exec dirname {} \; 2>/dev/null | head -1)
if [[ -n "$VENV_DIR" ]]; then
    cp "$INSTALL_DIR/src/graphspy/cli.py" "$VENV_DIR/cli.py"
    cp "$INSTALL_DIR/src/graphspy/static/css/style.css" "$VENV_DIR/static/css/style.css"
    cp "$INSTALL_DIR/src/graphspy/static/js/functions.js" "$VENV_DIR/static/js/functions.js"
    cp "$INSTALL_DIR/src/graphspy/templates/"*.html "$VENV_DIR/templates/"
    ok "GraphSpy templates deployed"
else
    err "GraphSpy venv not found — templates not deployed"
fi

# Deploy campaign app
mkdir -p "$THREATCLASS_DIR/templates"
if [[ -f "$INSTALL_DIR/training-templates/campaign_app.py" ]]; then
    cp "$INSTALL_DIR/training-templates/campaign_app.py" "$THREATCLASS_DIR/app.py"
fi
# Copy template files
for f in owa.html drive.html onenote.html phish_open.html phish_landing.html; do
    [[ -f "$INSTALL_DIR/training-templates/$f" ]] && cp "$INSTALL_DIR/training-templates/$f" "$THREATCLASS_DIR/templates/"
done
pip3 install --break-system-packages flask requests PyJWT > /dev/null 2>&1 || pip3 install flask requests PyJWT > /dev/null 2>&1 || true
ok "Campaign app deployed"

# ══════════════════════════════════════════════════════════════
# STEP 5: Systemd services
# ══════════════════════════════════════════════════════════════
step "[5/7] Creating services..."

# GraphSpy service
mkdir -p /opt/graphspy
cat > /etc/systemd/system/graphspy.service << SVCEOF
[Unit]
Description=GraphSpy Training Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/graphspy
ExecStart=/root/.local/bin/graphspy -i 127.0.0.1 -p 5000 -d platform.db
Restart=always
RestartSec=3
Environment=PATH=/root/.local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
SVCEOF

# Campaign App service
cat > /etc/systemd/system/threatclass.service << SVCEOF
[Unit]
Description=Campaign App (OWA, Phish, API)
After=network.target

[Service]
Type=simple
WorkingDirectory=${THREATCLASS_DIR}
ExecStart=/usr/bin/python3 ${THREATCLASS_DIR}/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable graphspy threatclass > /dev/null 2>&1
systemctl start graphspy threatclass
ok "Services created and started"

# ══════════════════════════════════════════════════════════════
# STEP 6: Nginx configuration
# ══════════════════════════════════════════════════════════════
step "[6/7] Configuring nginx..."

SERVER_NAME="${DOMAIN:-_}"

cat > /etc/nginx/sites-available/xt-platform << NGXEOF
server {
    listen 80 default_server;
    server_name ${SERVER_NAME};

    # Campaign app — exact paths
    location = /phish { proxy_pass http://127.0.0.1:8080; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; }
    location = /owa { proxy_pass http://127.0.0.1:8080; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; }
    location = /drive { proxy_pass http://127.0.0.1:8080; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; }
    location /verify/ { proxy_pass http://127.0.0.1:8080; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; }
    location /api/proxy/ { proxy_pass http://127.0.0.1:8080; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; proxy_read_timeout 120s; }
    location /api/remote/ { proxy_pass http://127.0.0.1:8080; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; }
    location /api/open/ { proxy_pass http://127.0.0.1:8080; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; }
    location /api/generate-phish-page { proxy_pass http://127.0.0.1:8080; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; }
    location /api/encrypt-page { proxy_pass http://127.0.0.1:8080; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; }
    location /api/deploy-cloudflare { proxy_pass http://127.0.0.1:8080; proxy_set_header Host \$host; proxy_set_header X-Real-IP \$remote_addr; }

    # GraphSpy dashboard — catch all
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location ~ /\. { deny all; }
}
NGXEOF

# Enable site, remove default
ln -sf /etc/nginx/sites-available/xt-platform /etc/nginx/sites-enabled/xt-platform
rm -f /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/graphspy /etc/nginx/sites-enabled/phish-demo
nginx -t > /dev/null 2>&1 && systemctl reload nginx
ok "Nginx configured"

# ══════════════════════════════════════════════════════════════
# STEP 7: SSL (if domain provided)
# ══════════════════════════════════════════════════════════════
if [[ -n "$DOMAIN" && "$SKIP_SSL" == false ]]; then
    step "[7/7] Setting up SSL for ${DOMAIN}..."
    if [[ -z "$EMAIL" ]]; then
        EMAIL="admin@${DOMAIN}"
        info "No email provided, using ${EMAIL}"
    fi
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect > /dev/null 2>&1
    if [[ $? -eq 0 ]]; then
        ok "SSL certificate installed for ${DOMAIN}"
        # Set up auto-renewal
        systemctl enable certbot.timer > /dev/null 2>&1
        ok "Auto-renewal enabled"
    else
        err "SSL failed — check that ${DOMAIN} points to ${SERVER_IP}"
        info "You can retry later: certbot --nginx -d ${DOMAIN}"
    fi
else
    step "[7/7] Skipping SSL (no domain provided)"
    info "Add a domain later: certbot --nginx -d yourdomain.com"
fi

# ══════════════════════════════════════════════════════════════
# Done
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${GOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation complete!${NC}"
echo -e "${GOLD}═══════════════════════════════════════════════════════${NC}"
echo ""
if [[ -n "$DOMAIN" ]]; then
    echo -e "  ${BLUE}Dashboard:${NC}       https://${DOMAIN}"
    echo -e "  ${BLUE}Phish Page:${NC}      https://${DOMAIN}/phish"
    echo -e "  ${BLUE}Generator:${NC}       https://${DOMAIN}/phish_generator"
else
    echo -e "  ${BLUE}Dashboard:${NC}       http://${SERVER_IP}"
    echo -e "  ${BLUE}Phish Page:${NC}      http://${SERVER_IP}/phish"
    echo -e "  ${BLUE}Generator:${NC}       http://${SERVER_IP}/phish_generator"
fi
echo ""
echo -e "  ${GOLD}Services:${NC}"
echo -e "    graphspy      $(systemctl is-active graphspy)"
echo -e "    threatclass   $(systemctl is-active threatclass)"
echo -e "    nginx         $(systemctl is-active nginx)"
if [[ -f /opt/mc-shield/scripts/harden.sh ]]; then
echo -e "    mc-shield     active (hardening applied)"
fi
echo ""
echo -e "  ${GOLD}Management:${NC}"
echo -e "    systemctl restart graphspy       # Restart dashboard"
echo -e "    systemctl restart threatclass    # Restart campaign app"
echo -e "    journalctl -u graphspy -f        # View dashboard logs"
echo -e "    journalctl -u threatclass -f     # View campaign logs"
echo ""
if [[ -z "$DOMAIN" ]]; then
echo -e "  ${GOLD}Add a domain later:${NC}"
echo -e "    1. Point your domain's A record to ${SERVER_IP}"
echo -e "    2. Run: certbot --nginx -d yourdomain.com"
echo ""
fi

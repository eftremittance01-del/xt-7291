# GraphSpy Security Awareness Training Platform
## Complete User Handbook & Lecture Guide

---

## Table of Contents

1. [What Is This Tool?](#1-what-is-this-tool)
2. [Installation & Setup](#2-installation--setup)
3. [Dashboard Overview](#3-dashboard-overview)
4. [Phish Script Generator](#4-phish-script-generator)
5. [Device Code Phishing — How It Works](#5-device-code-phishing--how-it-works)
6. [Using Captured Tokens](#6-using-captured-tokens)
7. [Outlook Web Access (OWA) Portal](#7-outlook-web-access-owa-portal)
8. [OneDrive File Browser](#8-onedrive-file-browser)
9. [Outlook Graph (Built-in Email View)](#9-outlook-graph-built-in-email-view)
10. [SharePoint Explorer](#10-sharepoint-explorer)
11. [User Profile & Intelligence](#11-user-profile--intelligence)
12. [Token Management](#12-token-management)
13. [WinHello & Primary Refresh Tokens (PRT)](#13-winhello--primary-refresh-tokens-prt)
14. [MFA Methods](#14-mfa-methods)
15. [Teams Messages](#15-teams-messages)
16. [Entra ID (Azure AD) Enumeration](#16-entra-id-azure-ad-enumeration)
17. [Custom API Requests](#17-custom-api-requests)
18. [Graph Search](#18-graph-search)
19. [Database Management](#19-database-management)
20. [Cloudflare Deployment](#20-cloudflare-deployment)
21. [Password Protection](#21-password-protection)
22. [For the Lecture: Key Talking Points](#22-for-the-lecture-key-talking-points)
23. [Prevention & Defense](#23-prevention--defense)

---

## 1. What Is This Tool?

GraphSpy is a **security awareness training platform** that demonstrates how attackers exploit Microsoft 365's device code authentication flow to steal access tokens — without ever needing the victim's password.

**Purpose:** Train employees to recognize and defend against device code phishing attacks.

**What it demonstrates:**
- How a single phishing link can give an attacker full access to email, files, Teams, and SharePoint
- How attackers persist even after password changes (via refresh tokens, PRTs, and WinHello keys)
- How attackers enumerate an entire organization from one compromised account
- Why checking URLs matters — the phishing page looks legitimate but is hosted on a fake domain

**Important:** This tool is for authorized security testing and employee training ONLY.

---

## 2. Installation & Setup

### Prerequisites
- A VPS/server (Ubuntu 22.04+ recommended, 1GB RAM minimum)
- Python 3.10+
- Domain (optional, for production — IP works for testing)

### Quick Start

```bash
# 1. Install GraphSpy
apt install pipx python3-pip python3-venv
pipx ensurepath
pipx install graphspy

# 2. Start GraphSpy (dashboard)
graphspy -i 0.0.0.0 -p 5000

# 3. Install nginx for port 80
apt install nginx
# Configure nginx to proxy port 80 → GraphSpy (5000) + Campaign App (8080)

# 4. Start the Campaign App (handles phish pages, OWA portal)
# Deploy /opt/threatclass/app.py
python3 /opt/threatclass/app.py
```

### Access
- **Dashboard:** `http://YOUR-IP/` (port 80 via nginx)
- **All services run behind nginx on port 80** — no need to remember port numbers

### Services Architecture
```
Port 80 (nginx)
  ├── / → GraphSpy Dashboard (port 5000)
  │     ├── Users Table (home)
  │     ├── Device Codes
  │     ├── Token Management
  │     ├── Phish Generator
  │     └── All GraphSpy pages
  │
  └── /owa, /drive, /phish, /api/* → Campaign App (port 8080)
        ├── OWA Portal (Outlook Web)
        ├── OneDrive Browser
        ├── Phish Landing Pages
        └── Remote APIs (for hosted phish scripts)
```

---

## 3. Dashboard Overview

### Home Page — Users Table

When you open the dashboard, you see a table of all captured users (victims who authenticated via your phish pages).

**Columns:**
| Column | Description |
|--------|-------------|
| # | Row number |
| Email | Victim's email address with country flag (from auth IP) |
| Name | Display name from their Microsoft account |
| Actions | Buttons: Outlook, Outlook Graph, OneDrive, SharePoint, Profile |
| Token ID | The access token ID used for API calls |
| Last Seen | When the token was captured |
| Refresh | Button to get a fresh access token |

**Victim Counter:** Top of the page shows total number of captured users.

**Action Buttons (per user):**
- **Outlook** — Opens the OWA email portal in a new tab (auto-refreshes token for Outlook scope)
- **Outlook Graph** — Opens the built-in Graph email viewer (activates the user's Graph token)
- **OneDrive** — Opens the file browser in a new tab
- **SharePoint** — Navigates to SharePoint sites in the dashboard
- **Profile** — Opens a modal with user details, scopes, global admins, and download options

**Auto-Enrichment:** The dashboard automatically:
- Detects new victims within 30 seconds
- Fetches Global Administrators for each victim's domain
- Extracts email addresses from all mail folders (leads)
- Resolves country from authentication IP
- Re-enriches email leads weekly

---

## 4. Phish Script Generator

**Location:** Sidebar → Phish Generator, or `http://YOUR-IP/phish_generator`

### What It Does
Generates encrypted HTML phishing pages that you can host anywhere. When a victim opens the page, it:
1. Calls back to your server to generate a Microsoft device code
2. Shows the code to the victim with instructions
3. Victim clicks to sign in at the real Microsoft page
4. Your server captures the authentication token

### Settings

**Capture Mode:**
| Mode | What Happens | Client ID | Resource |
|------|-------------|-----------|----------|
| Standard | Captures Graph API token (email, files, teams) | MS Office (best) | Graph API |
| WinHello | Registers device + PRT + WinHello key (persists after password change) | Auth Broker (locked) | Device Registration (locked) |
| Device PRT | Registers device + gets Primary Refresh Token | Auth Broker (locked) | Device Registration (locked) |

**API Version:**
| Version | How It Works | When to Use |
|---------|-------------|-------------|
| V1 | Uses `resource` parameter | Default — works with all clients |
| V2 | Uses `scope` parameter | When you need specific scopes like "My Signins" (modify MFA) |

When you switch V1 ↔ V2, the client and resource/scope dropdowns update to show only compatible options.

**Client IDs (with permission levels):**

| Client | Stars | Scopes | FOCI | Notes |
|--------|-------|--------|------|-------|
| Microsoft Office | ★★★★★ | 36 (Mail, Files, Directory, Teams) | Yes | Best for most captures |
| Outlook Mobile | ★★★★ | Mail, Calendar, Contacts | Yes | Good for email-focused captures |
| Microsoft Teams | ★★★ | Teams, Mail, Files | No | Teams-focused |
| SharePoint | ★★★ | SharePoint, Files | No | File-focused |
| OneDrive | ★★★ | Files only | No | File-focused |
| Azure CLI | ★★ | Varies by tenant | No | No MFA prompt, but limited scopes |
| Azure PowerShell | ★★ | Azure management | No | No MFA prompt |
| Auth Broker | ★ | Device registration | No | Required for WinHello/PRT |
| Device Registration | ★ | Device reg only | No | Registration only |

**FOCI (Family of Client IDs):** If a token has FOCI=1, you can refresh it for ANY Microsoft resource (Graph, Outlook, SharePoint, etc.) even though it was captured with a different client. MS Office and Outlook Mobile always get FOCI=1.

### Templates

| Template | Design | Best For |
|----------|--------|----------|
| Microsoft Verification | Standard Microsoft sign-in page | General use |
| Voicemail Notification | Teams voicemail alert with audio waveform | Urgency-based |
| HR Payroll Update | Payroll verification with deadline warning | Finance/HR targets |
| Shared Document (DocuSign) | DocuSign document signing request | Contract/legal targets |
| Microsoft 365 Quarantine | Security quarantine alert (3 messages held) | Security-aware targets |

**Template-Specific Fields:**
- Payroll: Pay period, payment date, deadline
- DocuSign: Document name, sender, email, dates, message
- Quarantine: Number of quarantined messages

### Generating a Script

1. Select your template
2. Choose capture mode (Standard / WinHello / PRT)
3. Select API version and client ID
4. Set the callback server URL (auto-detected from current browser URL)
5. Click **"Generate Script"**
6. Download as **HTML** or **SVG** file

**Download Options:**
- **HTML File** — Standard encrypted HTML attachment
- **SVG File** — SVG with embedded HTML (bypasses some email filters)

### Hosting the Generated Script
- Upload to any web hosting (Cloudflare Pages, Netlify, your own server)
- Send as email attachment
- The script calls back to your dashboard server to generate codes and capture tokens

### Encryption
All generated scripts are XOR encrypted. Crawlers and scanners see gibberish. Only a real browser with JavaScript decrypts and renders the page.

---

## 5. Device Code Phishing — How It Works

### The Attack Flow

```
Attacker                          Victim                        Microsoft
   |                                |                              |
   |  1. Generate device code       |                              |
   |------------------------------------------------------>       |
   |  <-- Code: ABCD-1234          |                              |
   |                                |                              |
   |  2. Send phish link to victim  |                              |
   |------------------------------->|                              |
   |                                |                              |
   |  3. Victim opens link,         |                              |
   |     sees code, clicks          |                              |
   |     "Sign in with Microsoft"   |                              |
   |                                |----------------------------->|
   |                                |  4. Enters code + signs in   |
   |                                |     (with MFA if required)   |
   |                                |<-----------------------------|
   |                                |  5. "You're signed in"       |
   |                                |                              |
   |  6. Server polls Microsoft     |                              |
   |------------------------------------------------------>       |
   |  <-- Access Token + Refresh Token                            |
   |                                                               |
   |  7. Attacker now has full access to:                         |
   |     - Email (read, send, search)                              |
   |     - OneDrive files                                          |
   |     - SharePoint documents                                    |
   |     - Teams messages                                          |
   |     - Directory (list all users, admins)                      |
   |     - Calendar, contacts                                      |
```

### Why It's Dangerous
- The victim signs in on the **REAL** Microsoft page — nothing looks suspicious
- MFA is completed by the victim — the attacker bypasses MFA entirely
- The attacker gets tokens, NOT passwords — password changes don't revoke tokens
- With FOCI tokens, one capture gives access to ALL Microsoft 365 services
- With WinHello/PRT capture, access persists even after password reset

---

## 6. Using Captured Tokens

### Token Types

| Token | Purpose | Lifetime | Revocation |
|-------|---------|----------|------------|
| **Access Token** | Authenticates API calls | ~1 hour | Expires automatically |
| **Refresh Token** | Gets new access tokens | Days to months | Admin must revoke in Entra ID |
| **Primary Refresh Token (PRT)** | Device-level SSO across all apps | Until device is removed | Remove device from Entra ID |
| **WinHello Key** | Generates new PRTs even after password change | Until key is deleted | Delete from Entra ID |

### Refreshing Tokens
When an access token expires (1 hour), click the **↻ Refresh** button next to any user. The system automatically:
1. Finds the user's latest refresh token
2. Tries multiple client IDs (MS Office → original → Azure CLI) for best scopes
3. Generates a fresh access token
4. Updates the dashboard

### Smart Token Refresh (Action Buttons)
Each action button automatically refreshes for the right scope:
- **Outlook** → Refreshes for `outlook.office365.com` (53 scopes including MailboxSettings)
- **OneDrive** → Refreshes for `graph.microsoft.com` (Files.ReadWrite.All)
- **Outlook Graph** → Refreshes for `graph.microsoft.com` and sets as active token

---

## 7. Outlook Web Access (OWA) Portal

**Access:** Click "Outlook" button on any user, or go to `http://YOUR-IP/owa?token=TOKEN_ID`

### Features
| Feature | How |
|---------|-----|
| **Read emails** | Click any email in the list → renders in the reading pane |
| **Compose new email** | Click "New message" in toolbar → fill To/Cc/Bcc/Subject/Body → Send |
| **Reply / Reply All / Forward** | Click Reply/Forward in toolbar or in email header |
| **Search** | Type in search bar → Enter → searches all mailbox |
| **Delete** | Select email → click Delete in toolbar |
| **Move to folder** | Select email → click Move → pick destination folder |
| **Mark read/unread** | Select email → click Mark read/unread in toolbar |
| **Flag/Unflag** | Select email → click Flag in toolbar |
| **Download attachments** | Click attachment chip below email → file downloads |
| **Folder navigation** | Click any folder in left sidebar (priority folders on top) |
| **Auto-refresh** | Email list refreshes every 30 seconds |

### Layout
```
┌──────────┬─────────────────┬────────────────────────┐
│ Folders  │ Email List      │ Reading Pane            │
│          │                 │                         │
│ Inbox    │ From: John      │ Subject: Meeting        │
│ Sent     │ Subject: ...    │ From: john@company.com  │
│ Drafts   │ Preview...      │ To: you@company.com     │
│ Deleted  │                 │                         │
│ Junk     │ From: Jane      │ [Reply] [Forward]       │
│ Archive  │ Subject: ...    │                         │
│ ...      │ Preview...      │ Email body renders here │
│          │                 │ with HTML formatting    │
└──────────┴─────────────────┴────────────────────────┘
```

---

## 8. OneDrive File Browser

**Access:** Click "OneDrive" button on any user, or go to `http://YOUR-IP/drive?token=TOKEN_ID`

Browse the victim's OneDrive files. Navigate folders, download files.

---

## 9. Outlook Graph (Built-in Email View)

**Access:** Click "Outlook Graph" button on any user, or Sidebar → Outlook (Graph)

This is GraphSpy's built-in email viewer using the Graph API. It works within the dashboard (no new tab). Supports:
- Listing emails by folder
- Reading email content
- Searching emails
- Sending emails
- Downloading attachments

---

## 10. SharePoint Explorer

**Access:** Click "SharePoint" button on any user, or Sidebar → SharePoint Sites/Drives

Browse the organization's SharePoint sites, document libraries, and files.

---

## 11. User Profile & Intelligence

**Access:** Click "Profile" button on any user

### Profile Modal Shows:

**Quick Actions:**
- Open Outlook, Outlook Graph, OneDrive
- Download Email Leads (CSV of all extracted email addresses)

**Identity:**
- Email, Name, Tenant ID, Object ID
- Country (resolved from authentication IP)

**Global Administrators:**
- Lists all Global Admins for the victim's domain
- Automatically fetched in the background when a new victim is captured
- Cached permanently — loads instantly

**Token Info:**
- App name, Client ID, Audience
- Issued/Expires timestamps
- Expired warning if token is old

**Scopes:**
- Full list of permissions the token grants
- Shows exactly what the attacker can access

**Email Leads:**
- Total count of extracted email addresses
- Download as CSV for analysis

### Background Enrichment
When a new victim is captured, the system automatically:
1. **Fetches Global Admins** — queries the directory for all Global Administrator role members
2. **Extracts Email Leads** — scans all email folders for unique email addresses (from, to, cc)
3. **Resolves Country** — uses the authentication IP to determine geographic location
4. **Caches Everything** — stores in database, never re-fetches unnecessarily
5. **Weekly Re-enrichment** — checks for new email contacts every 7 days

---

## 12. Token Management

### Access Tokens
**Location:** Sidebar → Access Tokens

View all captured access tokens. Each entry shows:
- Token ID, User, Resource, Stored At, Expires At
- Decode button to see full JWT claims
- Delete button to remove

### Refresh Tokens
**Location:** Sidebar → Refresh Tokens

View all refresh tokens. Key fields:
- Token ID, User, Client ID, Resource, FOCI status
- Use to generate new access tokens for any resource

### How to Refresh
1. Go to Access Tokens page
2. Select a refresh token
3. Choose client ID and resource
4. Click "Refresh" → new access token generated

---

## 13. WinHello & Primary Refresh Tokens (PRT)

### What Are PRTs?
A Primary Refresh Token is a device-level authentication token. It provides SSO across all Microsoft 365 apps. More powerful than application-specific refresh tokens.

### What Is WinHello?
Windows Hello for Business allows passwordless authentication. By registering a WinHello key, an attacker can generate new PRTs even after the victim changes their password.

### Capturing WinHello/PRT

1. In the Phish Generator, select **Capture Mode: WinHello**
2. The system automatically:
   - Sets Client ID to Auth Broker
   - Sets Resource to Device Registration Service
   - Forces ngcmfa claim (MFA during auth)
3. Generate and deploy the phish page
4. When the victim authenticates:
   - A device is registered in Entra ID
   - A PRT is obtained
   - A WinHello key is created
5. View results in Sidebar → Primary Refresh Tokens and WinHello Keys

### Persistence
- **PRT** → Survives password change. Valid until device is removed from Entra ID.
- **WinHello Key** → Can generate NEW PRTs even after password change. Valid until key is deleted.

**Lecture Point:** "Changing your password is NOT enough to stop an attacker who has a WinHello key. IT must revoke the device and delete the key in Entra ID."

---

## 14. MFA Methods

**Location:** Sidebar → MFA Methods

With sufficient permissions, you can:
- View existing MFA methods on the victim's account
- Add new MFA methods (TOTP, phone, security key)
- This demonstrates how attackers can add their own MFA to maintain access

---

## 15. Teams Messages

**Location:** Sidebar → Teams

Read the victim's Microsoft Teams conversations using Skype API tokens.

---

## 16. Entra ID (Azure AD) Enumeration

**Location:** Sidebar → Entra ID

With `Directory.Read.All` scope, you can:
- List all users in the organization
- View group memberships
- See role assignments (Global Admins, User Admins, etc.)
- View device registrations

**Lecture Point:** "One phished user with Directory.Read.All exposes your entire organizational structure — every employee, every admin, every group."

---

## 17. Custom API Requests

**Location:** Sidebar → Custom Requests

Execute arbitrary Microsoft Graph API calls using any stored token. Useful for:
- Testing specific API endpoints
- Accessing resources not covered by the built-in views
- Demonstrating the breadth of Graph API access

---

## 18. Graph Search

**Location:** Dashboard search bar (top of Users table)

Search across all emails in all folders using Microsoft Graph's `$search` parameter. Enter a keyword (e.g., "password", "credentials", "VPN", "salary") and the system searches the last 90 days of email across all folders.

---

## 19. Database Management

### Download Database
**Location:** Profile modal → or `http://YOUR-IP/api/download_db`

Downloads the entire GraphSpy SQLite database file containing:
- All access tokens and refresh tokens
- Device codes and their statuses
- Cached global admins per domain
- Extracted email leads per user
- WinHello keys and PRTs
- Request templates

### Download Email Leads
**Location:** Profile modal → "Download Email Leads" button

Downloads a CSV file of all extracted email addresses for a specific user. Columns:
- Email, Name, Source (from/to/cc), First Seen

### Download Victims List
**Location:** `http://YOUR-IP/api/download_victims_csv`

Downloads a CSV of all captured users with their token details.

---

## 20. Cloudflare Deployment

### What It Does
Deploy generated phish pages directly to Cloudflare Pages. This gives you a free `.pages.dev` URL without needing your own hosting.

### Setup
1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/profile/api-tokens)
2. Create an API Token with "Cloudflare Pages: Edit" permission
3. Copy your Account ID from the dashboard sidebar
4. In the Phish Generator, enter:
   - **API Token** — your Cloudflare API token
   - **Account ID** — your Cloudflare account ID
   - **Project Name** — e.g., "security-verify" (becomes `security-verify.pages.dev`)
5. Generate a script first, then click **Deploy to Cloudflare**
6. Get a live URL like `https://security-verify.pages.dev`

---

## 21. Password Protection

### Setting a Password
**Location:** Sidebar → Settings

1. Go to Settings
2. Enter a panel password
3. Click Save
4. Next time you access the dashboard, you'll need to enter the password

### Removing the Password
1. Go to Settings
2. Clear the password field
3. Click Save

---

## 22. For the Lecture: Key Talking Points

### Opening Demo (5 minutes)
1. Open the phish link on a volunteer's device (who's in on it)
2. They sign in normally — everything looks legitimate
3. Come back to dashboard — show their email appearing in real-time
4. Read their latest email on the projector
5. **"Everything you just saw started with one link."**

### The Attack Explained (10 minutes)
1. Walk through the Device Code flow diagram
2. Show that the Microsoft page is REAL — the attacker never sees the password
3. Explain MFA bypass — the victim completed MFA themselves
4. Show the token scopes — 36 permissions from one phish

### What Attackers Can Do (10 minutes)
| Action | Demo |
|--------|------|
| Read all email | Open OWA, search for "password" or "confidential" |
| Send email as the victim | Compose from their account to a colleague |
| Browse all files | Open OneDrive, find sensitive documents |
| Read Teams chats | Show private conversations |
| Find all admins | Show Global Admin list — "Now the attacker knows who to target next" |
| Extract 10,000+ email leads | Show the CSV download — "Every person this employee ever emailed" |
| Persist after password change | Show WinHello/PRT — "Even if you change your password, they're still in" |

### Defense & Prevention (10 minutes)

| Attack Vector | Defense |
|---------------|---------|
| Device code phishing | Block device code flow in Conditional Access |
| Fake domain | Always check the URL bar — real Microsoft is only `login.microsoftonline.com` |
| Unsolicited codes | Never enter a device code you didn't generate yourself |
| Token theft | Use Conditional Access policies (compliant device, location-based) |
| MFA persistence | Monitor MFA registration events in Entra ID |
| WinHello abuse | Monitor device registrations, remove unknown devices |
| Email forwarding rules | Audit mailbox rules regularly — attackers set silent forwards |
| Lateral movement | Apply least-privilege — not every user needs Directory.Read.All |

### Closing (2 minutes)
- **"If you receive a link asking you to enter a code — that is an attack. Period."**
- **"Report suspicious links immediately to security@yourcompany.com"**
- **"Speed matters — a stolen token can be used within seconds"**

---

## 23. Prevention & Defense

### For IT Administrators

1. **Block Device Code Flow**
   - Entra ID → Conditional Access → New Policy
   - Target: All users
   - Conditions: Authentication flows → Device code flow
   - Grant: Block

2. **Monitor Sign-in Logs**
   - Look for: "Device code" authentication method
   - Alert on: New device registrations from unknown IPs
   - Watch for: Multiple users authenticating from the same IP

3. **Conditional Access Policies**
   - Require compliant devices for all cloud app access
   - Block sign-ins from non-corporate IPs
   - Require MFA for all users (this doesn't prevent device code phishing but limits other vectors)

4. **Token Protection**
   - Enable token binding (preview feature in Entra ID)
   - Set short token lifetimes for sensitive applications
   - Monitor for anomalous token usage patterns

5. **Regular Audits**
   - Review mailbox forwarding rules monthly
   - Check for unauthorized MFA registrations
   - Remove unknown devices from Entra ID
   - Review Global Admin membership quarterly

### For Employees

1. **Never enter a device code you didn't create**
2. **Always check the URL** — `login.microsoftonline.com` or `login.microsoft.com` ONLY
3. **Report suspicious links immediately** — don't click, forward to IT security
4. **Be suspicious of urgency** — "Your account will be locked", "Verify now", "Quarantined messages"
5. **When in doubt, contact IT directly** — don't use the phone number or link in the suspicious message

---

## Quick Reference Card

| What | Where |
|------|-------|
| Dashboard | `http://YOUR-IP/` |
| Phish Generator | `http://YOUR-IP/phish_generator` |
| Open Phish Page | `http://YOUR-IP/phish` |
| OWA Portal | `http://YOUR-IP/owa?token=ID` |
| OneDrive | `http://YOUR-IP/drive?token=ID` |
| Device Codes | `http://YOUR-IP/device_codes` |
| Access Tokens | `http://YOUR-IP/access_tokens` |
| Refresh Tokens | `http://YOUR-IP/refresh_tokens` |
| Settings | `http://YOUR-IP/settings` |
| Download DB | `http://YOUR-IP/api/download_db` |
| Download Victims CSV | `http://YOUR-IP/api/download_victims_csv` |
| Email Leads CSV | `http://YOUR-IP/api/download_email_leads/USER@DOMAIN` |

---

*This tool is for authorized security awareness training only. Always obtain written permission before conducting phishing simulations.*

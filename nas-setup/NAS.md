# Raspberry Pi NAS — Setup & Usage Guide

A self-hosted Network Attached Storage (NAS) running on the same Raspberry Pi as Pi-hole, the analytics dashboard, and the MCP Telegram bot — with **zero impact** on those existing services.

---

## What It Does

| Capability | Detail |
|---|---|
| **File sharing** | Store and access files from any device on your network |
| **Password protected** | Username `celerity12` + password (Samba/SMB) |
| **LAN access** | Windows, Linux, iOS, Android — all supported |
| **Remote access** | Access from anywhere via Tailscale VPN (encrypted, no port forwarding) |
| **Auto-mount** | USB drive mounts automatically on Pi reboot |
| **Isolated** | Runs on ports 139/445 — no conflicts with Pi-hole, dashboard, or MCP bot |

---

## Connection Details (Quick Reference)

| | LAN | Remote (Tailscale) |
|---|---|---|
| **Pi IP** | `192.168.68.102` | `100.119.186.7` |
| **Hostname** | `pihole` | `pihole` |
| **Share name** | `celerity12-NAS` | `celerity12-NAS` |
| **Username** | `celerity12` | `celerity12` |

---

## Accessing the NAS

### Windows

#### LAN
1. Open **File Explorer**
2. Click the address bar and type:
   ```
   \\192.168.68.102\celerity12-NAS
   ```
3. Enter credentials when prompted:
   - Username: `celerity12`
   - Password: *(your Samba password)*

**Map as a permanent network drive:**
- Right-click **This PC** → **Map network drive**
- Drive letter: pick any (e.g. `Z:`)
- Folder: `\\192.168.68.102\celerity12-NAS`
- Check **Reconnect at sign-in**
- Check **Connect using different credentials** → enter `celerity12` + password

#### Remote (via Tailscale)
1. Install Tailscale on Windows from tailscale.com and sign in with `celerity12@gmail.com`
2. Open File Explorer address bar and type:
   ```
   \\100.119.186.7\celerity12-NAS
   ```
   Or use the hostname:
   ```
   \\pihole\celerity12-NAS
   ```

---

### Linux

#### LAN — GUI (Files / Nautilus)
1. Open **Files** app
2. Click **Other Locations** (bottom left)
3. In the address bar at the bottom type:
   ```
   smb://192.168.68.102/celerity12-NAS
   ```
4. Enter `celerity12` and your password

#### LAN — Terminal (one-time mount)
```bash
sudo apt install cifs-utils -y        # install once if not present
sudo mkdir -p /mnt/nas
sudo mount -t cifs //192.168.68.102/celerity12-NAS /mnt/nas -o username=celerity12,uid=1000,gid=1000
# enter Samba password when prompted
```

#### LAN — Terminal (permanent auto-mount on boot)
```bash
# Add to /etc/fstab
echo "//192.168.68.102/celerity12-NAS  /mnt/nas  cifs  username=celerity12,password=YOUR_PASSWORD,uid=1000,gid=1000,iocharset=utf8,nofail  0  0" | sudo tee -a /etc/fstab

sudo systemctl daemon-reload
sudo mount -a

# Verify
ls /mnt/nas
```

#### Remote (via Tailscale)
1. Install Tailscale on Linux:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   # sign in with celerity12@gmail.com
   ```
2. Verify the share is visible:
   ```bash
   smbclient -L //100.119.186.7 -U celerity12
   ```
3. Mount using Tailscale IP:
   ```bash
   sudo mount -t cifs //100.119.186.7/celerity12-NAS /mnt/nas -o username=celerity12,uid=1000,gid=1000
   ```

> **Note:** The firewall allows Samba from both LAN (`192.168.68.0/24`) and Tailscale (`100.64.0.0/10`) — no extra config needed.

---

### iOS (iPhone / iPad)

#### LAN
1. Open the **Files** app
2. Tap **Browse** → tap `...` (top right) → **Connect to Server**
3. Enter: `smb://192.168.68.102`
4. Tap **Connect**
5. Select **Registered User**
   - Name: `celerity12`
   - Password: *(your Samba password)*
6. Tap **Next** → select `celerity12-NAS`

The NAS now appears under **Locations** in the Files app. You can browse, upload, and open files directly.

#### Remote (via Tailscale)
1. Install **Tailscale** from the App Store
2. Sign in with `celerity12@gmail.com`
3. In the Files app → Connect to Server → enter:
   ```
   smb://100.119.186.7
   ```
4. Login with `celerity12` + password → select `celerity12-NAS`

---

## Architecture

```
Your Devices (LAN / Tailscale)
        │
        │  SMB port 445
        ▼
Raspberry Pi — pihole (192.168.68.102 / 100.119.186.7)
  ├── Pi-hole          → port 53/80/443   (unchanged)
  ├── Analytics        → port 8080        (unchanged)
  ├── MCP Telegram Bot → Telegram API     (unchanged)
  ├── Samba (smbd)     → port 139/445     ← NAS
  └── Tailscale VPN    → encrypted tunnel ← Remote access
        │
        ▼
  /mnt/nas  →  /dev/sda1  (931.5 GB USB drive)
```

---

## Setup (First Time / Re-deploy)

### Prerequisites
- Raspberry Pi running Pi-hole
- USB drive connected to the Pi (`/dev/sda1`, 931.5 GB)
- SSH access to the Pi

### Deploy from your laptop

```bash
cd nas-setup/
source config.sh && bash deploy_nas.sh
```

### Complete Tailscale setup on the Pi (once)

```bash
ssh pi@192.168.68.102
sudo tailscale up
# open the URL shown → sign in at tailscale.com
```

Install Tailscale on each device you want remote access from — use the same `celerity12@gmail.com` account.

---

## Checking Status on the Pi

```bash
# Is Samba running?
sudo systemctl status smbd

# Is the drive mounted?
df -h /mnt/nas

# Is Tailscale connected?
tailscale status

# List active Samba connections
sudo smbstatus

# View Samba logs
sudo journalctl -u smbd -n 50
```

---

## Storage Info

| Item | Value |
|---|---|
| Device | `/dev/sda1` |
| Mount point | `/mnt/nas` |
| Capacity | 931.5 GB |
| Filesystem | ext4 |
| Auto-mount | Yes (via `/etc/fstab` with `nofail`) |

---

## Family Access

### At Home (LAN) — No Tailscale Needed
Anyone connected to your home WiFi (`192.168.68.x`) can access the NAS immediately.
Just share these details with them:

| | |
|---|---|
| Address | `192.168.68.102` |
| Share | `celerity12-NAS` |
| Username | `celerity12` |
| Password | *(your Samba password)* |

**How to connect by device:**
- **Windows:** File Explorer → `\\192.168.68.102\celerity12-NAS`
- **iPhone/iPad:** Files app → `...` → Connect to Server → `smb://192.168.68.102`
- **Android:** CX File Explorer → SMB → `192.168.68.102`

---

### Remote Access for Family — Tailscale

Family members outside the home need Tailscale to connect securely.

#### Option 1 — Invite to your Tailnet (recommended, simplest)
Everyone uses the same Tailscale account (`celerity12@gmail.com`) or you invite them:

1. Go to [tailscale.com/admin](https://tailscale.com/admin) → **Users** → **Invite users**
2. They install Tailscale on their device and accept the invite
3. They can then connect using the Tailscale IP or hostname:
   - `smb://100.119.186.7/celerity12-NAS`
   - `smb://pihole/celerity12-NAS`
   - `smb://pihole.tail08dfdf.ts.net/celerity12-NAS`

> Free Tailscale plan supports up to 100 devices.

#### Option 2 — Separate Samba user per person (more control)
Give each family member their own username and password instead of sharing one:

```bash
ssh pi@192.168.68.102

# Add a new user (e.g. alice)
sudo useradd -M -s /usr/sbin/nologin alice
sudo smbpasswd -a alice          # set their Samba password
sudo usermod -aG celerity12 alice   # give them access to the NAS folder
```

Repeat for each person. They connect with their own username + password but access the same shared drive.

**To remove a user's access:**
```bash
sudo smbpasswd -d alice    # disable
sudo userdel alice         # or delete entirely
```

**To list all Samba users:**
```bash
sudo pdbedit -L
```

---

## Security Notes

- Samba ports (139/445) are firewall-restricted to **LAN** (`192.168.68.0/24`) and **Tailscale** (`100.64.0.0/10`) only — not exposed to the open internet
- Remote access uses **Tailscale WireGuard encryption** — no ports forwarded on your router
- The `celerity12` Linux user has **no login shell** — cannot SSH into the Pi
- All access requires a password — no guest access

---

## Troubleshooting

**Windows — "Network path not found"**
- Ensure you are on the same LAN (`192.168.68.x`)
- Turn on Network Discovery: Settings → Network → Advanced sharing settings → Turn on network discovery
- Try by IP directly: `\\192.168.68.102\celerity12-NAS`

**Linux — "mount error(16): Device or resource busy"**
- Already mounted. Check with `ls /mnt/nas` — if you see files, it's working.
- To remount: `sudo umount /mnt/nas && sudo mount -a`

**Linux — "mount error(2): No such file or directory"**
- Install cifs-utils: `sudo apt install cifs-utils`
- Verify Samba is reachable: `smbclient -L //192.168.68.102 -U celerity12`

**iOS — share not appearing**
- Make sure you're on the same WiFi network as the Pi
- Try connecting to `smb://192.168.68.102` (without the share name) and browse from there

**Drive not showing after Pi reboot**
- Check: `lsblk` — confirm `/dev/sda1` is detected
- Manually mount: `sudo mount /dev/sda1 /mnt/nas`

**Tailscale not connecting**
- Re-authenticate: `sudo tailscale up`
- Check status: `tailscale status`
- Ensure Tailscale is also running on your device

**Permission denied when writing files**
- Fix on Pi: `sudo chown -R celerity12:celerity12 /mnt/nas`

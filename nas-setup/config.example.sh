#!/bin/bash
# =============================================================================
# NAS Config — copy this to config.sh and fill in your values
# Source it before running deploy_nas.sh:
#   source config.sh && bash deploy_nas.sh
# =============================================================================

# --- Pi SSH connection ---
export PI_HOST="raspberrypi.local"   # Pi hostname or IP, e.g. 192.168.1.100
export PI_USER="pi"                  # SSH username on the Pi
export PI_SSH_KEY="$HOME/.ssh/id_rsa"  # Path to your SSH private key

# --- Drive ---
# Run `lsblk` on the Pi to find your USB drive device name
export NAS_DRIVE="/dev/sda1"         # e.g. /dev/sda1, /dev/sdb1
export NAS_MOUNT="/mnt/nas"          # where to mount it on the Pi

# --- Samba share ---
export NAS_USER="nasuser"            # Linux/Samba username (created automatically)
export SHARE_NAME="NAS"             # Name of the share (shown in File Explorer)
export LAN_SUBNET="192.168.1.0/24"  # Your LAN subnet (adjust if different)

# cifs-krb5-linux

Automated Kerberos-authenticated CIFS (SMB) mounts for Linux, using per-share configuration files, a systemd generator, and a custom SPNEGO upcall router.

## Overview

Mounting CIFS shares with Kerberos (`sec=krb5`) requires a valid Kerberos ticket to be present before the mount is attempted, and that ticket must be kept alive for as long as the share is mounted. This project automates the full lifecycle:

- Obtains a Kerberos ticket at boot using a keytab (no password prompt)
- Mounts the share only after the ticket is confirmed present
- Renews the ticket periodically to prevent expiry
- Routes Kerberos upcalls to the correct credential cache when multiple shares on the same server use different principals

## How It Works

```
Boot
 │
 ├─ systemd generator reads /etc/cifs-mounts.d/*.conf
 │   └─ generates per-share units into /run/systemd/generator/
 │
 ├─ cifs-kinit-<mount>.service   (After=network-online.target)
 │   └─ kinit -k -t <keytab> <principal>  →  KCM:0:<name>
 │
 ├─ <mount>.mount                (Requires=cifs-kinit-<mount>.service)
 │   └─ mount -t cifs //<server>/<share> <mountpoint>
 │
 └─ cifs-renew-<mount>.timer     (OnBootSec=2min, OnUnitActiveSec=10min)
     └─ cifs-renew-<mount>.service
         └─ kinit -R  ||  kinit -k -t   (refresh or re-acquire)

Kernel upcall (on ticket expiry)
 └─ request-key → cifs-upcall-router
     └─ finds mountpoint from calling process
         └─ sets KRB5CCNAME → exec cifs.upcall
```

## Repository Layout

```
etc/
  cifs-mounts.d/
    share1.conf              # per-share configuration (one file per mount)
  request-key.d/
    cifs.spnego.conf         # routes upcalls to cifs-upcall-router
  security/
    keytabs/
      create-keytab          # interactive script to create/update keytab files

usr/
  lib/systemd/system-generators/
    cifs-krb5-generator      # generates systemd units at boot
  local/sbin/
    cifs-upcall-router       # per-share Kerberos cache router
```

## Configuration

Each share requires one file in `/etc/cifs-mounts.d/`. The filename is arbitrary.

```bash
# /etc/cifs-mounts.d/share1.conf

PRINCIPAL=svcaccount@REALM
KEYTAB=/etc/security/keytabs/svcaccount.keytab
CACHE=KCM:0:share1

SERVER=fileserver
SHARE=data
MOUNT=/mnt/data

CIFS_UID=1000
CIFS_GID=1000
DIR_MODE=0755
FILE_MODE=0644

VERS=3.1.1
SEC=krb5
IOCHARSET=utf8
CACHE_MODE=strict

AUTO_RENEW=yes
```

| Variable | Required | Description |
|---|---|---|
| `PRINCIPAL` | yes | Kerberos principal (`user@REALM`) |
| `KEYTAB` | yes | Path to keytab file |
| `CACHE` | yes | KCM cache name (`KCM:0:<id>` \| `KEYRING:persistent:0:<id>`) |
| `SERVER` | yes | SMB server hostname |
| `SHARE` | yes | Share name on the server |
| `MOUNT` | yes | Local mountpoint |
| `CIFS_UID` | no | File ownership UID |
| `CIFS_GID` | no | File ownership GID |
| `DIR_MODE` | no | Directory permission mask |
| `FILE_MODE` | no | File permission mask |
| `VERS` | no | SMB protocol version (default: `3`) |
| `SEC` | no | Security mode (default: `krb5`) |
| `IOCHARSET` | no | Character set (default: none) |
| `CACHE_MODE` | no | CIFS cache mode (e.g. `strict`) |
| `AUTO_RENEW` | no | Set to `yes` to enable the renewal timer |

## Creating a Keytab

```bash
/etc/security/keytabs/create-keytab /etc/security/keytabs/svcaccount.keytab
```

The script prompts for the principal and password, writes a keytab using `aes256-cts-hmac-sha1-96`, verifies it with `kinit -k -t`, and destroys the test ticket immediately. Run it again on the same file to update after a password change.

## Deployment

Copy the repository tree onto the target system:

```bash
cp -r etc/cifs-mounts.d        /etc/
cp -r etc/request-key.d        /etc/
cp -r etc/security/keytabs     /etc/security/
cp -r usr/lib/systemd          /usr/lib/
cp -r usr/local/sbin           /usr/local/

chmod +x /usr/lib/systemd/system-generators/cifs-krb5-generator
chmod +x /usr/local/sbin/cifs-upcall-router
chmod +x /etc/security/keytabs/create-keytab
chmod 600 /etc/security/keytabs/*.keytab
```

Then either reboot or trigger the generator manually:

```bash
systemctl daemon-reload
systemctl start cifs-kinit-<name>.service
systemctl start <mount>.mount
systemctl start cifs-renew-<name>.timer   # if AUTO_RENEW=yes
```

Unit names are derived from the mount path via `systemd-escape`. For `/mnt/data` the names are `mnt-data.mount`, `cifs-kinit-mnt-data.service`, etc.

## Troubleshooting

**Generator errors at boot:**
```bash
# Enable debug logging in the generator (uncomment the two lines near the top):
#exec 2>/run/cifs-generator-err.log
#set -x

cat /run/cifs-generator-err.log
```

**Upcall routing:**
```bash
journalctl -t cifs-upcall-router
```

**Ticket status:**
```bash
KRB5CCNAME=KCM:0:share1 klist
```
or
```bash
klist -A
```


**Check generated units:**
```bash
ls /run/systemd/generator/cifs-* /run/systemd/generator/*.mount
systemctl status mnt-data.mount cifs-kinit-mnt-data.service
```

## Requirements

### RHEL-like:
- `cifs-utils` (provides `cifs.upcall`, `mount.cifs`)
- `krb5-workstation` (provides `kinit`, `klist`, `ktutil`)
- `sssd-kcm` for KCM daemon cache (optional)

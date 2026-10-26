# Backup Setup

The Pi receives a daily backup of Claude memory files, knowledge graphs, and Obsidian vaults from the Windows PC. A **Backup Status** desktop kiosk on the Pi shows the git log for both backup repositories.

---

## What gets backed up

| Source (Windows) | Destination (Pi) | Repo |
|---|---|---|
| `C:\Users\Rupal\.claude\memory\` — global memory | `~/agentic-memory-backup/global-memory/` | `agentic-memory-backup` |
| `C:\Users\Rupal\.claude\projects\*/memory/` — per-project memory | `~/agentic-memory-backup/projects/` | `agentic-memory-backup` |
| `AppData\Roaming\agentmemory\` — knowledge graph DB | `~/agentic-memory-backup/agentmemory/` | `agentic-memory-backup` |
| Obsidian vaults (`.md` only — no binaries or secrets) | `~/agentic-memory-backup/vaults/` | `agentic-memory-backup` |
| `C:\Users\Rupal\.claude\skills\` — Claude Code skills | `~/agentic-skills-backup/` | `agentic-skills-backup` |

Vaults backed up:
- `obsidianvaults` (GitHub repo clone — Fintrak, Luckydays, Vantage Fit, VF Cx Functions, VantageCircle Core, Vantagefit OS MIND)
- `aegis-ai-vault` (vault branch of aegis-ai repo)
- `pinet` — embedded vault in this repo
- `openfit` — embedded vault in the openfit repo
- `Agentic Dev` — hub workspace vault

---

## Windows side

### Backup script
`C:\Users\Rupal\.agents\sync_memory_to_pi.py`

Runs on the Windows PC; archives all sources, SCPs to the Pi, and commits.

```
python "C:\Users\Rupal\.agents\sync_memory_to_pi.py"
```

### Scheduled task (daily 3 AM)
Register once with PowerShell (requires manual run — scheduled task registration needs elevation):

```powershell
! powershell -ExecutionPolicy Bypass -File "C:\Users\Rupal\.agents\setup_memory_backup_schedule.ps1"
```

Task name: `ClaudeMemoryBackupToPi`

---

## Pi side

### Storage location
All backup data and knowledge graphs live on the **PINET USB drive** (`/dev/sda`, 58 GB ext4, permanently mounted at `/mnt/pinet-media`):

```
/mnt/pinet-media/agentic-data/
    agentic-skills-backup/    ← skills (git-tracked)
    agentic-memory-backup/    ← memory + graphs + vaults (git-tracked)
    graphs/                   ← graphify knowledge graphs
```

Symlinks in the home directory keep all scripts working without changes:
```
~/agentic-skills-backup  →  /mnt/pinet-media/agentic-data/agentic-skills-backup
~/agentic-memory-backup  →  /mnt/pinet-media/agentic-data/agentic-memory-backup
~/graphs                 →  /mnt/pinet-media/agentic-data/graphs
```

> **Note:** if the USB drive is not mounted, the symlinks dangle and backups will fail. The drive uses `nofail` in fstab so a missing drive won't block boot, but the backup cron will error visibly.

### First-time setup (new Pi or re-formatted USB)
```bash
# Create dir on USB drive
sudo mkdir -p /mnt/pinet-media/agentic-data
sudo chown rupal:rupal /mnt/pinet-media/agentic-data

# Init git repos
cd /mnt/pinet-media/agentic-data
git init -b main agentic-skills-backup && cd agentic-skills-backup \
  && git config user.email "rupal@backup" && git config user.name "Backup Bot" && cd ..
git init -b main agentic-memory-backup && cd agentic-memory-backup \
  && git config user.email "rupal@backup" && git config user.name "Backup Bot" && cd ..
mkdir -p graphs

# Create symlinks
ln -s /mnt/pinet-media/agentic-data/agentic-skills-backup ~/agentic-skills-backup
ln -s /mnt/pinet-media/agentic-data/agentic-memory-backup ~/agentic-memory-backup
ln -s /mnt/pinet-media/agentic-data/graphs ~/graphs
```

### `backup-status-index` script
Installed at `/usr/local/bin/backup-status-index`. Generates `~/backup-status/index.html` — a dark-themed page showing the last 6 commits from each repo.

Deploy:
```bash
scp scripts/bin/backup-status-index rupal@192.168.29.125:~/backup-status-index
ssh rupal@192.168.29.125 "sudo mv ~/backup-status-index /usr/local/bin/ && sudo chmod +x /usr/local/bin/backup-status-index"
```

### Backup Status taskbar launcher
`desktop/backup-pi.desktop` → deployed to `~/.local/share/applications/` (not `~/Desktop/`), icon to `~/.local/share/icons/`.

The icon lives in the **taskbar launcher strip** alongside Photo Frame and Camera, keeping the desktop clean. Deploy:

```bash
scp desktop/backup-pi.desktop desktop/icons/backup-pi.svg rupal@192.168.29.125:~/
ssh rupal@192.168.29.125 "mv ~/backup-pi.desktop ~/.local/share/applications/ && mv ~/backup-pi.svg ~/.local/share/icons/"
```

When tapped:
1. Regenerates `~/backup-status/index.html`
2. Opens it in the DSI kiosk (800×480, close button top-left, **auto-hides after 4 s**)

---

## Security notes

- Transfer uses SSH/SCP (key-based auth). Pi is a local device; no public exposure.
- Archives are unencrypted at rest on the Pi — acceptable for a home-network device.
- Vault backup is **`.md` only** — binary assets (fonts, images) are excluded.
- `data.json` (Copilot plugin — may hold an API key) is always skipped from vault backups.
- `.git` directories are excluded from vault copies to prevent submodule confusion.
- The `agentic-memory-backup` git history is local-only (no GitHub remote).

---

## Restore

**Skills:**
```bash
scp -r rupal@192.168.29.125:~/agentic-skills-backup/skills ~/.claude/skills
```

**Memory:**
```bash
scp -r rupal@192.168.29.125:~/agentic-memory-backup/global-memory ~/.claude/memory
```

"""Build a single zip file the new developer can download + extract.

Includes everything they need to take over:
  - All source code (api/, src/, scripts/, public/, build_data.py, etc.)
  - All data files (sources + verification artefacts)
  - Documentation (HANDOVER.md, docs/, MASTER_SPEC.md, etc.)
  - Memory files (so their Claude Code session has context day-1)
  - package.json, vite.config.js, vercel.json

EXCLUDES (the new dev will regenerate):
  - node_modules/ — `npm install` recreates
  - dist/ — `npm run build` recreates
  - .vercel/ — `vercel link` recreates per their project
  - __pycache__/ — Python cache
  - Local .env or secrets — they'll set their own keys

USAGE:
  python scripts/package_for_handover.py
  → creates Desktop\\findahousingprovider_handover.zip
"""
import os, zipfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
DESKTOP = HOME / "OneDrive" / "Desktop"
DESKTOP.mkdir(parents=True, exist_ok=True)
ZIP_PATH = DESKTOP / "findahousingprovider_handover.zip"

EXCLUDE_DIRS = {
    "node_modules", "dist", ".vercel", "__pycache__", ".git",
    ".scratch", ".firecrawl", "references",
}
EXCLUDE_PATTERNS = (".pyc", ".log", ".tmp")

# Files outside the project we also want to include for context
MEMORY_DIR = HOME / ".claude" / "projects" / "C--Users-paul---claude" / "memory"

def should_include(path):
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS: return False
    if any(str(path).endswith(p) for p in EXCLUDE_PATTERNS): return False
    return True

def main():
    print(f"Packaging into: {ZIP_PATH}")
    file_count = 0
    total_bytes = 0
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1. Project files
        for p in ROOT.rglob("*"):
            if not p.is_file(): continue
            rel = p.relative_to(ROOT)
            if not should_include(rel): continue
            zf.write(p, f"findahousingprovider/{rel.as_posix()}")
            file_count += 1
            total_bytes += p.stat().st_size

        # 2. Memory files (so new dev's Claude session has context)
        if MEMORY_DIR.exists():
            for p in MEMORY_DIR.glob("*.md"):
                # Only the FAHP-related ones, not other projects
                if "findahousingprovider" in p.name or p.name == "MEMORY.md":
                    zf.write(p, f"findahousingprovider/_claude_memory/{p.name}")
                    file_count += 1
                    total_bytes += p.stat().st_size

        # 3. Quick-start README at the top
        zf.writestr("findahousingprovider/QUICK_START.md", QUICK_START)

    final_size = ZIP_PATH.stat().st_size
    print(f"\n[OK] Done.")
    print(f"  Files included:    {file_count:,}")
    print(f"  Uncompressed size: {total_bytes/1024/1024:.1f} MB")
    print(f"  Zip size:          {final_size/1024/1024:.1f} MB")
    print(f"\nSend to developer: {ZIP_PATH}")

QUICK_START = """# Quick start — new developer

You have just received the full Find a Housing Provider codebase. Here's the
shortest path to a working dev environment + production deploy.

## 1. Install + first deploy (45 min)

```bash
# unzip into a folder, then:
cd findahousingprovider
npm install
npm install -g vercel
vercel login          # use your own Vercel account
vercel link           # create new project: "findahousingprovider"
```

## 2. Add env vars to the new Vercel project

In Vercel dashboard → your-project → Settings → Environment Variables, add:
  - STRIPE_SECRET_KEY  (from stripe.com)
  - FIRECRAWL_API_KEY  (from firecrawl.dev) — only needed when running scripts locally
  - ADMIN_TOKEN        (any random secret)

## 3. Provision the database

Vercel dashboard → Storage → Create Database → KV.
Connect to your project. Vercel auto-adds the KV_* env vars.

## 4. First deploy

```bash
npm run build
vercel deploy --prod --yes
```

That's it. Site is live.

## 5. To take over operations

Read **HANDOVER.md** in the root. Everything else is in there.

## Files to be aware of

- `HANDOVER.md` — complete operations + architecture document
- `docs/UPLOAD_NEW_CONTRACT.md` — monthly CSV ingest workflow
- `docs/VERIFICATION_PROCESS.md` — how providers get Verified vs Listed
- `_claude_memory/MEMORY.md` — load into your Claude Code session for instant context
"""

if __name__ == "__main__":
    main()

"""Process a long names.json list in batches of N, applying + deploying after each.

Safer than the one-shot lookup script for very large runs:
  - If Firecrawl credits run out mid-way, you keep the partial results live
  - You can step away with confidence that the previous batch is already deployed
  - Customers see continual incremental improvement as the run progresses

USAGE:
  python scripts/firecrawl_lookup_batched.py path/to/names.json [BATCH_SIZE]

Defaults to BATCH_SIZE=750.
"""
import json, sys, subprocess, time
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    name_file = sys.argv[1]
    batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 750

    names = json.load(open(name_file, encoding='utf-8'))
    total = len(names)
    print(f"Total names: {total}")
    print(f"Batch size:  {batch_size}")
    print(f"Batches:     {(total + batch_size - 1) // batch_size}")
    print()

    Path('data/verification/batches').mkdir(parents=True, exist_ok=True)
    started = time.time()

    for i in range(0, total, batch_size):
        batch_num = (i // batch_size) + 1
        chunk = names[i:i + batch_size]
        chunk_file = Path('data/verification/batches') / f'chunk_{batch_num:03d}.json'
        json.dump(chunk, open(chunk_file, 'w', encoding='utf-8'), indent=2)

        print(f"\n{'='*70}", flush=True)
        print(f"  BATCH {batch_num}: processing names {i+1}-{min(i+batch_size, total)} of {total}", flush=True)
        print(f"{'='*70}", flush=True)

        # 1. Firecrawl lookup
        print(f"\n--- Firecrawl /search + /extract ---", flush=True)
        subprocess.run(['python', '-u', 'scripts/firecrawl_lookup_names.py',
                        str(chunk_file), '--workers', '8'], check=False)

        # 2. Apply verdicts
        print(f"\n--- Apply verdicts ---", flush=True)
        subprocess.run(['python', 'scripts/apply_firecrawl.py'], check=False)

        # 3. Rebuild
        print(f"\n--- Rebuild providers.json ---", flush=True)
        subprocess.run(['python', 'build_data.py'], check=True,
                       stdout=subprocess.DEVNULL)

        # 4. Frontend
        print(f"\n--- Frontend build ---", flush=True)
        subprocess.run(['npm', 'run', 'build'], check=False,
                       stdout=subprocess.DEVNULL, shell=True)

        # 5. Deploy
        print(f"\n--- Vercel deploy ---", flush=True)
        result = subprocess.run(['vercel', 'deploy', '--prod', '--yes'],
                                check=False, shell=True, capture_output=True, text=True)
        # find the aliased line
        for line in (result.stderr or result.stdout or '').splitlines():
            if 'Aliased' in line or 'Production' in line:
                print(f"   {line.strip()}", flush=True)

        # Report intermediate state
        prov = json.load(open('api/_data/providers.json', encoding='utf-8'))
        v = sum(1 for x in prov if x.get('verification',{}).get('verified'))
        elapsed_min = int((time.time() - started) // 60)
        print(f"\n   ✓ Batch {batch_num} live: {len(prov)} providers, {v} verified ({v*100//len(prov)}%) "
              f"— elapsed {elapsed_min}min", flush=True)

    print(f"\n{'='*70}")
    print(f"  ALL BATCHES COMPLETE in {int((time.time() - started)//60)} min")
    print(f"{'='*70}")

if __name__ == '__main__':
    main()

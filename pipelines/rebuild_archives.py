import json
import glob
import os
import re
from datetime import datetime, timezone, timedelta

def clean_file(filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        if not isinstance(data, list):
            return 0
            
        now = datetime.now(timezone.utc)
        future_threshold = now + timedelta(days=2)
        past_threshold = datetime(2000, 1, 1, tzinfo=timezone.utc)
        
        cleaned = []
        removed_count = 0
        
        for item in data:
            ts_str = item.get('timestamp')
            if not ts_str:
                continue
                
            try:
                # Handle possible Z or offsets in ISO string
                ts_iso = ts_str.replace('Z', '+00:00')
                ts = datetime.fromisoformat(ts_iso)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                    
                if ts > future_threshold or ts < past_threshold:
                    print(f"[{filepath}] Removing weird signal: {item.get('title')} (Date: {ts_str})")
                    removed_count += 1
                else:
                    # Also strip control characters from titles to prevent XML sitemap crashes
                    if 'title' in item and isinstance(item['title'], str):
                        item['title'] = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', item['title'])
                    cleaned.append(item)
            except Exception as e:
                # If date parsing fails, drop the weird record.
                removed_count += 1
                
        if removed_count > 0:
            with open(filepath, 'w') as f:
                json.dump(cleaned, f, indent=2)
                
        return removed_count
    except Exception as e:
        print(f"Could not process {filepath}: {e}")
        return 0

def main():
    print("🧹 Cleaning weird anomaly signals (future-dated & epoch 0 & control chars) from all archives...")
    files = []
    
    if os.path.exists('data/latest_intel.json'):
        files.append('data/latest_intel.json')
        
    files.extend(glob.glob('data/archive/*.json'))
    files.extend(glob.glob('public/archive/**/*.json', recursive=True))
    
    total_removed = 0
    for path in set(files):
        # Skip manifest files or simple dict files
        if 'manifest' in path or 'summary' in path: 
            continue
        total_removed += clean_file(path)
        
    print(f"\n✨ Cleaned up {total_removed} broken anomalies across the database.")

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import json
import subprocess
import os
import sys

def run_command(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout

def get_conflicted_files():
    output = run_command("git status --porcelain")
    if not output:
        return []
    
    conflicted = []
    for line in output.splitlines():
        if line.startswith("UU ") or line.startswith("AA "):
            conflicted.append(line[3:].strip())
    return conflicted

def resolve_json_conflict(filepath):
    print(f"Attempting to resolve conflict in: {filepath}")
    
    # Get the three versions: BASE (1), OURS (2), THEIRS (3)
    # During a rebase, :2 is what was on the branch we are rebasing onto (the new foundation)
    # and :3 is the commit we are trying to apply.
    ours_raw = run_command(f"git show :2:{filepath}")
    theirs_raw = run_command(f"git show :3:{filepath}")
    
    if ours_raw is None or theirs_raw is None:
        print(f"  ❌ Could not retrieve Git versions for {filepath}")
        return False
    
    try:
        ours = json.loads(ours_raw)
        theirs = json.loads(theirs_raw)
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON decode error: {e}")
        return False

    if not isinstance(ours, list) or not isinstance(theirs, list):
        print(f"  ❌ File {filepath} is not a JSON list, skipping auto-resolve.")
        return False

    # Merge and deduplicate by 'hash'
    merged_dict = {}
    
    # Add ours first (foundation)
    for item in ours:
        h = item.get('hash')
        if h:
            merged_dict[h] = item
            
    # Add theirs (new changes), overwriting if same hash
    for item in theirs:
        h = item.get('hash')
        if h:
            merged_dict[h] = item
            
    merged_list = list(merged_dict.values())
    
    # Sort by timestamp descending if possible
    try:
        merged_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    except Exception:
        pass
        
    # Write back to file
    with open(filepath, 'w') as f:
        json.dump(merged_list, f, indent=2)
        
    print(f"  ✅ Successfully merged {len(merged_list)} items ({len(ours)} ours + {len(theirs)} theirs)")
    return True

def main():
    conflicted_files = get_conflicted_files()
    if not conflicted_files:
        print("No conflicted files found.")
        return

    resolved_count = 0
    for file in conflicted_files:
        if file.endswith(".json"):
            if resolve_json_conflict(file):
                resolved_count += 1
        else:
            print(f"Skipping non-JSON file: {file}")

    if resolved_count > 0:
        print(f"\nResolved {resolved_count} JSON conflicts.")
    else:
        print("\nNo conflicts were resolved.")

if __name__ == "__main__":
    main()

import json
import os

def check_overlaps():
    sv_path = "data/stolen_vehicles.json"
    ast_path = "data/ast_logs.json"
    
    # Check if files exist
    if not os.path.exists(sv_path) or not os.path.exists(ast_path):
        print("Missing dataset files.")
        return

    # Load Official DPS Stolen Vehicles (Vehicle API)
    with open(sv_path, "r") as f:
        sv_data = json.load(f)
        
    sv_ids = set()
    for item in sv_data:
        # The AST Incident ID in this feed is stored in the 'posted' attribute
        inc_id = item.get("posted", "")
        if inc_id and inc_id.startswith("AK"):
            sv_ids.add(inc_id.upper().strip())

    # Load the parsed Alaska State Trooper Text Dispatches (Historical Crawl)
    with open(ast_path, "r") as f:
        ast_data = json.load(f)

    ast_ids = set()
    for item in ast_data:
        inc_id = item.get("id", "")
        if inc_id and inc_id.startswith("AK"):
            ast_ids.add(inc_id.upper().strip())

    total_sv = len(sv_data)
    total_sv_with_ids = len(sv_ids)
    
    total_ast = len(ast_data)
    total_ast_with_ids = len(ast_ids)
    
    # Calculate overlap
    intersection = sv_ids.intersection(ast_ids)
    only_in_ast = ast_ids.difference(sv_ids)
    only_in_sv = sv_ids.difference(ast_ids)
    
    print("## 🔄 Dataset Cross-Check Analysis\n")
    print("### Metrics")
    print(f"- **Total DPS Official Stolen Vehicles Tracked:** {total_sv:,} (Found {total_sv_with_ids:,} explicit Incident IDs)")
    print(f"- **Total Troopers Historical Dispatches Extracted:** {total_ast:,}")
    print(f"- **Exact ID Collisions (Overlap):** {len(intersection):,}")
    print(f"- **Incidents Only Described in Text Dispatches:** {len(only_in_ast):,}")
    print("\n### Conclusion")
    
    percent_overlap = (len(intersection) / len(ast_ids) * 100) if ast_ids else 0
    
    print(f"We matched **{percent_overlap:.1f}%** of the text-parsed Troopers Dispatches directly against the official centralized Stolen Vehicles Database.")
    print("The incidents found *only* in the text dispatches represent cases where the vehicle might not have triggered an API event, was recovered immediately, or was handled by local PD rather than central database insertion.")

if __name__ == "__main__":
    check_overlaps()

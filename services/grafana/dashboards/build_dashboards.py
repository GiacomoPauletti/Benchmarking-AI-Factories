import json
import os
import glob

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def build_dashboard(src_dir, output_file):
    # Load base dashboard configuration
    base_config_path = os.path.join(src_dir, 'dashboard.json')
    if not os.path.exists(base_config_path):
        print(f"Skipping {src_dir}: dashboard.json not found")
        return

    dashboard = load_json(base_config_path)
    
    # Load panels
    panels_dir = os.path.join(src_dir, 'panels')
    if os.path.exists(panels_dir):
        panels = []
        # Sort files to ensure deterministic order
        panel_files = sorted(glob.glob(os.path.join(panels_dir, '*.json')))
        for panel_file in panel_files:
            print(f"  Adding panel: {os.path.basename(panel_file)}")
            panel = load_json(panel_file)
            panels.append(panel)
        
        # If dashboard already has panels, append or replace? 
        # For now, let's assume we replace or extend. 
        # If "panels" key exists in dashboard.json, we extend it.
        if 'panels' not in dashboard:
            dashboard['panels'] = []
        
        dashboard['panels'].extend(panels)

    # Save to output file
    print(f"Saving dashboard to {output_file}")
    save_json(output_file, dashboard)

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    src_root = os.path.join(base_dir, 'src')
    output_root = base_dir # Save directly in dashboards/ folder

    if not os.path.exists(src_root):
        print(f"Source directory {src_root} not found.")
        return

    # Iterate over subdirectories in src/
    for item in os.listdir(src_root):
        item_path = os.path.join(src_root, item)
        if os.path.isdir(item_path):
            print(f"Building dashboard: {item}")
            output_file = os.path.join(output_root, f"{item}.json")
            build_dashboard(item_path, output_file)

if __name__ == "__main__":
    main()

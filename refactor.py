import os
import ast
import re

def create_dirs():
    for d in ['core', 'ui', 'utils']:
        os.makedirs(d, exist_ok=True)

def split_file_by_patterns(filepath, output_map):
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()
    
    tree = ast.parse(source)
    
    # Extract imports
    imports = []
    nodes = []
    
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(ast.get_source_segment(source, node))
        else:
            nodes.append(node)
            
    # Classify nodes
    files_content = {k: [] for k in output_map.keys()}
    
    for node in nodes:
        node_source = ast.get_source_segment(source, node)
        name = getattr(node, 'name', '')
        if not name and isinstance(node, ast.Assign):
            # Try to get variable name
            if getattr(node, 'targets', None):
                if isinstance(node.targets[0], ast.Name):
                    name = node.targets[0].id
                    
        placed = False
        for out_file, patterns in output_map.items():
            if name:
                for p in patterns:
                    if re.search(p, name, re.IGNORECASE):
                        files_content[out_file].append(node_source)
                        placed = True
                        break
            if placed:
                break
                
        if not placed:
            # default to first file
            default_file = list(output_map.keys())[0]
            files_content[default_file].append(node_source)
            
    # Write files
    import_block = "\n".join(imports) + "\n\n"
    for out_file, contents in files_content.items():
        if contents:
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write(import_block)
                f.write("\n\n".join(contents))

def main():
    create_dirs()
    
    sync_map = {
        'core/sync_worker.py': ['Worker', 'Thread'],
        'utils/crypto_utils.py': ['Crypto', 'Encrypt', 'Decrypt', 'Key'],
        'utils/text_utils.py': ['Text', 'String', 'Format'],
        'utils/system_utils.py': ['System', 'OS', 'File', 'Path', 'Dir'],
        'core/sync_manager.py': ['.*'] # Default fallback
    }
    
    ui_map = {
        'ui/memo_window.py': ['MemoWindow'],
        'ui/memo_editor.py': ['MemoEditor', 'Editor'],
        'ui/memo_explorer.py': ['MemoExplorer', 'Explorer'],
        'ui/settings_window.py': ['SettingsWindow', 'Setting'],
        'ui/dialogs.py': ['Dialog', 'Alert', 'Popup'],
        'ui/ui_manager.py': ['.*'] # Default fallback
    }
    
    if os.path.exists('sync_manager.py'):
        split_file_by_patterns('sync_manager.py', sync_map)
        os.remove('sync_manager.py')
        
    if os.path.exists('ui_manager.py'):
        split_file_by_patterns('ui_manager.py', ui_map)
        os.remove('ui_manager.py')

if __name__ == '__main__':
    main()

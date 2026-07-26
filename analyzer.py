import ast
import json
import sys

def analyze_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    tree = ast.parse(content)
    
    classes = []
    functions = []
    
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append({
                'name': node.name,
                'start_line': node.lineno,
                'end_line': node.end_lineno
            })
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            functions.append({
                'name': node.name,
                'start_line': node.lineno,
                'end_line': node.end_lineno
            })
            
    print(json.dumps({'classes': classes, 'functions': functions}, indent=2))

if __name__ == '__main__':
    analyze_file(sys.argv[1])

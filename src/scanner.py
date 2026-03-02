import os

class CodeScanner:
    def __init__(self, project_path):
        self.project_path = project_path

    def get_context_for_file(self, target_file):
        """Reads the content of the target file to provide context to the AI."""
        try:
            with open(target_file, 'r') as f:
                content = f.read()
            return content
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def scan_workspace(self, root_dir=None):
        """Elite feature: Scans the entire workspace for Python files and basic health metrics."""
        if root_dir is None:
            root_dir = self.project_path
            
        results = []
        for root, dirs, files in os.walk(root_dir):
            if any(x in root for x in [".git", "__pycache__", "venv", "node_modules", "frontend", "uploads"]):
                continue
                
            for file in files:
                if file.endswith('.py'):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, root_dir)
                    try:
                        size = os.path.getsize(full_path)
                        results.append({
                            "name": file,
                            "path": full_path,
                            "rel_path": rel_path,
                            "size": size,
                        })
                    except:
                        pass
        return results

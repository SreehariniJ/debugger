import os

class CodeScanner:
    def __init__(self, root_dir):
        self.root_dir = root_dir

    def get_all_code(self):
        """Walks through the directory and returns a map of filename to content."""
        code_map = {}
        # We only look for common programming files (extensible for your PPT goals)
        target_extensions = ('.py', '.c', '.cpp', '.java', '.js')
        
        for root, dirs, files in os.walk(self.root_dir):
            # Skip hidden folders like .git
            files = [f for f in files if not f.startswith('.')]
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for file in files:
                if file.endswith(target_extensions):
                    path = os.path.join(root, file)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            code_map[path] = f.read()
                    except Exception as e:
                        print(f"Could not read {path}: {e}")
        return code_map

    def get_context_for_file(self, target_file):
        """Extracts content of a specific file to send to the AI."""
        if os.path.exists(target_file):
            with open(target_file, 'r') as f:
                return f.read()
        return "File not found."

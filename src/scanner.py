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

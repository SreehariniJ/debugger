import json
import os

class LocalRAGEngine:
    def __init__(self, data_dir="knowledge_base"):
        # This tells the engine to look in your new folder
        self.data_dir = data_dir
        self.kb_data = self._load_json("kb.json")
        self.pylint_data = self._load_json("pylint_knowledge.json")

    def _load_json(self, filename):
        # Look for the file in the TechVoyagers/knowledge_base path
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base_path, self.data_dir, filename)
        
        if os.path.exists(path):
            with open(path, 'r') as f:
                try:
                    return json.load(f)
                except Exception as e:
                    print(f"⚠️ Warning: Could not parse {filename}: {e}")
                    return None
        return None

    def query_docs(self, error_msg):
        """Matches the detected error against your JSON entries."""
        # 1. Search kb.json
        if self.kb_data:
            for section in ["core", "secondary"]:
                entries = self.kb_data.get(section, {})
                for err_name, details in entries.items():
                    if err_name.lower() in error_msg.lower():
                        return f"Source: kb.json | {details['explanation']} Suggestion: {details['suggestion']}"

        # 2. Search pylint_knowledge.json
        if self.pylint_data:
            for item in self.pylint_data:
                name = item.get("name", "").replace("-", " ")
                if name != "" and name in error_msg.lower():
                    return f"Source: Pylint Docs | {item['description']}"

        return "No specific local documentation found."

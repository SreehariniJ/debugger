import os
from llama_cpp import Llama

class DebuggingAgents:
    def __init__(self, model_path="models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"):
        self.model_path = model_path
        if os.path.exists(self.model_path):
            self.llm = Llama(model_path=self.model_path, n_ctx=2048, verbose=False)
        else:
            print(f"❌ Model not found at {self.model_path}")
            self.llm = None

    def clean_response(self, text, start_phrase):
        """Strict filter to ensure the output is concise and student-friendly."""
        # 1. Take only the first two sentences to avoid 'rambling'
        sentences = text.split('.')
        short_version = ". ".join(sentences[:2]) 
        
        # 2. Cut off any AI 'noise' (A:, B:, Analysis:, etc.)
        for stopper in ["A:", "B:", "Analysis:", "Teacher:", "Explanation:", "This solution"]:
            short_version = short_version.split(stopper)[0]
            
        # 3. Final polish
        clean_text = short_version.strip().replace("..", ".")
        if not clean_text.endswith("."):
            clean_text += "."
            
        return f"{start_phrase} {clean_text}"

    def generate_response(self, prompt):
        if self.llm is None: return "Model missing."
        output = self.llm(
            prompt, 
            max_tokens=50,       # Force brevity for chat agents
            temperature=0.0,    # Literal mode
            repeat_penalty=2.0, # Stop loops
            echo=False
        )
        return output['choices'][0]['text'].strip()

    def analyzer_agent(self, error, context):
        start = "The error is"
        prompt = f"Code: {context}\nError: {error}\nTask: Identify the bug in 10 words or less.\nResult: {start}"
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def explainer_agent(self, analysis, knowledge):
        start = "Fix:"
        prompt = f"""
        [STRICT MODE]
        Knowledge: {knowledge}
        Bug: {analysis}
        Constraint: Do not guess variable meanings. Do not use words not found in the code.
        Task: Provide a 1-sentence fix.
        Result: {start}"""
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def verifier_agent(self, explanation):
        start = "Status:"
        prompt = f"Fix: {explanation}\nTask: Is this safe? Answer in 5 words.\nResult: {start}"
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def code_fixer_agent(self, context, error):
        """Rewrites the entire script to fix the detected error."""
        prompt = f"""
        [SYSTEM: DYNAMIC REPAIR]
        Broken Code: 
        {context}

        Error Detected: 
        {error}

        Task: Rewrite the code to fix this error. Ensure the code is safe and complete.
        Result: ```python"""
        
        # Using a higher max_tokens (300) so the model can write the full file
        output = self.llm(
            prompt, 
            max_tokens=300, 
            temperature=0.0, 
            stop=["```"], 
            echo=False
        )
        return output['choices'][0]['text'].strip()

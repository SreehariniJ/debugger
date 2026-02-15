class DebuggingAgents:
    def __init__(self):
        # Point to the NEW small model you just downloaded
        self.llm = LlamaCpp(
            model_path="models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
            n_ctx=2048,
            temperature=0.2
        )

import os
import urllib.request

def setup():
    # Create models folder locally (Git will ignore its contents)
    if not os.path.exists("models"):
        os.makedirs("models")
    
    # URL for the Qwen 1.5B model - Small and fast!
    model_url = "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
    save_path = "models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"

    if os.path.exists(save_path):
        print("✅ AI Model already exists locally.")
    else:
        print("⏳ Downloading the AI 'Brain' (1.5GB)... Please wait.")
        urllib.request.urlretrieve(model_url, save_path)
        print(f"🎉 Success! Model saved to {save_path}")

if __name__ == "__main__":
    setup()

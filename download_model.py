import os
import urllib.request

def setup():
    # Create models folder if it doesn't exist
    if not os.path.exists("models"):
        os.makedirs("models")
        print("📁 Created 'models' directory.")

    model_url = "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
    save_path = "models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"

    if os.path.exists(save_path):
        print("✅ Model already exists in /models.")
    else:
        print("⏳ Downloading Qwen 2.5 Coder (1.5B)... This may take a few minutes.")
        urllib.request.urlretrieve(model_url, save_path)
        print(f"🎉 Download complete! Saved to {save_path}")

if __name__ == "__main__":
    setup()

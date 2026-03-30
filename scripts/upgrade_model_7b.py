import os
import urllib.request
import sys

def download_progress(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(100, int(downloaded * 100 / total_size))
        sys.stdout.write(f"\rDownloading 7B Model... {percent}% ({downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB)")
        sys.stdout.flush()

def setup():
    if not os.path.exists("models"):
        os.makedirs("models")
    
    # URL for Qwen 2.5 Coder 7B Instruct (Q4_K_M)
    model_url = "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
    save_path = "models/qwen2.5-coder-7b-instruct-q4_k_m.gguf"

    if os.path.exists(save_path):
        print("\n✅ Qwen 7B Model already exists locally.")
    else:
        print("\n⏳ Downloading the AI 'Brain' (~4.7GB)... Please wait, this may take a while depending on your connection.")
        urllib.request.urlretrieve(model_url, save_path, download_progress)
        print(f"\n🎉 Success! Model saved to {save_path}")

if __name__ == "__main__":
    setup()

from huggingface_hub import hf_hub_download

# Define the model details
repo_id = "MaziyarPanahi/Llama-3-8B-Instruct-v0.1-GGUF"
filename = "Llama-3-8B-Instruct-v0.1.Q4_K_M.gguf"
local_dir = "models"

print(f"Starting download of {filename} to {local_dir} folder...")

# This function downloads the file directly to your local folder
path = hf_hub_download(
    repo_id=repo_id,
    filename=filename,
    local_dir=local_dir,
    local_dir_use_symlinks=False
)

print(f"Successfully downloaded to: {path}")

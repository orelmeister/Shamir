
import importlib
import os
import sys
import requests
from dotenv import load_dotenv

# --- Configuration ---
LIBRARIES_TO_CHECK = [
    "aiohttp",
    "bs4",
    "dotenv",
    "google.cloud.aiplatform",
    "langchain",
    "langchain_core",
    "langchain_google_vertexai",
    "langchain_ollama",
    "langchain_deepseek",
    "pytz",
    "yfinance",
    "requests"
]

REQUIRED_ENV_VARS = [
    "FMP_API_KEY",
    "POLYGON_API_KEY",
    "GOOGLE_CLOUD_PROJECT",
    "DEEPSEEK_API_KEY"
]

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL_TO_CHECK = "llama3.1:8b"

# --- Functions ---

def check_libraries():
    """Checks if all required Python libraries are installed."""
    print("--- Checking Python Libraries ---")
    missing_libs = []
    for lib in LIBRARIES_TO_CHECK:
        try:
            importlib.import_module(lib)
            print(f"[ OK ] {lib}")
        except ImportError:
            package_name = lib
            if lib == "bs4": package_name = "beautifulsoup4"
            if lib == "dotenv": package_name = "python-dotenv"
            if "google.cloud" in lib: package_name = "google-cloud-aiplatform"
            
            print(f"[FAIL] {lib} -> MISSING. Please run: pip install {package_name}")
            missing_libs.append(lib)
    return not missing_libs

def check_env_vars():
    """Checks if all required environment variables are set."""
    print("\n--- Checking Environment Variables ---")
    load_dotenv()
    missing_vars = []
    for var in REQUIRED_ENV_VARS:
        if var in os.environ and os.environ[var]:
            # Mask the key for security
            masked_key = os.environ[var][:4] + "****"
            print(f"[ OK ] {var} is set ({masked_key})")
        else:
            print(f"[FAIL] {var} -> MISSING or empty in .env file.")
            missing_vars.append(var)
    return not missing_vars

def check_ollama_service():
    """Checks if the Ollama service is running and the model is available."""
    print("\n--- Checking Ollama Service ---")
    # 1. Check if the service is running
    try:
        response = requests.get(OLLAMA_BASE_URL)
        response.raise_for_status()
        print(f"[ OK ] Ollama server is running and accessible at {OLLAMA_BASE_URL}")
    except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        print(f"[FAIL] Ollama server is NOT RUNNING or accessible at {OLLAMA_BASE_URL}.")
        print(f"       Error: {e}")
        return False

    # 2. Check if the specific model is available
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
        model_names = [m["name"] for m in models]
        
        if OLLAMA_MODEL_TO_CHECK in model_names:
            print(f"[ OK ] Ollama model '{OLLAMA_MODEL_TO_CHECK}' is available.")
            return True
        else:
            print(f"[FAIL] Ollama model '{OLLAMA_MODEL_TO_CHECK}' is NOT AVAILABLE.")
            print(f"       Available models: {model_names}")
            print(f"       Please run: ollama pull {OLLAMA_MODEL_TO_CHECK}")
            return False
    except Exception as e:
        print(f"[FAIL] Could not verify Ollama models. Error: {e}")
        return False

# --- Main Execution ---

if __name__ == "__main__":
    print("Starting environment check for the Multi-Agent Trading System...")
    
    libs_ok = check_libraries()
    vars_ok = check_env_vars()
    ollama_ok = check_ollama_service()
    
    print("\n--- Summary ---")
    if libs_ok and vars_ok and ollama_ok:
        print("\n[SUCCESS] Your environment is configured correctly. You are ready to run the main script.")
        sys.exit(0)
    else:
        print("\n[FAILURE] Your environment has issues. Please fix the [FAIL] items above before running the main script.")
        sys.exit(1)

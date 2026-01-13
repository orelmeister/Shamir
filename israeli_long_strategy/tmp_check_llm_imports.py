import importlib.util as u

mods = [
    "langchain_deepseek",
    "langchain_google_genai",
    "langchain_ollama",
    "langchain_openai",
]

for m in mods:
    print(m, bool(u.find_spec(m)))

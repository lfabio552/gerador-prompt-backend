import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('GOOGLE_API_KEY')
print(f"Testando com a chave que começa com: {api_key[:5]}...")

genai.configure(api_key=api_key)

print("\n--- LISTA DE MODELOS DISPONÍVEIS PARA SUA CHAVE ---")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
except Exception as e:
    print(f"Erro ao listar modelos: {e}")

print("\n---------------------------------------------------")
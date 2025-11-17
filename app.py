import os
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# --- NOSSAS NOVAS FERRAMENTAS ---
from pytube import YouTube
import xml.etree.ElementTree as ET # Para ler a legenda
# ---------------------------------

load_dotenv() 
app = Flask(__name__)
CORS(app) 

try:
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("Modelo Gemini configurado com sucesso!")
except Exception as e:
    print(f"Erro ao configurar o modelo Gemini: {e}")
    model = None

# --- ROTAS 1 e 2 (Inalteradas) ---
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        prompt = f"Ideia: {data.get('idea')}. Estilo: {data.get('style')}. Crie prompt imagem detalhado em inglês."
        return jsonify({'advanced_prompt': model.generate_content(prompt).text})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/generate-veo3-prompt', methods=['POST'])
def generate_veo3_prompt():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        prompt = f"Crie prompt video Google Veo. Cena: {data.get('scene')}. Em inglês."
        return jsonify({'advanced_prompt': model.generate_content(prompt).text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 3: RESUMIDOR (Versão Pytube) ---
@app.route('/summarize-video', methods=['POST'])
def summarize_video():
    if not model: return jsonify({'error': 'Modelo Gemini não configurado.'}), 500
    data = request.json
    video_url = data.get('url')
    if not video_url: return jsonify({'error': 'Link vazio.'}), 400

    try:
        print(f"Processando com Pytube: {video_url}")
        
        # 1. Cria o objeto do YouTube
        yt = YouTube(video_url)
        
        # 2. Busca a legenda (caption)
        # Tenta pegar em PT, depois EN, depois PT-auto, depois EN-auto
        caption = yt.captions.get_by_language_code('pt')
        if not caption:
            print("Legenda PT não achada. Tentando EN...")
            caption = yt.captions.get_by_language_code('en')
        if not caption:
             print("Legenda EN não achada. Tentando PT (Auto)...")
             caption = yt.captions.get_by_language_code('a.pt') # 'a' = Auto-Gerada
        if not caption:
             print("Legenda PT-Auto não achada. Tentando EN (Auto)...")
             caption = yt.captions.get_by_language_code('a.en')
        
        if not caption:
            print("Nenhuma legenda encontrada.")
            return jsonify({'error': 'Este vídeo não possui legendas em PT ou EN (nem automáticas).'}), 400

        # 3. Baixa e processa a legenda (que vem em XML)
        print(f"Legenda encontrada: {caption.code}")
        caption_xml = caption.xml_captions
        
        # Lê o XML e junta o texto
        root = ET.fromstring(caption_xml)
        full_text = " ".join([elem.text for elem in root.iter('text') if elem.text])
        
        if not full_text:
             return jsonify({'error': 'Legenda encontrada, mas estava vazia.'}), 400

        print(f"Legenda OK! Tamanho: {len(full_text)}. Enviando ao Gemini...")

        # 4. Envia ao Gemini
        prompt = f"""
        Resuma este vídeo do YouTube em Português do Brasil.
        ## 🎬 Título Criativo
        **Resumo:** (Parágrafo curto)
        **💡 Pontos Chave:** (Lista com emojis)
        **🏁 Conclusão:**
        Transcrição: "{full_text[:30000]}" 
        """
        
        response = model.generate_content(prompt)
        return jsonify({'summary': response.text})

    except Exception as e:
        print(f"ERRO FINAL (Pytube): {e}")
        error_msg = str(e)
        if "members only" in error_msg:
            return jsonify({'error': 'Este vídeo é apenas para membros.'}), 400
        if "Video unavailable" in error_msg:
             return jsonify({'error': 'Este vídeo está indisponível ou é privado.'}), 400
        return jsonify({'error': f'Erro no Pytube: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
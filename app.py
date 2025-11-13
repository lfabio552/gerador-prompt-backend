import os
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

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

@app.route('/summarize-video', methods=['POST'])
def summarize_video():
    if not model: return jsonify({'error': 'Modelo Gemini não configurado.'}), 500
    data = request.json
    video_url = data.get('url')
    if not video_url: return jsonify({'error': 'Link vazio.'}), 400

    try:
        print(f"Processando: {video_url}")
        video_id = ""
        if "v=" in video_url: video_id = video_url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in video_url: video_id = video_url.split("youtu.be/")[1].split("?")[0]
        
        if not video_id: return jsonify({'error': 'Link inválido.'}), 400

        # Tenta listar legendas (agora com a versão do GitHub, isso vai funcionar)
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            try:
                transcript = transcript_list.find_transcript(['pt', 'en'])
            except:
                transcript = transcript_list[0] # Pega qualquer uma

            transcript_data = transcript.fetch()
            full_text = " ".join([t['text'] for t in transcript_data])
            
        except Exception as e:
            print(f"Erro legenda: {e}")
            return jsonify({'error': 'Erro ao buscar legendas. O vídeo pode não ter legendas ou o YouTube bloqueou o acesso.'}), 400

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
        return jsonify({'error': f'Erro: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
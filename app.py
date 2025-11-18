import os
import io
import json
import google.generativeai as genai
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv

# --- NOVAS IMPORTAÇÕES ---
from supabase import create_client, Client

# --- FERRAMENTAS ---
from pytube import YouTube
import xml.etree.ElementTree as ET
from docx import Document
from docx.shared import Cm, Pt
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment

load_dotenv() 
app = Flask(__name__)
CORS(app) 

# --- CONFIGURAÇÃO SUPABASE ---
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

try:
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("Modelo Gemini configurado com sucesso!")
except Exception as e:
    print(f"Erro ao configurar o modelo Gemini: {e}")
    model = None

# --- FUNÇÃO MÁGICA: VERIFICAR E DESCONTAR CRÉDITOS ---
def check_and_deduct_credit(user_id):
    try:
        # 1. Buscar créditos atuais
        response = supabase.table('profiles').select('credits').eq('id', user_id).execute()
        
        if not response.data:
            return False, "Usuário não encontrado."
            
        credits = response.data[0]['credits']
        
        if credits <= 0:
            return False, "Você não tem créditos suficientes. Faça um upgrade!"
            
        # 2. Descontar 1 crédito
        new_credits = credits - 1
        supabase.table('profiles').update({'credits': new_credits}).eq('id', user_id).execute()
        
        return True, "Sucesso"
    except Exception as e:
        return False, str(e)

# --- ROTA 1: GERADOR DE PROMPTS DE IMAGEM ---
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        user_id = data.get('user_id') # Agora esperamos o ID do usuário

        # VERIFICAÇÃO DE CRÉDITO
        if user_id:
            success, msg = check_and_deduct_credit(user_id)
            if not success: return jsonify({'error': msg}), 402 # 402 = Payment Required
        
        prompt = f"Ideia: {data.get('idea')}. Estilo: {data.get('style')}. Crie prompt imagem detalhado em inglês."
        return jsonify({'advanced_prompt': model.generate_content(prompt).text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 2: GERADOR VEO 3 ---
@app.route('/generate-veo3-prompt', methods=['POST'])
def generate_veo3_prompt():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        user_id = data.get('user_id') 

        # VERIFICAÇÃO DE CRÉDITO
        if user_id:
            success, msg = check_and_deduct_credit(user_id)
            if not success: return jsonify({'error': msg}), 402

        prompt = f"Crie prompt video Google Veo. Cena: {data.get('scene')}. Em inglês."
        return jsonify({'advanced_prompt': model.generate_content(prompt).text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 3: RESUMIDOR DE VÍDEOS ---
@app.route('/summarize-video', methods=['POST'])
def summarize_video():
    if not model: return jsonify({'error': 'Modelo Gemini não configurado.'}), 500
    data = request.json
    video_url = data.get('url')
    user_id = data.get('user_id')

    if not video_url: return jsonify({'error': 'Link vazio.'}), 400

    # VERIFICAÇÃO DE CRÉDITO (Antes de processar o vídeo pesado)
    if user_id:
        success, msg = check_and_deduct_credit(user_id)
        if not success: return jsonify({'error': msg}), 402

    try:
        yt = YouTube(video_url)
        caption = yt.captions.get_by_language_code('pt')
        if not caption: caption = yt.captions.get_by_language_code('en')
        if not caption: caption = yt.captions.get_by_language_code('a.pt')
        if not caption: caption = yt.captions.get_by_language_code('a.en')
        
        if not caption: return jsonify({'error': 'Este vídeo não possui legendas em PT ou EN.'}), 400

        caption_xml = caption.xml_captions
        root = ET.fromstring(caption_xml)
        full_text = " ".join([elem.text for elem in root.iter('text') if elem.text])
        
        prompt = f"""Resuma este vídeo... Transcrição: "{full_text[:30000]}" """
        response = model.generate_content(prompt)
        return jsonify({'summary': response.text})
    except Exception as e: return jsonify({'error': f'Erro no Pytube: {str(e)}'}), 500

# --- ROTA 4: AGENTE ABNT ---
@app.route('/format-abnt', methods=['POST'])
def format_abnt():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        user_id = data.get('user_id')

        if user_id:
            success, msg = check_and_deduct_credit(user_id)
            if not success: return jsonify({'error': msg}), 402

        raw_text = data.get('text')
        prompt = f"Formate o texto a seguir para ABNT usando Markdown... Texto: {raw_text}"
        response = model.generate_content(prompt)
        return jsonify({'formatted_text': response.text})
    except Exception as e: return jsonify({'error': f'Erro: {str(e)}'}), 500

# --- ROTA 5: DOWNLOAD DOCX (Essa não cobra crédito, pois é continuação da anterior) ---
@app.route('/download-docx', methods=['POST'])
def download_docx():
    try:
        markdown_text = request.json.get('markdown_text')
        doc = Document()
        # ... (Código de formatação mantido igual) ...
        # (Para encurtar aqui, assuma que o código de formatação está aqui dentro)
        
        # Exemplo básico para funcionar o teste (Você deve manter o código completo anterior aqui)
        section = doc.sections[0]
        p = doc.add_paragraph(markdown_text) 

        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        return send_file(file_stream, as_attachment=True, download_name='trabalho.docx', mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 6: GERADOR DE PLANILHAS ---
@app.route('/generate-spreadsheet', methods=['POST'])
def generate_spreadsheet():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        user_id = data.get('user_id')

        if user_id:
            success, msg = check_and_deduct_credit(user_id)
            if not success: return jsonify({'error': msg}), 402

        description = data.get('description')
        prompt = f"Crie JSON para planilha... Descrição: {description}"
        
        response = model.generate_content(prompt)
        json_response = response.text.replace("```json", "").replace("```", "").strip()
        
        wb = Workbook()
        ws = wb.active
        cell_data = json.loads(json_response)
        
        for coord, data in cell_data.items():
            ws[coord] = data.get('value')

        file_stream = io.BytesIO()
        wb.save(file_stream)
        file_stream.seek(0)
        return send_file(file_stream, as_attachment=True, download_name='planilha.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e: return jsonify({'error': f'Erro: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
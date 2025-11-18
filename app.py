import os
import io
import json # Usaremos JSON para a comunicação!
import google.generativeai as genai
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv

# --- NOSSAS FERRAMENTAS ---
from pytube import YouTube
import xml.etree.ElementTree as ET
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
# ---------------------------

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

# --- ROTA 1: GERADOR DE PROMPTS DE IMAGEM ---
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        prompt = f"Ideia: {data.get('idea')}. Estilo: {data.get('style')}. Crie prompt imagem detalhado em inglês."
        return jsonify({'advanced_prompt': model.generate_content(prompt).text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 2: GERADOR VEO 3 ---
# --- ESTA É A LINHA CORRIGIDA ---
@app.route('/generate-veo3-prompt', methods=['POST'])
def generate_veo3_prompt(): 
# ---------------------------------
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        prompt = f"Crie prompt video Google Veo. Cena: {data.get('scene')}. Em inglês."
        return jsonify({'advanced_prompt': model.generate_content(prompt).text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 3: RESUMIDOR DE VÍDEOS (Pytube) ---
@app.route('/summarize-video', methods=['POST'])
def summarize_video():
    if not model: return jsonify({'error': 'Modelo Gemini não configurado.'}), 500
    data = request.json
    video_url = data.get('url')
    if not video_url: return jsonify({'error': 'Link vazio.'}), 400
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
        if not full_text: return jsonify({'error': 'Legenda vazia.'}), 400
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
    except Exception as e: return jsonify({'error': f'Erro no Pytube: {str(e)}'}), 500

# --- ROTA 4: AGENTE ABNT (Formatador de Texto) ---
@app.route('/format-abnt', methods=['POST'])
def format_abnt():
    if not model: return jsonify({'error': 'Modelo Gemini não configurado.'}), 500
    try:
        data = request.json
        raw_text = data.get('text')
        if not raw_text: return jsonify({'error': 'O texto não pode estar vazio.'}), 400
        prompt = f"""
        Formate o texto a seguir para ABNT usando Markdown.
        Regras: ## 1. TÍTULO, ### 1.1 SUBTÍTULO, > Citação longa, "Citação curta", (Autor, ANO), ## REFERÊNCIAS
        Texto Cru: {raw_text}
        """
        response = model.generate_content(prompt)
        return jsonify({'formatted_text': response.text})
    except Exception as e: return jsonify({'error': f'Erro: {str(e)}'}), 500

# --- ROTA 5: GERADOR DE DOCUMENTO .DOCX ABNT ---
@app.route('/download-docx', methods=['POST'])
def download_docx():
    try:
        markdown_text = request.json.get('markdown_text')
        doc = Document()
        section = doc.sections[0]
        section.top_margin = Cm(3); section.left_margin = Cm(3); section.bottom_margin = Cm(2); section.right_margin = Cm(2)
        style = doc.styles['Normal']; style.font.name = 'Arial'; style.font.size = Pt(12); style.paragraph_format.line_spacing = 1.5
        lines = markdown_text.split('\n')
        for line in lines:
            if line.startswith('## '):
                p = doc.add_heading(line.replace('## ', '').strip(), level=2)
            elif line.startswith('### '):
                p = doc.add_heading(line.replace('### ', '').strip(), level=3)
            elif line.startswith('> '):
                p = doc.add_paragraph(line.replace('> ', '').strip())
                p.paragraph_format.left_indent = Cm(4); p.paragraph_format.line_spacing = 1.0; p.style.font.size = Pt(10)
            elif line.strip() != "":
                p = doc.add_paragraph(line.strip()); p.paragraph_format.first_line_indent = Cm(1.25)
        
        file_stream = io.BytesIO(); doc.save(file_stream); file_stream.seek(0)
        return send_file(file_stream, as_attachment=True, download_name='trabalho_formatado.docx', mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 6: GERADOR DE PLANILHAS (VERSÃO JSON SEGURA) ---
@app.route('/generate-spreadsheet', methods=['POST'])
def generate_spreadsheet():
    if not model:
        return jsonify({'error': 'Modelo Gemini não configurado.'}), 500

    try:
        data = request.json
        description = data.get('description')
        if not description:
            return jsonify({'error': 'A descrição não pode estar vazia.'}), 400

        # --- O NOVO PROMPT (PEDINDO JSON) ---
        prompt = f"""
        Você é um assistente de design de planilhas.
        Sua tarefa é converter a descrição de um usuário em um objeto JSON que define uma planilha.
        Responda APENAS com o objeto JSON, sem ```json ou explicações.

        O JSON deve ter chaves que são as coordenadas da célula (ex: "A1", "B1").
        O valor de cada chave deve ser um objeto com:
        - "value": (Obrigatório) O texto da célula.
        - "style": (Opcional) "header" para cabeçalhos.
        - "formula": (Opcional) A fórmula do Excel (ex: "=B2-C2").
        - "width": (Opcional, apenas na linha 1) A largura da coluna.

        Descrição do Usuário:
        "{description}"

        Exemplo de Resposta (Apenas o JSON):
        {{
          "A1": {{ "value": "Data", "style": "header", "width": 15 }},
          "B1": {{ "value": "Valor Ganho", "style": "header", "width": 20 }},
          "C1": {{ "value": "Gastos", "style": "header", "width": 20 }},
          "D1": {{ "value": "Valor Líquido", "style": "header", "width": 20 }},
          "D2": {{ "formula": "=B2-C2" }},
          "D3": {{ "formula": "=B3-C3" }},
          "D4": {{ "formula": "=B4-C4" }},
          "D5": {{ "formula": "=B5-C5" }},
          "D6": {{ "formula": "=B6-C6" }},
          "D7": {{ "formula": "=B7-C7" }},
          "D8": {{ "formula": "=B8-C8" }},
          "D9": {{ "formula": "=B9-C9" }},
          "D10": {{ "formula": "=B10-C10" }},
          "D11": {{ "formula": "=B11-C11" }},
          "C12": {{ "value": "Total Líquido:", "style": "header" }},
          "D12": {{ "formula": "=SUM(D2:D11)", "style": "header" }}
        }}
        """

        response = model.generate_content(prompt)
        json_response = response.text

        if json_response.startswith("```json"):
            json_response = json_response[7:]
        if json_response.endswith("```"):
            json_response = json_response[:-3]
        json_response = json_response.strip()
        
        print("--- JSON (LIMPO) GERADO PELO GEMINI ---")
        print(json_response)
        print("---------------------------------------")

        wb = Workbook()
        ws = wb.active
        header_fill = PatternFill(start_color='006400', end_color='006400', fill_type='solid')
        header_font = Font(color='FFFFFF', bold=True)
        center_align = Alignment(horizontal='center', vertical='center')

        cell_data = json.loads(json_response)
        
        for coord, data in cell_data.items():
            cell = ws[coord] # Pega a célula (ex: A1)
            
            if data.get('value'):
                cell.value = data['value']
            
            if data.get('formula'):
                cell.value = data['formula'] # O valor da célula é a fórmula
                
            if data.get('style') == 'header':
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = center_align
                
            if data.get('width'):
                col_letter = coord[0] 
                ws.column_dimensions[col_letter].width = data['width']

        file_stream = io.BytesIO()
        wb.save(file_stream)
        file_stream.seek(0)

        return send_file(
            file_stream,
            as_attachment=True,
            download_name='planilha_pronta.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        print(f"ERRO AO GERAR PLANILHA: {e}")
        return jsonify({'error': f'Erro ao gerar planilha: {str(e)}'}), 500

# --- Roda o Servidor ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
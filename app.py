import os
import google.generativeai as genai
import io
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from flask import send_file
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

# --- ROTA 4: AGENTE DE FORMATAÇÃO ABNT ---
@app.route('/format-abnt', methods=['POST'])
def format_abnt():
    if not model:
        return jsonify({'error': 'Modelo Gemini não configurado.'}), 500

    try:
        data = request.json
        raw_text = data.get('text')

        if not raw_text:
            return jsonify({'error': 'O texto não pode estar vazio.'}), 400

        # O prompt "mágico" que ensina a IA a ser um professor de ABNT
        prompt = f"""
        Você é um especialista sênior em formatação de trabalhos acadêmicos pelas normas da ABNT.
        Sua tarefa é pegar o texto "cru" do usuário e formatá-lo 100% em ABNT, usando Markdown para a estilização.

        Regras de Formatação (Markdown):
        - **Títulos (Ex: 1. INTRODUÇÃO):** Use `##` (ex: `## 1. INTRODUÇÃO`).
        - **Subtítulos (Ex: 1.1 Metodologia):** Use `###` (ex: `### 1.1 METODOLOGIA`).
        - **Citações diretas curtas (até 3 linhas):** Mantenha no corpo do texto, entre aspas duplas, com (AUTOR, ANO, p. XX).
        - **Citações diretas longas (mais de 3 linhas):** Crie um bloco de citação (>), com recuo, fonte menor (embora markdown não controle fonte), e (AUTOR, ANO, p. XX).
        - **Citações indiretas:** (Autor, ANO).
        - **Referências:** No final, crie uma seção `## REFERÊNCIAS` e liste todas as fontes citadas em ordem alfabética, formatadas corretamente (Ex: SOBRENOME, Nome. Título. Cidade: Editora, ANO.)
        - **Negrito:** Use `**negrito**` apenas onde a ABNT permitir (geralmente títulos).

        Por favor, formate o texto abaixo. Não resuma, apenas formate.

        --- TEXTO CRU DO USUÁRIO ---
        {raw_text}
        --- FIM DO TEXTO CRU ---

        O resultado deve ser apenas o texto formatado em Markdown.
        """
        
        response = model.generate_content(prompt)
        return jsonify({'formatted_text': response.text})

    except Exception as e:
        print(f"ERRO ABNT: {e}")
        return jsonify({'error': f'Erro ao formatar o texto: {str(e)}'}), 500

# --- ROTA 5: GERADOR DE DOCUMENTO .DOCX ABNT ---
@app.route('/download-docx', methods=['POST'])
def download_docx():
    try:
        markdown_text = request.json.get('markdown_text')
        
        # 1. Criar o documento e definir estilos ABNT
        doc = Document()
        
        # Margens ABNT (Superior/Esquerda 3cm, Inferior/Direita 2cm)
        section = doc.sections[0]
        section.top_margin = Cm(3)
        section.left_margin = Cm(3)
        section.bottom_margin = Cm(2)
        section.right_margin = Cm(2)
        
        # Fonte padrão (Arial 12)
        style = doc.styles['Normal']
        style.font.name = 'Arial'
        style.font.size = Pt(12)
        style.paragraph_format.line_spacing = 1.5 # Espaçamento 1.5
        style.paragraph_format.space_after = Pt(0) # Sem espaço extra pós-parágrafo

        # 2. Ler o Markdown e "Desenhar" o Word
        lines = markdown_text.split('\n')
        
        for line in lines:
            if line.startswith('## '):
                # Título (ex: 1. INTRODUÇÃO)
                text = line.replace('## ', '').strip()
                p = doc.add_heading(text, level=2)
                p.style.font.name = 'Arial'
                p.style.font.size = Pt(12)
                p.style.font.bold = True
            
            elif line.startswith('### '):
                # Subtítulo (ex: 1.1 Objetivos)
                text = line.replace('### ', '').strip()
                p = doc.add_heading(text, level=3)
                p.style.font.name = 'Arial'
                p.style.font.size = Pt(12)

            elif line.startswith('> '):
                # Citação longa
                text = line.replace('> ', '').strip()
                p = doc.add_paragraph(text)
                # Recuo ABNT de 4cm para citação
                p.paragraph_format.left_indent = Cm(4)
                p.paragraph_format.line_spacing = 1.0 # Espaçamento simples
                p.style.font.size = Pt(10) # Fonte menor
            
            elif line.strip() == "":
                # Linha em branco (pular)
                continue
                
            else:
                # Parágrafo normal
                p = doc.add_paragraph(line.strip())
                # Recuo de primeira linha (parágrafo ABNT)
                p.paragraph_format.first_line_indent = Cm(1.25)
        
        # 3. Salvar o documento na memória
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0) # Volta para o começo do "arquivo"

        # 4. Enviar o arquivo para o usuário
        return send_file(
            file_stream,
            as_attachment=True,
            download_name='trabalho_formatado.docx',
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        print(f"ERRO AO GERAR DOCX: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
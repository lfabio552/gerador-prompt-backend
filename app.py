import os
import io
import json
import google.generativeai as genai
import stripe
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client

# --- FERRAMENTAS ---
from pytube import YouTube
import xml.etree.ElementTree as ET
from docx import Document
from docx.shared import Cm, Pt
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from pypdf import PdfReader # Nova ferramenta para ler PDF

load_dotenv() 
app = Flask(__name__)
CORS(app) 

# --- CONFIGURAÇÕES ---
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
frontend_url = os.environ.get("FRONTEND_URL")
endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

try:
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    # Modelo de texto
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("Modelo Gemini configurado com sucesso!")
except Exception as e:
    print(f"Erro ao configurar o modelo Gemini: {e}")
    model = None

# --- FUNÇÃO DE CRÉDITOS ---
def check_and_deduct_credit(user_id):
    try:
        response = supabase.table('profiles').select('credits, is_pro').eq('id', user_id).execute()
        if not response.data: return False, "Usuário não encontrado."
        user_data = response.data[0]
        if user_data.get('is_pro'): return True, "Sucesso (VIP)"
        if user_data['credits'] <= 0: return False, "Você não tem créditos suficientes. Assine o plano PRO!"
        
        supabase.table('profiles').update({'credits': user_data['credits'] - 1}).eq('id', user_id).execute()
        return True, "Sucesso"
    except Exception as e: return False, str(e)

# --- FUNÇÃO AUXILIAR: GERAR EMBEDDING (Vetor Numérico) ---
def get_embedding(text):
    try:
        # Usa o modelo específico do Google para criar vetores
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
            title="Documento do Usuário"
        )
        return result['embedding']
    except Exception as e:
        print(f"Erro ao gerar embedding: {e}")
        return None

# --- ROTA 1: IMAGEM ---
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            success, msg = check_and_deduct_credit(user_id)
            if not success: return jsonify({'error': msg}), 402
        
        prompt = f"Ideia: {data.get('idea')}. Estilo: {data.get('style')}. Crie prompt imagem detalhado em inglês."
        return jsonify({'advanced_prompt': model.generate_content(prompt).text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 2: VEO 3 ---
@app.route('/generate-veo3-prompt', methods=['POST'])
def generate_veo3_prompt():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            success, msg = check_and_deduct_credit(user_id)
            if not success: return jsonify({'error': msg}), 402

        prompt = f"Crie prompt video Google Veo. Cena: {data.get('scene')}. Em inglês."
        return jsonify({'advanced_prompt': model.generate_content(prompt).text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 3: RESUMIDOR ---
@app.route('/summarize-video', methods=['POST'])
def summarize_video():
    if not model: return jsonify({'error': 'Modelo Gemini não configurado.'}), 500
    data = request.json
    video_url = data.get('url')
    user_id = data.get('user_id')
    if not video_url: return jsonify({'error': 'Link vazio.'}), 400

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
        
        if not full_text: return jsonify({'error': 'Legenda vazia.'}), 400

        prompt = f"""Resuma este vídeo... Transcrição: "{full_text[:30000]}" """
        response = model.generate_content(prompt)
        return jsonify({'summary': response.text})
    except Exception as e: return jsonify({'error': f'Erro no Pytube: {str(e)}'}), 500

# --- ROTA 4: ABNT ---
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

# --- ROTA 5: DOWNLOAD DOCX ---
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

# --- ROTA 6: PLANILHAS ---
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
        prompt = f"""
        Crie um objeto JSON para uma planilha Excel baseada em: "{description}".
        Responda APENAS o JSON.
        Formato: {{ "A1": {{ "value": "Nome", "style": "header", "width": 20 }} }}
        """
        response = model.generate_content(prompt)
        json_response = response.text.replace("```json", "").replace("```", "").strip()
        
        if json_response.startswith("{"): pass
        else:
             start = json_response.find("{")
             end = json_response.rfind("}") + 1
             if start != -1 and end != -1: json_response = json_response[start:end]

        wb = Workbook(); ws = wb.active
        header_fill = PatternFill(start_color='006400', end_color='006400', fill_type='solid')
        header_font = Font(color='FFFFFF', bold=True)
        center_align = Alignment(horizontal='center', vertical='center')

        cell_data = json.loads(json_response)
        for coord, data in cell_data.items():
            cell = ws[coord]
            if data.get('value'): cell.value = data['value']
            if data.get('formula'): cell.value = data['formula']
            if data.get('style') == 'header':
                cell.fill = header_fill; cell.font = header_font; cell.alignment = center_align
            if data.get('width'):
                ws.column_dimensions[coord[0]].width = data['width']

        file_stream = io.BytesIO(); wb.save(file_stream); file_stream.seek(0)
        return send_file(file_stream, as_attachment=True, download_name='planilha.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e: return jsonify({'error': f'Erro: {str(e)}'}), 500

# --- ROTA 7: CHECKOUT DO STRIPE ---
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        if not stripe.api_key: return jsonify({'error': 'Erro Stripe Key'}), 500
        data = request.json
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': os.environ.get('STRIPE_PRICE_ID'), 'quantity': 1}],
            mode='subscription', 
            success_url=f'{frontend_url}/?success=true',
            cancel_url=f'{frontend_url}/?canceled=true',
            metadata={'user_id': data.get('user_id')},
            customer_email=data.get('email')
        )
        return jsonify({'url': checkout_session.url})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 8: WEBHOOK ---
@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError: return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError: return 'Invalid signature', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session.get('metadata', {}).get('user_id')
        if user_id:
            supabase.table('profiles').update({'is_pro': True, 'stripe_customer_id': session.get('customer')}).eq('id', user_id).execute()
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        stripe_customer_id = subscription.get('customer')
        if stripe_customer_id:
            resp = supabase.table('profiles').select('id').eq('stripe_customer_id', stripe_customer_id).execute()
            if resp.data:
                user_id = resp.data[0]['id']
                supabase.table('profiles').update({'is_pro': False}).eq('id', user_id).execute()

    return 'Success', 200

# --- ROTA 9: PORTAL CLIENTE ---
@app.route('/create-portal-session', methods=['POST'])
def create_portal_session():
    try:
        user_id = request.json.get('user_id')
        resp = supabase.table('profiles').select('stripe_customer_id').eq('id', user_id).execute()
        if not resp.data or not resp.data[0]['stripe_customer_id']:
            return jsonify({'error': 'Sem assinatura.'}), 400
        
        portal_session = stripe.billing_portal.Session.create(
            customer=resp.data[0]['stripe_customer_id'],
            return_url=f'{frontend_url}/',
        )
        return jsonify({'url': portal_session.url})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- ROTA 10: UPLOAD DE PDF (RAG) ---
@app.route('/upload-document', methods=['POST'])
def upload_document():
    try:
        # 1. Receber arquivo e usuário
        user_id = request.form.get('user_id')
        file = request.files.get('file')
        
        if not user_id or not file:
            return jsonify({'error': 'Usuário ou arquivo faltando.'}), 400

        # Verificar crédito (Upload gasta 1 crédito se não for PRO)
        success, msg = check_and_deduct_credit(user_id)
        if not success: return jsonify({'error': msg}), 402

        print(f"Processando PDF: {file.filename}")

        # 2. Ler o PDF
        pdf_reader = PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        
        if len(text) < 50:
            return jsonify({'error': 'Não consegui ler texto deste PDF. Ele pode ser uma imagem escaneada.'}), 400

        # 3. Salvar registro do documento no Supabase
        doc_response = supabase.table('documents').insert({
            'user_id': user_id,
            'filename': file.filename
        }).execute()
        
        document_id = doc_response.data[0]['id']

        # 4. Quebrar texto em pedaços (Chunks) e Gerar Embeddings
        # Vamos quebrar a cada 1000 caracteres aprox.
        chunk_size = 1000
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        print(f"Gerando embeddings para {len(chunks)} pedaços...")
        
        items_to_insert = []
        for chunk in chunks:
            embedding = get_embedding(chunk) # Usa o modelo do Google
            if embedding:
                items_to_insert.append({
                    'document_id': document_id,
                    'content': chunk,
                    'embedding': embedding
                })
        
        # 5. Salvar pedaços no Supabase
        # (O Supabase aceita insert em lote, é mais rápido)
        if items_to_insert:
            supabase.table('document_chunks').insert(items_to_insert).execute()

        return jsonify({'message': 'Documento processado com sucesso!', 'document_id': document_id})

    except Exception as e:
        print(f"ERRO UPLOAD: {e}")
        return jsonify({'error': str(e)}), 500

# --- ROTA 11: PERGUNTAR AO DOCUMENTO (RAG) ---
@app.route('/ask-document', methods=['POST'])
def ask_document():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        question = data.get('question')
        document_id = data.get('document_id') # Opcional: focar num doc específico
        user_id = data.get('user_id')

        if not question or not user_id:
            return jsonify({'error': 'Pergunta ou usuário faltando.'}), 400

        # 1. Verificar crédito (Perguntar também gasta? Vamos dizer que sim por enquanto)
        success, msg = check_and_deduct_credit(user_id)
        if not success: return jsonify({'error': msg}), 402

        # 2. Transformar a pergunta em números (Embedding)
        query_embedding = get_embedding(question)
        if not query_embedding:
            return jsonify({'error': 'Erro ao processar pergunta.'}), 500

        # 3. Buscar trechos parecidos no Supabase (RPC call)
        # Essa função 'match_documents' nós criamos no SQL lá atrás
        params = {
            'query_embedding': query_embedding,
            'match_threshold': 0.5, # Nível de similaridade (0 a 1)
            'match_count': 5,       # Pegar os 5 melhores trechos
            'user_id_filter': user_id
        }
        
        response_rpc = supabase.rpc('match_documents', params).execute()
        matches = response_rpc.data

        if not matches:
            return jsonify({'answer': 'Não encontrei informações sobre isso nos seus documentos.'})

        # 4. Montar o contexto para o Gemini
        context_text = "\n\n".join([item['content'] for item in matches])
        
        prompt = f"""
        Você é um assistente inteligente que responde perguntas baseadas em documentos fornecidos.
        
        Use APENAS o contexto abaixo para responder a pergunta do usuário.
        Se a resposta não estiver no contexto, diga que não sabe.
        
        --- CONTEXTO ---
        {context_text}
        ----------------
        
        Pergunta: {question}
        """

        response_gemini = model.generate_content(prompt)
        return jsonify({'answer': response_gemini.text})

    except Exception as e:
        print(f"ERRO CHAT PDF: {e}")
        return jsonify({'error': str(e)}), 500

# --- ROTA 12: TRADUTOR CORPORATIVO ---
@app.route('/corporate-translator', methods=['POST'])
def corporate_translator():
    if not model: return jsonify({'error': 'Modelo Gemini erro.'}), 500
    try:
        data = request.json
        user_id = data.get('user_id')
        
        # 1. Verifica Crédito
        if user_id:
            success, msg = check_and_deduct_credit(user_id)
            if not success: return jsonify({'error': msg}), 402

        # 2. Prepara o Prompt
        raw_text = data.get('text')
        tone = data.get('tone', 'Profissional') # Pode ser 'Diplomático', 'Executivo', etc.

        if not raw_text: return jsonify({'error': 'Texto vazio.'}), 400

        prompt = f"""
        Você é um especialista em comunicação corporativa e etiqueta empresarial.
        Sua tarefa é reescrever a mensagem abaixo para que ela fique extremamente {tone}, educada e executiva.
        Mantenha o sentido original, mas remova qualquer gíria, agressividade ou informalidade.
        
        Mensagem Original: "{raw_text}"
        
        Responda APENAS com a mensagem reescrita.
        """

        response = model.generate_content(prompt)
        return jsonify({'translated_text': response.text})

    except Exception as e:
        return jsonify({'error': f'Erro: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
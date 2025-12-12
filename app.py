import os
import io
import json
import re
import google.generativeai as genai
import stripe
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client

# --- FERRAMENTAS EXTRAS ---
from pytube import YouTube
import xml.etree.ElementTree as ET
from docx import Document
from docx.shared import Cm, Pt
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment
from pypdf import PdfReader 

# Carrega variáveis do .env
load_dotenv() 

app = Flask(__name__)
CORS(app) 

# --- VERIFICAÇÃO DE CHAVES ---
stripe_key = os.environ.get("STRIPE_SECRET_KEY")
stripe_price = os.environ.get("STRIPE_PRICE_ID")
frontend_url = os.environ.get("FRONTEND_URL")
endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

# Configurações
stripe.api_key = stripe_key

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if url and key:
    supabase: Client = create_client(url, key)
else:
    print("ERRO CRÍTICO: Chaves do Supabase faltando!")
    supabase = None

try:
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("Modelo Gemini configurado com sucesso!")
except Exception as e:
    print(f"Erro ao configurar o modelo Gemini: {e}")
    model = None

# --- FUNÇÃO DE CRÉDITOS ---
def check_and_deduct_credit(user_id):
    try:
        if not supabase: return False, "Erro de banco de dados."
        response = supabase.table('profiles').select('credits, is_pro').eq('id', user_id).execute()
        
        if not response.data: return False, "Usuário não encontrado."
        
        user_data = response.data[0]
        credits = user_data['credits']
        is_pro = user_data.get('is_pro', False) 
        
        if is_pro: return True, "Sucesso (VIP)"
            
        if credits <= 0: return False, "Sem créditos. Assine o PRO!"
            
        new_credits = credits - 1
        supabase.table('profiles').update({'credits': new_credits}).eq('id', user_id).execute()
        return True, "Sucesso"
    except Exception as e: return False, str(e)

# --- FUNÇÃO AUXILIAR: EMBEDDINGS ---
def get_embedding(text):
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
            title="Documento do Usuário"
        )
        return result['embedding']
    except Exception as e:
        print(f"Erro embedding: {e}")
        return None

# --- ROTAS DAS FERRAMENTAS ---

# 1. IMAGEM
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)
        
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        prompt = f"Crie prompt imagem: {data.get('idea')}"
        response = model.generate_content(prompt)
        return jsonify({'advanced_prompt': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 2. VEO 3 & SORA 2
@app.route('/generate-veo3-prompt', methods=['POST'])
def generate_video_prompt():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        target_model = data.get('model', 'Veo 3')
        scene = data.get('scene')
        style = data.get('style')
        camera = data.get('camera')
        lighting = data.get('lighting')
        audio = data.get('audio')

        base_instruction = "Crie um prompt OTIMIZADO PARA VÍDEO."
        if target_model == 'Sora 2':
            base_instruction += " Foco em física realista e detalhes visuais (Sora)."
        else:
            base_instruction += " Foco em termos cinematográficos e técnicos (Veo)."

        prompt = f"""
        {base_instruction}
        Cena: {scene}
        Estilo: {style}
        Câmera: {camera}
        Luz: {lighting}
        Som: {audio}
        Gere APENAS o prompt final em Inglês.
        """
        
        response = model.generate_content(prompt)
        return jsonify({'advanced_prompt': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 3. RESUMIDOR
@app.route('/summarize-video', methods=['POST'])
def summarize_video():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402

        yt = YouTube(data.get('url'))
        caption = yt.captions.get_by_language_code('pt')
        if not caption: caption = yt.captions.get_by_language_code('en')
        if not caption: caption = yt.captions.get_by_language_code('a.pt') 
        
        if not caption: return jsonify({'error': 'Sem legendas.'}), 400
        
        xml = caption.xml_captions
        root = ET.fromstring(xml)
        text = " ".join([elem.text for elem in root.iter('text') if elem.text])
        
        prompt = f"Resuma: {text[:30000]}"
        response = model.generate_content(prompt)
        return jsonify({'summary': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 4. ABNT
@app.route('/format-abnt', methods=['POST'])
def format_abnt():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        prompt = f"Formate ABNT Markdown: {data.get('text')}"
        response = model.generate_content(prompt)
        return jsonify({'formatted_text': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 4.1. RESUMIDOR DE TEXTOS LONGOS (Substitui o VideoSummarizer problemático)
@app.route('/summarize-text', methods=['POST'])
def summarize_text():
    if not model:
        return jsonify({'error': 'Modelo Gemini não disponível'}), 500
    
    try:
        data = request.get_json(force=True)
        if isinstance(data, str):
            data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            success, message = check_and_deduct_credit(user_id)
            if not success:
                return jsonify({'error': message}), 402

        text = data.get('text', '')
        if len(text) < 50:
            return jsonify({'error': 'Texto muito curto. Mínimo 50 caracteres.'}), 400
        
        # Limitar tamanho para não exceder tokens do Gemini
        text_limitado = text[:15000]  # 15k caracteres é seguro
        
        prompt = f"""
        Resuma o seguinte texto de forma clara e concisa.
        Mantenha os pontos principais e informações essenciais.
        Tamanho do resumo: Aproximadamente 20% do original.
        
        TEXTO PARA RESUMIR:
        {text_limitado}
        
        RESPOSTA: Apenas o resumo, sem introduções.
        """
        
        response = model.generate_content(prompt)
        return jsonify({'summary': response.text})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 5. DOWNLOAD DOCX
@app.route('/download-docx', methods=['POST'])
def download_docx():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        doc = Document()
        doc.add_paragraph(data.get('markdown_text'))
        f = io.BytesIO()
        doc.save(f)
        f.seek(0)
        return send_file(f, as_attachment=True, download_name='doc.docx', mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e: return jsonify({'error': str(e)}), 500

# 6. PLANILHAS (VERSÃO FLEXÍVEL E GARANTIDA)
@app.route('/generate-spreadsheet', methods=['POST'])
def generate_spreadsheet():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        # Prompt OTIMIZADO para sempre retornar algo útil
        prompt = f"""
        Você é um especialista em Excel. Crie o conteúdo de uma planilha para:
        "{data.get('description')}"

        IMPORTANTE: Responda EXATAMENTE neste formato de lista (Célula|Valor):
        
        A1|TÍTULO DA PLANILHA
        A3|Data
        B3|Descrição
        C3|Valor
        A4|01/01/2024
        B4|Exemplo de Item
        C4|100.00
        
        Gere pelo menos 5 linhas de dados de exemplo para a planilha não ficar vazia.
        Use títulos em CAIXA ALTA.
        """
        
        response = model.generate_content(prompt)
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Planilha Gerada"
        
        lines = response.text.strip().split('\n')
        data_found = False # Flag para saber se achamos dados
        
        for line in lines:
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 2:
                    cell = parts[0].strip()
                    value = "|".join(parts[1:]).strip()
                    
                    # Verifica se a célula é válida (Ex: A1, B2)
                    if re.match(r'^[A-Z]{1,3}[0-9]{1,6}$', cell):
                        data_found = True
                        try:
                            # Tenta converter números
                            if value.replace('.', '', 1).isdigit():
                                value = float(value)
                        except: pass
                        
                        try:
                            ws[cell] = value
                            if isinstance(value, str) and value.isupper() and len(value) > 2:
                                ws[cell].font = Font(bold=True)
                                ws[cell].fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
                        except: pass

        # SE A IA FALHOU E A PLANILHA ESTÁ VAZIA, CRIAMOS UMA DE EMERGÊNCIA
        if not data_found:
            ws['A1'] = "ERRO NA GERAÇÃO AUTOMÁTICA"
            ws['A2'] = "A IA não retornou dados no formato correto."
            ws['A3'] = "Descrição do seu pedido:"
            ws['B3'] = data.get('description')
            ws.column_dimensions['A'].width = 30
            ws.column_dimensions['B'].width = 50

        # Ajuste largura
        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 30
        ws.column_dimensions['C'].width = 15

        f = io.BytesIO()
        wb.save(f)
        f.seek(0)
        
        return send_file(f, as_attachment=True, download_name='planilha_ia.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        print(f"ERRO PLANILHA: {e}")
        return jsonify({'error': f"Erro ao gerar: {str(e)}"}), 500

# 7. UPLOAD PDF (RAG)
@app.route('/upload-document', methods=['POST'])
def upload_document():
    try:
        user_id = request.form.get('user_id')
        file = request.files.get('file')
        if not user_id or not file: return jsonify({'error': 'Dados faltando'}), 400
        
        s, m = check_and_deduct_credit(user_id)
        if not s: return jsonify({'error': m}), 402

        reader = PdfReader(file)
        text = ""
        for page in reader.pages: text += page.extract_text() + "\n"
        
        doc = supabase.table('documents').insert({'user_id': user_id, 'filename': file.filename}).execute()
        doc_id = doc.data[0]['id']

        chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
        items = []
        for c in chunks:
            emb = get_embedding(c)
            if emb: items.append({'document_id': doc_id, 'content': c, 'embedding': emb})
        
        if items: supabase.table('document_chunks').insert(items).execute()
        return jsonify({'message': 'OK', 'document_id': doc_id})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 8. CHAT PDF (RAG)
@app.route('/ask-document', methods=['POST'])
def ask_document():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        question = data.get('question')
        
        q_emb = get_embedding(question)
        params = {'query_embedding': q_emb, 'match_threshold': 0.5, 'match_count': 5, 'user_id_filter': user_id}
        matches = supabase.rpc('match_documents', params).execute().data
        
        context = "\n".join([m['content'] for m in matches])
        prompt = f"Contexto: {context}\nPergunta: {question}"
        resp = model.generate_content(prompt)
        
        return jsonify({'answer': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 9. TRADUTOR CORPORATIVO
@app.route('/corporate-translator', methods=['POST'])
def corporate_translator():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        prompt = f"Reescreva corporativamente: {data.get('text')}. Tom: {data.get('tone')}"
        resp = model.generate_content(prompt)
        return jsonify({'translated_text': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 10. SOCIAL MEDIA GENERATOR
@app.route('/generate-social-media', methods=['POST'])
def generate_social_media():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        text = data.get('text')
        prompt = f"""
        Crie 3 posts (Instagram, LinkedIn, Twitter) sobre: "{text}".
        SAÍDA JSON OBRIGATÓRIA: {{ "instagram": "...", "linkedin": "...", "twitter": "..." }}
        """
        response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.9))
        
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" in json_text: json_text = json_text[json_text.find("{"):json_text.rfind("}")+1]
        return jsonify(json.loads(json_text))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 11. CORRETOR DE REDAÇÃO
@app.route('/correct-essay', methods=['POST'])
def correct_essay():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        prompt = f"""
        Corrija a redação sobre "{data.get('theme')}". Texto: "{data.get('essay')}"
        SAÍDA JSON: {{ "total_score": 0, "competencies": {{...}}, "feedback": "..." }}
        """
        response = model.generate_content(prompt)
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" in json_text: json_text = json_text[json_text.find("{"):json_text.rfind("}")+1]
        return jsonify(json.loads(json_text))
    except Exception as e: return jsonify({'error': str(e)}), 500

# 12. SIMULADOR DE ENTREVISTA
@app.route('/mock-interview', methods=['POST'])
def mock_interview():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        prompt = f"""
        Simule entrevista para "{data.get('role')}". Descrição: "{data.get('description')}".
        SAÍDA JSON: {{ "questions": [{{ "q": "...", "a": "..." }}], "tips": ["..."] }}
        """
        response = model.generate_content(prompt)
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" in json_text: json_text = json_text[json_text.find("{"):json_text.rfind("}")+1]
        return jsonify(json.loads(json_text))
    except Exception as e: return jsonify({'error': str(e)}), 500

# 13. GERADOR DE QUIZ E FLASHCARDS
@app.route('/generate-study-material', methods=['POST'])
def generate_study_material():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        mode = data.get('mode')
        if mode == 'quiz':
            prompt = f"""
            Gere um Quiz sobre: "{data.get('text')[:15000]}".
            SAÍDA JSON: {{ "questions": [{{ "question": "...", "options": ["..."], "answer": "...", "explanation": "..." }}] }}
            """
        else:
            prompt = f"""
            Gere Flashcards sobre: "{data.get('text')[:15000]}".
            SAÍDA JSON: {{ "flashcards": [{{ "front": "...", "back": "..." }}] }}
            """
        
        response = model.generate_content(prompt)
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" in json_text: json_text = json_text[json_text.find("{"):json_text.rfind("}")+1]
        return jsonify(json.loads(json_text))
    except Exception as e: return jsonify({'error': str(e)}), 500

# 14. CARTA DE APRESENTAÇÃO
@app.route('/generate-cover-letter', methods=['POST'])
def generate_cover_letter():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        prompt = f"""
        Escreva uma Cover Letter para a vaga: "{data.get('job_desc')}" baseada no CV: "{data.get('cv_text')}". Tom: {data.get('tone')}.
        """
        response = model.generate_content(prompt)
        return jsonify({'cover_letter': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- PAGAMENTOS (STRIPE WEBHOOKS) ---
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)
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

@app.route('/create-portal-session', methods=['POST'])
def create_portal_session():
    try:
        user_id = request.json.get('user_id')
        resp = supabase.table('profiles').select('stripe_customer_id').eq('id', user_id).execute()
        if not resp.data or not resp.data[0]['stripe_customer_id']: return jsonify({'error': 'Sem assinatura.'}), 400
        
        session = stripe.billing_portal.Session.create(
            customer=resp.data[0]['stripe_customer_id'],
            return_url=f'{frontend_url}/',
        )
        return jsonify({'url': session.url})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    try: event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except: return 'Error', 400
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        uid = session.get('metadata', {}).get('user_id')
        if uid: supabase.table('profiles').update({'is_pro': True, 'stripe_customer_id': session.get('customer')}).eq('id', uid).execute()
    elif event['type'] == 'customer.subscription.deleted':
        sub = event['data']['object']
        cus_id = sub.get('customer')
        resp = supabase.table('profiles').select('id').eq('stripe_customer_id', cus_id).execute()
        if resp.data: supabase.table('profiles').update({'is_pro': False}).eq('id', resp.data[0]['id']).execute()
    return 'Success', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
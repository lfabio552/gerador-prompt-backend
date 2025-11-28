import os
import io
import json
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
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        prompt = f"Crie prompt imagem: {data.get('idea')}"
        response = model.generate_content(prompt)
        return jsonify({'advanced_prompt': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 2. VEO 3
@app.route('/generate-veo3-prompt', methods=['POST'])
def generate_veo3_prompt():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        prompt = f"Crie prompt video: {data.get('scene')}"
        response = model.generate_content(prompt)
        return jsonify({'advanced_prompt': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 3. RESUMIDOR
@app.route('/summarize-video', methods=['POST'])
def summarize_video():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    data = request.json
    if data.get('user_id'):
        s, m = check_and_deduct_credit(data.get('user_id'))
        if not s: return jsonify({'error': m}), 402

    try:
        yt = YouTube(data.get('url'))
        caption = yt.captions.get_by_language_code('pt')
        if not caption: caption = yt.captions.get_by_language_code('en')
        if not caption: caption = yt.captions.get_by_language_code('a.pt') # Auto
        
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
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        prompt = f"Formate ABNT Markdown: {data.get('text')}"
        response = model.generate_content(prompt)
        return jsonify({'formatted_text': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 5. DOWNLOAD DOCX
@app.route('/download-docx', methods=['POST'])
def download_docx():
    try:
        doc = Document()
        doc.add_paragraph(request.json.get('markdown_text'))
        f = io.BytesIO()
        doc.save(f)
        f.seek(0)
        return send_file(f, as_attachment=True, download_name='doc.docx', mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e: return jsonify({'error': str(e)}), 500

# 6. PLANILHAS
@app.route('/generate-spreadsheet', methods=['POST'])
def generate_spreadsheet():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        prompt = f"Gere JSON planilha: {data.get('description')}. APENAS JSON."
        resp = model.generate_content(prompt)
        txt = resp.text.replace("```json", "").replace("```", "").strip()
        if "{" in txt: txt = txt[txt.find("{"):txt.rfind("}")+1]
        
        wb = Workbook(); ws = wb.active
        for k,v in json.loads(txt).items():
            ws[k] = v.get('value')
        
        f = io.BytesIO(); wb.save(f); f.seek(0)
        return send_file(f, as_attachment=True, download_name='sheet.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e: return jsonify({'error': str(e)}), 500

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
        data = request.json
        user_id = data.get('user_id')
        question = data.get('question')
        
        # Busca vetorial
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
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        prompt = f"Reescreva corporativamente: {data.get('text')}. Tom: {data.get('tone')}"
        resp = model.generate_content(prompt)
        return jsonify({'translated_text': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 10. SOCIAL MEDIA GENERATOR (VERSÃO TURBO 2.0)
@app.route('/generate-social-media', methods=['POST'])
def generate_social_media():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        text = data.get('text')
        
        prompt = f"""
        Você é um Gerente de Social Media Expert. Crie 3 posts distintos baseados neste texto: "{text}".
        
        1. INSTAGRAM: Use linguagem visual, emojis, hashtags populares, tom engajador e "chamada para ação".
        2. LINKEDIN: Tom profissional, focado em negócios, lições de carreira ou inovação, sem gírias.
        3. TWITTER/X: Curto, direto (max 280 chars), impactante, talvez uma opinião forte ou "thread starter".

        SAÍDA OBRIGATÓRIA EM JSON (SEM MARKDOWN):
        {{ 
            "instagram": "texto do post...", 
            "linkedin": "texto do post...", 
            "twitter": "texto do post..." 
        }}
        """
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.9)
        )
        
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" in json_text:
            start = json_text.find("{")
            end = json_text.rfind("}") + 1
            json_text = json_text[start:end]

        return jsonify(json.loads(json_text))
    except Exception as e:
        print(f"ERRO SOCIAL: {e}")
        return jsonify({'error': str(e)}), 500

# 11. CORRETOR DE REDAÇÃO (ENEM)
@app.route('/correct-essay', methods=['POST'])
def correct_essay():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        theme = data.get('theme')
        essay = data.get('essay')
        
        prompt = f"""
        Aja como um Corretor Oficial do ENEM. Avalie a seguinte redação com base no tema: "{theme}".
        Texto: "{essay}"
        
        SAÍDA OBRIGATÓRIA EM JSON (SEM MARKDOWN):
        {{
            "total_score": 000,
            "competencies": {{ "1": "...", "2": "...", "3": "...", "4": "...", "5": "..." }},
            "feedback": "..."
        }}
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
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        role = data.get('role')
        description = data.get('description')
        
        prompt = f"""
        Aja como um Recrutador Sênior (Headhunter). Eu vou fazer uma entrevista para a vaga: "{role}".
        Descrição da vaga: "{description}".

        Gere um guia de preparação em JSON contendo:
        1. "tough_questions": 5 perguntas difíceis e específicas que você faria.
        2. "ideal_answers": Para cada pergunta, a resposta ideal (star method).
        3. "tips": 3 dicas do que NÃO falar.

        SAÍDA OBRIGATÓRIA EM JSON (SEM MARKDOWN):
        {{
            "questions": [
                {{ "q": "Pergunta 1...", "a": "Resposta ideal..." }},
                {{ "q": "Pergunta 2...", "a": "Resposta ideal..." }},
                ...
            ],
            "tips": ["Dica 1", "Dica 2", "Dica 3"]
        }}
        """
        
        response = model.generate_content(prompt)
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" in json_text: json_text = json_text[json_text.find("{"):json_text.rfind("}")+1]

        return jsonify(json.loads(json_text))
    except Exception as e: return jsonify({'error': str(e)}), 500

# 13. GERADOR DE QUIZ E FLASHCARDS (NOVO)
@app.route('/generate-study-material', methods=['POST'])
def generate_study_material():
    if not model: return jsonify({'error': 'Erro modelo'}), 500
    try:
        data = request.json
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        text = data.get('text')
        mode = data.get('mode') # 'quiz' ou 'flashcards'
        
        if mode == 'quiz':
            prompt = f"""
            Com base no texto abaixo, crie um Quiz de 5 perguntas de múltipla escolha.
            Texto: "{text[:15000]}"

            SAÍDA APENAS JSON:
            {{
                "questions": [
                    {{
                        "question": "Pergunta...",
                        "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
                        "answer": "Letra correta (ex: A)",
                        "explanation": "Por que está correta..."
                    }}
                ]
            }}
            """
        else: # Flashcards
            prompt = f"""
            Com base no texto abaixo, crie 5 Flashcards (Frente e Verso) para memorização.
            Texto: "{text[:15000]}"

            SAÍDA APENAS JSON:
            {{
                "flashcards": [
                    {{ "front": "Conceito ou Pergunta", "back": "Definição ou Resposta" }},
                    ...
                ]
            }}
            """
        
        response = model.generate_content(prompt)
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" in json_text: json_text = json_text[json_text.find("{"):json_text.rfind("}")+1]

        return jsonify(json.loads(json_text))
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- PAGAMENTOS (STRIPE WEBHOOKS) ---
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
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

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        return 'Invalid signature', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        uid = session.get('metadata', {}).get('user_id')
        if uid:
            supabase.table('profiles').update({
                'is_pro': True, 
                'stripe_customer_id': session.get('customer')
            }).eq('id', uid).execute()
    
    elif event['type'] == 'customer.subscription.deleted':
        sub = event['data']['object']
        cus_id = sub.get('customer')
        resp = supabase.table('profiles').select('id').eq('stripe_customer_id', cus_id).execute()
        if resp.data:
            supabase.table('profiles').update({'is_pro': False}).eq('id', resp.data[0]['id']).execute()

    return 'Success', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
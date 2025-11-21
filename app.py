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

load_dotenv() 
app = Flask(__name__)
CORS(app) 

# --- CONFIGURAÇÕES ---
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
frontend_url = os.environ.get("FRONTEND_URL")
# IMPORTANTE: O Segredo do Webhook (vamos pegar no painel do Stripe depois)
endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

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

# --- FUNÇÃO DE CRÉDITOS ---
def check_and_deduct_credit(user_id):
    try:
        response = supabase.table('profiles').select('credits, is_pro').eq('id', user_id).execute()
        if not response.data: return False, "Usuário não encontrado."
        user_data = response.data[0]
        if user_data.get('is_pro'): return True, "Sucesso (VIP)"
        if user_data['credits'] <= 0: return False, "Sem créditos. Assine o PRO!"
        
        supabase.table('profiles').update({'credits': user_data['credits'] - 1}).eq('id', user_id).execute()
        return True, "Sucesso"
    except Exception as e: return False, str(e)

# --- ROTAS DAS FERRAMENTAS (Resumidas para caber aqui, mantenha a lógica!) ---
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    # ... (Lógica igual a anterior) ...
    if not model: return jsonify({'error': 'Erro'}), 500
    try:
        data = request.json
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402
        response = model.generate_content(f"Crie prompt imagem: {data.get('idea')}")
        return jsonify({'advanced_prompt': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/generate-veo3-prompt', methods=['POST'])
def generate_veo3_prompt():
    if not model: return jsonify({'error': 'Erro'}), 500
    try:
        data = request.json
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402
        response = model.generate_content(f"Crie prompt video VEO: {data.get('scene')}")
        return jsonify({'advanced_prompt': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/summarize-video', methods=['POST'])
def summarize_video():
    if not model: return jsonify({'error': 'Erro'}), 500
    data = request.json
    if data.get('user_id'):
        s, m = check_and_deduct_credit(data.get('user_id'))
        if not s: return jsonify({'error': m}), 402
    try:
        yt = YouTube(data.get('url'))
        caption = yt.captions.get_by_language_code('pt')
        if not caption: caption = yt.captions.get_by_language_code('en')
        if not caption: caption = yt.captions.get_by_language_code('a.pt')
        if not caption: caption = yt.captions.get_by_language_code('a.en')
        if not caption: return jsonify({'error': 'Sem legendas.'}), 400
        xml = caption.xml_captions
        root = ET.fromstring(xml)
        text = " ".join([elem.text for elem in root.iter('text') if elem.text])
        response = model.generate_content(f"Resuma este video: {text[:30000]}")
        return jsonify({'summary': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/format-abnt', methods=['POST'])
def format_abnt():
    if not model: return jsonify({'error': 'Erro'}), 500
    try:
        data = request.json
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402
        response = model.generate_content(f"Formate ABNT: {data.get('text')}")
        return jsonify({'formatted_text': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

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

@app.route('/generate-spreadsheet', methods=['POST'])
def generate_spreadsheet():
    if not model: return jsonify({'error': 'Erro'}), 500
    try:
        data = request.json
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402
        
        resp = model.generate_content(f"Gere JSON planilha para: {data.get('description')}. Responda APENAS JSON.")
        txt = resp.text.replace("```json", "").replace("```", "").strip()
        if "{" in txt: txt = txt[txt.find("{"):txt.rfind("}")+1]
        
        wb = Workbook(); ws = wb.active
        for k,v in json.loads(txt).items():
            ws[k] = v.get('value')
        
        f = io.BytesIO()
        wb.save(f)
        f.seek(0)
        return send_file(f, as_attachment=True, download_name='sheet.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e: return jsonify({'error': str(e)}), 500

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

# --- ROTA 8: O WEBHOOK (O Ouvido do Stripe) ---
@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        # Verifica se o aviso veio mesmo do Stripe
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        return 'Invalid signature', 400

    # Se o pagamento foi completado com sucesso
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Pega o ID do usuário que guardamos no metadata
        user_id = session.get('metadata', {}).get('user_id')

        if user_id:
            print(f"💰 Pagamento recebido para: {user_id}")
            # Atualiza o usuário para PRO no Supabase
            supabase.table('profiles').update({
                'is_pro': True,
                'stripe_customer_id': session.get('customer')
            }).eq('id', user_id).execute()

    return 'Success', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
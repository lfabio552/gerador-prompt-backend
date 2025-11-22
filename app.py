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

# Carrega variáveis do .env (apenas localmente)
load_dotenv() 

app = Flask(__name__)
CORS(app) 

# --- VERIFICAÇÃO DE CHAVES (DEBUG NO LOG) ---
print("--- INICIANDO VERIFICAÇÃO DE CHAVES ---")
stripe_key = os.environ.get("STRIPE_SECRET_KEY")
if not stripe_key:
    print("ERRO CRÍTICO: STRIPE_SECRET_KEY não encontrada!")
else:
    print(f"STRIPE_SECRET_KEY encontrada: {stripe_key[:5]}...")

stripe_price = os.environ.get("STRIPE_PRICE_ID")
if not stripe_price:
    print("ERRO CRÍTICO: STRIPE_PRICE_ID não encontrada!")

frontend_url = os.environ.get("FRONTEND_URL")
if not frontend_url:
    print("ERRO CRÍTICO: FRONTEND_URL não encontrada!")

print("---------------------------------------")

# --- CONFIGURAÇÕES GERAIS ---
stripe.api_key = stripe_key
endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

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

# --- FUNÇÃO DE CONTROLE DE CRÉDITOS ---
def check_and_deduct_credit(user_id):
    try:
        if not supabase: return False, "Erro de configuração no Banco de Dados."
        
        response = supabase.table('profiles').select('credits, is_pro').eq('id', user_id).execute()
        
        if not response.data: return False, "Usuário não encontrado."
            
        user_data = response.data[0]
        credits = user_data['credits']
        is_pro = user_data.get('is_pro', False) 
        
        if is_pro:
            print(f"Usuário {user_id} é PRO. Acesso liberado.")
            return True, "Sucesso (VIP)"
            
        if credits <= 0:
            return False, "Você não tem créditos suficientes. Assine o plano PRO!"
            
        new_credits = credits - 1
        supabase.table('profiles').update({'credits': new_credits}).eq('id', user_id).execute()
        
        return True, "Sucesso"
    except Exception as e:
        return False, str(e)

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
        # Verifica se a chave carregou
        if not stripe.api_key:
            print("ERRO: stripe.api_key está vazia!")
            return jsonify({'error': 'Erro de configuração no servidor (Stripe Key Missing)'}), 500

        data = request.json
        user_id = data.get('user_id')
        user_email = data.get('email')

        if not user_id: return jsonify({'error': 'Usuário não identificado.'}), 400

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': os.environ.get('STRIPE_PRICE_ID'),
                'quantity': 1,
            }],
            mode='subscription', 
            success_url=f'{frontend_url}/?success=true',
            cancel_url=f'{frontend_url}/?canceled=true',
            metadata={'user_id': user_id},
            customer_email=user_email
        )
        return jsonify({'url': checkout_session.url})
    except Exception as e:
        print(f"ERRO STRIPE: {e}")
        return jsonify({'error': str(e)}), 500

# --- ROTA 8: WEBHOOK ---
@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e: return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e: return 'Invalid signature', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session.get('metadata', {}).get('user_id')

        if user_id:
            print(f"💰 Pagamento recebido para: {user_id}")
            supabase.table('profiles').update({
                'is_pro': True,
                'stripe_customer_id': session.get('customer')
            }).eq('id', user_id).execute()

    return 'Success', 200

# --- ROTA 9: PORTAL DO CLIENTE (GERENCIAR ASSINATURA) ---
@app.route('/create-portal-session', methods=['POST'])
def create_portal_session():
    try:
        data = request.json
        user_id = data.get('user_id')

        if not user_id: return jsonify({'error': 'Usuário não identificado.'}), 400

        # 1. Buscar o ID do Cliente no Stripe (que salvamos no Webhook)
        response = supabase.table('profiles').select('stripe_customer_id').eq('id', user_id).execute()
        
        if not response.data or not response.data[0]['stripe_customer_id']:
            return jsonify({'error': 'Você ainda não tem uma assinatura ativa para gerenciar.'}), 400
            
        customer_id = response.data[0]['stripe_customer_id']

        # 2. Pedir ao Stripe o link do portal
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f'{frontend_url}/', # Para onde ele volta depois de gerenciar
        )

        return jsonify({'url': portal_session.url})

    except Exception as e:
        print(f"ERRO PORTAL: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
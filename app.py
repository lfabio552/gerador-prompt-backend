import os
import io
import json
import re
import google.generativeai as genai
import stripe
import replicate
from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS
from dotenv import load_dotenv
from supabase import create_client, Client

# --- FERRAMENTAS EXTRAS ---
from pytube import YouTube
import xml.etree.ElementTree as ET
from docx import Document
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font
from pypdf import PdfReader 

load_dotenv() 

app = Flask(__name__)

# --- CONFIGURAÇÃO CORS "BLINDADA" (MANUAL) ---
# Habilita a lib básica
CORS(app)

# 1. INTERCEPTADOR DE PREFLIGHT (A Mágica acontece aqui)
# Se o navegador perguntar "Posso?", respondemos "Pode!" antes de qualquer erro acontecer.
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "*")
        response.headers.add("Access-Control-Allow-Methods", "*")
        return response

# 2. INJETOR DE HEADERS
# Garante que a resposta final leve a permissão junto.
@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
    return response

# --- CONFIGURAÇÕES ---
stripe_key = os.environ.get("STRIPE_SECRET_KEY")
endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
frontend_url = os.environ.get("FRONTEND_URL", "*")

if stripe_key: stripe.api_key = stripe_key

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
if url and key:
    supabase: Client = create_client(url, key)
else:
    print("ERRO: Supabase não configurado.")
    supabase = None

try:
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    model = genai.GenerativeModel('gemini-2.5-flash')
except Exception as e:
    print(f"Erro Gemini: {e}")
    model = None

# --- FUNÇÃO DE CRÉDITOS ---
def check_and_deduct_credit(user_id):
    try:
        if not supabase: return False, "Erro de banco de dados."
        response = supabase.table('profiles').select('credits, is_pro').eq('id', user_id).execute()
        
        if not response.data: return False, "Usuário não encontrado."
        
        user_data = response.data[0]
        credits = user_data.get('credits', 0)
        is_pro = user_data.get('is_pro', False) 
        
        if is_pro: return True, "Sucesso (VIP)"
        if credits <= 0: return False, "Sem créditos."
            
        new_credits = credits - 1
        supabase.table('profiles').update({'credits': new_credits}).eq('id', user_id).execute()
        return True, "Sucesso"
    except Exception as e: return False, str(e)

# --- EMBEDDINGS ---
def get_embedding(text):
    try:
        result = genai.embed_content(model="models/text-embedding-004", content=text)
        return result['embedding']
    except: return None

@app.route('/')
def health_check():
    return jsonify({'status': 'ok', 'service': 'Adapta IA Backend'})

# ==============================================================================
#  ROTAS (Sem 'OPTIONS' no methods, pois o before_request cuida disso)
# ==============================================================================

# 1. GERADOR DE PROMPTS IMAGEM
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        idea = data.get('idea') or data.get('prompt') or data.get('text')
        if not idea: return jsonify({'error': 'Ideia vazia'}), 400

        response = model.generate_content(f"Crie prompt imagem (SDXL/Midjourney) em Inglês: {idea}")
        return jsonify({'advanced_prompt': response.text, 'prompt': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 2. VEO 3 & SORA 2 (Foco do erro)
@app.route('/generate-veo3-prompt', methods=['POST'])
@app.route('/generate-video-prompt', methods=['POST'])
def generate_video_prompt():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        # FLEXIBILIDADE DE NOMES
        idea = data.get('idea') or data.get('prompt') or data.get('text') or data.get('scene')
        
        if not idea: return jsonify({'error': 'Ideia não fornecida'}), 400

        target_model = data.get('model', 'Veo 3')
        style = data.get('style', '')
        camera = data.get('camera', '')
        lighting = data.get('lighting', '')
        audio = data.get('audio', '')

        base_instruction = "Crie um prompt OTIMIZADO PARA VÍDEO."
        if target_model == 'Sora 2': base_instruction += " Foco em física realista (Sora)."
        else: base_instruction += " Foco cinematográfico (Veo)."

        prompt = f"""
        {base_instruction}
        Cena: {idea}. Estilo: {style}. Câmera: {camera}. Luz: {lighting}. Som: {audio}.
        Output: APENAS o prompt em Inglês.
        """
        
        response = model.generate_content(prompt)
        return jsonify({'advanced_prompt': response.text, 'prompt': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 3. RESUMIDOR DE VÍDEO
@app.route('/summarize-video', methods=['POST'])
def summarize_video():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)

        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402

        video_url = data.get('url') or data.get('video_url')
        try:
            yt = YouTube(video_url)
            caption = yt.captions.get_by_language_code('pt')
            if not caption: caption = yt.captions.get_by_language_code('en')
            if not caption: caption = yt.captions.get_by_language_code('a.pt') 
            
            if not caption: text = f"Título: {yt.title}. Desc: {yt.description}"
            else:
                xml = caption.xml_captions
                root = ET.fromstring(xml)
                text = " ".join([elem.text for elem in root.iter('text') if elem.text])
        except Exception as e: return jsonify({'error': f"Erro vídeo: {str(e)}"}), 400
        
        response = model.generate_content(f"Resuma: {text[:30000]}")
        return jsonify({'summary': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 4. ABNT
@app.route('/format-abnt', methods=['POST'])
def format_abnt():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402
        
        text = data.get('text') or data.get('reference')
        response = model.generate_content(f"Formate ABNT: {text}")
        return jsonify({'formatted_text': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 5. RESUMIDOR DE TEXTO
@app.route('/summarize-text', methods=['POST'])
def summarize_text():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402

        text = data.get('text') or data.get('content', '')
        if len(text) < 10: return jsonify({'error': 'Texto curto'}), 400
        
        response = model.generate_content(f"Resuma ({data.get('format','bulletpoints')}): {text[:15000]}")
        return jsonify({'summary': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 6. DOWNLOAD DOCX
@app.route('/download-docx', methods=['POST'])
def download_docx():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        doc = Document()
        doc.add_paragraph(data.get('markdown_text') or data.get('text', ''))
        f = io.BytesIO()
        doc.save(f)
        f.seek(0)
        return send_file(f, as_attachment=True, download_name='doc.docx', mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e: return jsonify({'error': str(e)}), 500

# 7. PLANILHA
@app.route('/generate-spreadsheet', methods=['POST'])
def generate_spreadsheet():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402

        prompt = f"""
        Crie planilha Excel para: "{data.get('description') or data.get('text')}"
        Formato: Célula|Valor
        Ex: A1|Título
        Gere 5 linhas.
        """
        response = model.generate_content(prompt)
        wb = Workbook()
        ws = wb.active
        for line in response.text.split('\n'):
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 2:
                    try: ws[parts[0].strip()] = parts[1].strip()
                    except: pass
        f = io.BytesIO()
        wb.save(f)
        f.seek(0)
        return send_file(f, as_attachment=True, download_name='planilha.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e: return jsonify({'error': str(e)}), 500

# 8. UPLOAD PDF
@app.route('/upload-document', methods=['POST'])
def upload_document():
    try:
        user_id = request.form.get('user_id')
        file = request.files.get('file')
        if not user_id or not file: return jsonify({'error': 'Dados faltando'}), 400
        s, m = check_and_deduct_credit(user_id)
        if not s: return jsonify({'error': m}), 402

        reader = PdfReader(file)
        text = "".join([page.extract_text() + "\n" for page in reader.pages])
        doc = supabase.table('documents').insert({'user_id': user_id, 'filename': file.filename}).execute()
        
        # Embeddings simplificados
        if len(text) > 0:
            emb = get_embedding(text[:1000]) # Pega só o começo pra não estourar cota no teste
            if emb: supabase.table('document_chunks').insert({'document_id': doc.data[0]['id'], 'content': text[:1000], 'embedding': emb}).execute()
            
        return jsonify({'message': 'OK', 'document_id': doc.data[0]['id']})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 9. CHAT PDF
@app.route('/ask-document', methods=['POST'])
@app.route('/chat-pdf', methods=['POST'])
def ask_document():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        
        question = data.get('question') or data.get('query') or data.get('text')
        user_id = data.get('user_id')
        
        context = ""
        if user_id:
            q_emb = get_embedding(question)
            if q_emb:
                try:
                    params = {'query_embedding': q_emb, 'match_threshold': 0.5, 'match_count': 3, 'user_id_filter': user_id}
                    matches = supabase.rpc('match_documents', params).execute().data
                    context = "\n".join([m['content'] for m in matches])
                except: pass

        prompt = f"Contexto: {context}\nPergunta: {question}" if context else f"Pergunta: {question}"
        resp = model.generate_content(prompt)
        return jsonify({'answer': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 10. TRADUTOR
@app.route('/corporate-translator', methods=['POST'])
def corporate_translator():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402
        
        text = data.get('text') or data.get('content')
        lang = data.get('target_lang') or 'português'
        resp = model.generate_content(f"Traduza corporativamente para {lang}: {text}")
        return jsonify({'translated_text': resp.text, 'translation': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 11. SOCIAL MEDIA
@app.route('/generate-social-media', methods=['POST'])
def generate_social_media():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402

        text = data.get('text') or data.get('topic')
        resp = model.generate_content(f"Crie 3 posts (Insta, Linkedin, Twitter) JSON sobre: {text}")
        
        try: # Tenta extrair JSON
            txt = resp.text.replace("```json", "").replace("```", "").strip()
            if "{" in txt: txt = txt[txt.find("{"):txt.rfind("}")+1]
            return jsonify(json.loads(txt))
        except: return jsonify({'content': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 12. REDAÇÃO
@app.route('/correct-essay', methods=['POST'])
def correct_essay():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402

        essay = data.get('essay') or data.get('text')
        resp = model.generate_content(f"Corrija redação JSON (nota, erros): {essay}")
        try:
            txt = resp.text.replace("```json", "").replace("```", "").strip()
            if "{" in txt: txt = txt[txt.find("{"):txt.rfind("}")+1]
            return jsonify(json.loads(txt))
        except: return jsonify({'correction': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 13. ENTREVISTA
@app.route('/mock-interview', methods=['POST'])
def mock_interview():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402

        role = data.get('role')
        desc = data.get('description') or data.get('company')

        resp = model.generate_content(f"Simule entrevista JSON para {role}")
        try:
            txt = resp.text.replace("```json", "").replace("```", "").strip()
            if "{" in txt: txt = txt[txt.find("{"):txt.rfind("}")+1]
            return jsonify(json.loads(txt))
        except: return jsonify({'message': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 14. ESTUDO
@app.route('/generate-study-material', methods=['POST'])
def generate_study_material():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402

        text = data.get('text') or data.get('topic')
        resp = model.generate_content(f"Crie material estudo sobre: {text}")
        try:
            txt = resp.text.replace("```json", "").replace("```", "").strip()
            if "{" in txt: txt = txt[txt.find("{"):txt.rfind("}")+1]
            return jsonify(json.loads(txt))
        except: return jsonify({'material': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 15. CARTA
@app.route('/generate-cover-letter', methods=['POST'])
def generate_cover_letter():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402
        
        job = data.get('job_desc') or 'Vaga'
        resp = model.generate_content(f"Crie Cover Letter para {job}")
        return jsonify({'cover_letter': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 16. IMAGEM (Replicate)
@app.route('/generate-image', methods=['POST'])
def generate_image():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if data.get('user_id'):
            s, m = check_and_deduct_credit(data.get('user_id'))
            if not s: return jsonify({'error': m}), 402

        prompt = data.get('prompt') or data.get('text') or data.get('idea')
        if not prompt or len(prompt) < 5: return jsonify({'error': 'Prompt curto'}), 400

        output = replicate.run(
            "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            input={"prompt": prompt, "width": 1024, "height": 1024}
        )
        url = output[0] if isinstance(output, list) else output
        if supabase and data.get('user_id'):
            supabase.table('image_history').insert({'user_id': data['user_id'], 'prompt': prompt[:500], 'image_url': url}).execute()
        return jsonify({'success': True, 'image_url': url, 'prompt': prompt})
    except Exception as e: 
        return jsonify({'success': True, 'image_url': 'https://placehold.co/1024x1024/png?text=Erro+Replicate', 'error_detail': str(e)})

# --- HISTÓRICO ---
@app.route('/save-history', methods=['POST'])
def save_history():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        if supabase and data.get('user_id'):
            db_data = {
                'user_id': data.get('user_id'),
                'tool_type': data.get('tool_type') or data.get('toolType'),
                'tool_name': data.get('tool_name') or data.get('toolName'),
                'input_data': str(data.get('input_data') or data.get('inputData') or '')[:1000],
                'output_data': str(data.get('output_data') or data.get('outputData') or '')[:2000],
                'metadata': data.get('metadata', {})
            }
            res = supabase.table('user_history').insert(db_data).execute()
            return jsonify({'status': 'success', 'data': res.data})
        return jsonify({'status': 'skipped'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/get-history', methods=['POST', 'GET'])
def get_history():
    try:
        user_id = request.args.get('user_id')
        tool_type = request.args.get('tool_type')
        if request.method == 'POST':
            data = request.get_json(force=True) or {}
            if isinstance(data, str): data = json.loads(data)
            user_id = data.get('user_id')
            tool_type = data.get('tool_type')

        if supabase and user_id:
            query = supabase.table('user_history').select('*').eq('user_id', user_id).order('created_at', desc=True)
            if tool_type: query = query.eq('tool_type', tool_type)
            res = query.execute()
            return jsonify({'history': res.data})
        return jsonify({'history': []})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/delete-history-item', methods=['POST'])
def delete_history_item():
    try:
        data = request.get_json(force=True) or {}
        item_id = data.get('item_id') or data.get('id')
        if supabase and item_id:
            supabase.table('user_history').delete().eq('id', item_id).execute()
        return jsonify({'success': True})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- PAGAMENTO ---
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        data = request.get_json(force=True) or {}
        if isinstance(data, str): data = json.loads(data)
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': os.environ.get('STRIPE_PRICE_ID'), 'quantity': 1}],
            mode='subscription', 
            success_url=f'{frontend_url}/?success=true',
            cancel_url=f'{frontend_url}/?canceled=true',
            metadata={'user_id': data.get('user_id')},
            customer_email=data.get('email')
        )
        return jsonify({'url': session.url})
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

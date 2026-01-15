import os
import io
import json
import re
import google.generativeai as genai
import stripe
import replicate
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

load_dotenv() 

app = Flask(__name__)

# --- CONFIGURAÇÃO CORS DEFINITIVA ---
# Isso habilita o CORS para todas as rotas e origens automaticamente.
# Não precisamos de headers manuais nem tratamentos de OPTIONS nas rotas.
CORS(app)

# --- VERIFICAÇÃO DE CHAVES ---
stripe_key = os.environ.get("STRIPE_SECRET_KEY")
endpoint_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")

if stripe_key:
    stripe.api_key = stripe_key

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
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
            title="Documento"
        )
        return result['embedding']
    except: return None

@app.route('/')
def health_check():
    return jsonify({'status': 'ok', 'service': 'Adapta IA Backend'})

# ==============================================================================
#  ROTAS (Sem headers manuais, sem tratamentos de OPTIONS)
# ==============================================================================

# 1. GERADOR DE PROMPTS IMAGEM
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)
        
        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        idea = data.get('idea') or data.get('prompt') or data.get('text')
        
        prompt_ia = f"Crie um prompt detalhado em INGLÊS para gerar uma imagem no Midjourney/SDXL baseada nesta ideia: '{idea}'"
        response = model.generate_content(prompt_ia)
        return jsonify({'advanced_prompt': response.text, 'prompt': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 2. VEO 3 & SORA 2 (Prompts de Vídeo)
@app.route('/generate-veo3-prompt', methods=['POST'])
@app.route('/generate-video-prompt', methods=['POST'])
def generate_video_prompt():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        idea = data.get('idea') or data.get('prompt') or data.get('text') or data.get('scene')
        target_model = data.get('model', 'Veo 3')
        
        # Parâmetros opcionais (strings vazias se não existirem)
        style = data.get('style', '')
        camera = data.get('camera', '')
        lighting = data.get('lighting', '')
        audio = data.get('audio', '')

        base_instruction = "Crie um prompt OTIMIZADO PARA VÍDEO."
        if target_model == 'Sora 2':
            base_instruction += " Foco em física realista e detalhes visuais (Sora)."
        else:
            base_instruction += " Foco em termos cinematográficos e técnicos (Veo)."

        prompt = f"""
        {base_instruction}
        Cena Principal: {idea}
        Estilo: {style}
        Câmera: {camera}
        Luz: {lighting}
        Som: {audio}
        Gere APENAS o prompt final em Inglês.
        """
        
        response = model.generate_content(prompt)
        return jsonify({'advanced_prompt': response.text, 'prompt': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 3. RESUMIDOR DE VÍDEO
@app.route('/summarize-video', methods=['POST'])
def summarize_video():
    try:
        data = request.get_json(force=True)
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
            
            if not caption: 
                text = f"Título: {yt.title}. Descrição: {yt.description}"
            else:
                xml = caption.xml_captions
                root = ET.fromstring(xml)
                text = " ".join([elem.text for elem in root.iter('text') if elem.text])
        except Exception as e:
            return jsonify({'error': f"Erro no vídeo: {str(e)}"}), 400
        
        prompt = f"Resuma o seguinte conteúdo de vídeo: {text[:30000]}"
        response = model.generate_content(prompt)
        return jsonify({'summary': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 4. ABNT
@app.route('/format-abnt', methods=['POST'])
def format_abnt():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        text = data.get('text') or data.get('reference')
        prompt = f"Formate nas normas da ABNT: {text}"
        response = model.generate_content(prompt)
        return jsonify({'formatted_text': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 5. RESUMIDOR DE TEXTOS
@app.route('/summarize-text', methods=['POST'])
def summarize_text():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        text = data.get('text') or data.get('content', '')
        format_type = data.get('format', 'bulletpoints')

        if len(text) < 10: return jsonify({'error': 'Texto muito curto.'}), 400
        
        prompt = f"Resuma o texto no formato {format_type}: {text[:15000]}"
        response = model.generate_content(prompt)
        return jsonify({'summary': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 6. DOWNLOAD DOCX
@app.route('/download-docx', methods=['POST'])
def download_docx():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        doc = Document()
        content = data.get('markdown_text') or data.get('text', '')
        doc.add_paragraph(content)
        
        f = io.BytesIO()
        doc.save(f)
        f.seek(0)
        return send_file(f, as_attachment=True, download_name='documento.docx', mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e: return jsonify({'error': str(e)}), 500

# 7. PLANILHAS
@app.route('/generate-spreadsheet', methods=['POST'])
def generate_spreadsheet():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        desc = data.get('description') or data.get('text')

        prompt = f"""
        Você é um especialista em Excel. Crie uma planilha para: "{desc}"
        Responda EXATAMENTE neste formato (Célula|Valor):
        A1|TÍTULO
        A2|Data
        B2|Valor
        A3|01/01/2024
        B3|100
        Gere pelo menos 5 linhas de dados.
        """
        response = model.generate_content(prompt)
        
        wb = Workbook()
        ws = wb.active
        
        lines = response.text.strip().split('\n')
        for line in lines:
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

# 9. CHAT PDF
@app.route('/ask-document', methods=['POST'])
@app.route('/chat-pdf', methods=['POST'])
def ask_document():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)
        
        question = data.get('question') or data.get('query') or data.get('text')
        user_id = data.get('user_id')
        
        # Tenta RAG simples se tiver user_id
        context = ""
        if user_id:
            q_emb = get_embedding(question)
            if q_emb:
                try:
                    params = {'query_embedding': q_emb, 'match_threshold': 0.5, 'match_count': 5, 'user_id_filter': user_id}
                    matches = supabase.rpc('match_documents', params).execute().data
                    context = "\n".join([m['content'] for m in matches])
                except: pass

        prompt = f"Contexto: {context}\n\nPergunta: {question}" if context else f"Responda: {question}"
        resp = model.generate_content(prompt)
        return jsonify({'answer': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 10. TRADUTOR
@app.route('/corporate-translator', methods=['POST'])
def corporate_translator():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        text = data.get('text') or data.get('content')
        tone = data.get('tone', 'formal')
        target_lang = data.get('target_lang') or data.get('language') or 'português'
        
        prompt = f"Reescreva corporativamente em {target_lang} (Tom {tone}): {text}"
        resp = model.generate_content(prompt)
        return jsonify({'translated_text': resp.text, 'translation': resp.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 11. SOCIAL MEDIA
@app.route('/generate-social-media', methods=['POST'])
def generate_social_media():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        text = data.get('text') or data.get('topic')
        
        prompt = f"""
        Crie 3 posts (Instagram, LinkedIn, Twitter) sobre: "{text}".
        SAÍDA JSON: {{ "instagram": "...", "linkedin": "...", "twitter": "..." }}
        """
        response = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.9))
        
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" in json_text: json_text = json_text[json_text.find("{"):json_text.rfind("}")+1]
        
        try: return jsonify(json.loads(json_text))
        except: return jsonify({'content': response.text})

    except Exception as e: return jsonify({'error': str(e)}), 500

# 12. REDAÇÃO
@app.route('/correct-essay', methods=['POST'])
def correct_essay():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        essay = data.get('essay') or data.get('text') or data.get('essayText')
        theme = data.get('theme', 'Livre')

        prompt = f"""
        Corrija a redação sobre "{theme}". Texto: "{essay}"
        SAÍDA JSON: {{ "total_score": 0, "competencies": {{}}, "feedback": "..." }}
        """
        response = model.generate_content(prompt)
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" in json_text: json_text = json_text[json_text.find("{"):json_text.rfind("}")+1]
        try: return jsonify(json.loads(json_text))
        except: return jsonify({'correction': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 13. ENTREVISTA
@app.route('/mock-interview', methods=['POST'])
def mock_interview():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        role = data.get('role')
        desc = data.get('description') or data.get('company')

        prompt = f"""
        Simule entrevista para "{role}" ({desc}).
        SAÍDA JSON: {{ "questions": [{{ "q": "...", "a": "..." }}], "tips": ["..."] }}
        """
        response = model.generate_content(prompt)
        json_text = response.text.replace("```json", "").replace("```", "").strip()
        if "{" in json_text: json_text = json_text[json_text.find("{"):json_text.rfind("}")+1]
        try: return jsonify(json.loads(json_text))
        except: return jsonify({'message': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 14. MATERIAL ESTUDO
@app.route('/generate-study-material', methods=['POST'])
def generate_study_material():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        text = data.get('text') or data.get('topic')
        mode = data.get('mode', 'material')

        if mode == 'quiz':
            prompt = f"""
            Gere um Quiz sobre: "{text[:15000]}".
            SAÍDA JSON: {{ "questions": [{{ "question": "...", "options": ["..."], "answer": "...", "explanation": "..." }}] }}
            """
        else:
            prompt = f"Gere Material de Estudo sobre: {text[:15000]}"
        
        response = model.generate_content(prompt)
        try:
            json_text = response.text.replace("```json", "").replace("```", "").strip()
            if "{" in json_text: json_text = json_text[json_text.find("{"):json_text.rfind("}")+1]
            return jsonify(json.loads(json_text))
        except: return jsonify({'material': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 15. CARTA
@app.route('/generate-cover-letter', methods=['POST'])
def generate_cover_letter():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402
        
        job = data.get('job_desc') or data.get('job_description')
        cv = data.get('cv_text') or data.get('user_resume')
        
        prompt = f"Escreva uma Cover Letter para: {job}. CV: {cv}"
        response = model.generate_content(prompt)
        return jsonify({'cover_letter': response.text})
    except Exception as e: return jsonify({'error': str(e)}), 500

# 16. IMAGEM (Replicate)
@app.route('/generate-image', methods=['POST'])
def generate_image():
    try:
        data = request.get_json(force=True)
        if isinstance(data, str): data = json.loads(data)

        user_id = data.get('user_id')
        if user_id:
            s, m = check_and_deduct_credit(user_id)
            if not s: return jsonify({'error': m}), 402

        prompt = data.get('prompt') or data.get('text') or data.get('idea')
        
        if not prompt or len(prompt) < 10: return jsonify({'error': 'Prompt curto.'}), 400

        # SDXL
        output = replicate.run(
            "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            input={"prompt": prompt, "width": 1024, "height": 1024}
        )
        image_url = output[0] if isinstance(output, list) else output

        if supabase and user_id:
            supabase.table('image_history').insert({'user_id': user_id, 'prompt': prompt[:500], 'image_url': image_url}).execute()

        return jsonify({'success': True, 'image_url': image_url, 'prompt': prompt})
    except Exception as e: 
        return jsonify({'success': True, 'image_url': 'https://placehold.co/1024x1024/png?text=Erro+Replicate', 'error_detail': str(e)})

# --- HISTÓRICO ---
@app.route('/save-history', methods=['POST'])
def save_history():
    try:
        data = request.get_json(force=True)
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
        if request.method == 'GET':
            user_id = request.args.get('user_id')
            tool_type = request.args.get('tool_type')
        else:
            data = request.get_json(force=True)
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
        data = request.get_json(force=True)
        item_id = data.get('item_id') or data.get('id')
        if supabase and item_id:
            supabase.table('user_history').delete().eq('id', item_id).execute()
        return jsonify({'success': True})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- PAGAMENTOS ---
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        data = request.get_json(force=True)
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

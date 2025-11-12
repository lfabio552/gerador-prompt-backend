import os
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# --- Configuração Inicial ---
load_dotenv() # Carrega as variáveis do arquivo .env para o ambiente local
app = Flask(__name__)
CORS(app) 

# --- Configura a API do Gemini ---
# A biblioteca vai ler a chave da variável de ambiente que configuramos na Render
try:
    genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
    # MUDANÇA AQUI: Usando o modelo mais novo disponível na sua lista (Novembro 2025)
    model = genai.GenerativeModel('gemini-2.5-flash')
    print("Modelo Gemini configurado com sucesso!")
except Exception as e:
    print(f"Erro ao configurar o modelo Gemini: {e}")
    model = None

# --- ROTA PARA O GERADOR DE PROMPTS DE IMAGEM ---
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    if not model:
        return jsonify({'error': 'Modelo Gemini não foi configurado corretamente.'}), 500

    try:
        data = request.json
        simple_idea = data.get('idea')
        style = data.get('style', 'photorealistic')

        if not simple_idea:
            return jsonify({'error': 'A ideia não pode estar vazia.'}), 400

        # O prompt de instrução para o Gemini
        instruction_prompt = f"""
        Você é um especialista em engenharia de prompt para IAs de imagem.
        Transforme a seguinte ideia simples em um prompt detalhado, estruturado e otimizado em inglês.
        Ideia do usuário: "{simple_idea}"
        Estilo desejado: "{style}"

        Regras para o prompt gerado:
        - Expanda a ideia adicionando contexto, ambiente, iluminação cinematográfica, atmosfera e detalhes visuais ricos.
        - Inclua detalhes sobre personagens (aparência, expressão, roupas), cenário (hora do dia, paisagem, fundo), estilo artístico e detalhes técnicos da câmera (ângulo, lente, foco).
        - O resultado deve ser apenas o prompt em inglês, fluido e natural, sem nenhuma introdução ou explicação.
        """

        # Chamada para a API do Gemini
        response = model.generate_content(instruction_prompt)

        return jsonify({'advanced_prompt': response.text})

    except Exception as e:
        print(f"Erro durante a geração de conteúdo: {e}")
        return jsonify({'error': f'Ocorreu um erro ao gerar o prompt: {e}'}), 500

# --- NOVA ROTA PARA O GERADOR VEO 3 ---
@app.route('/generate-veo3-prompt', methods=['POST'])
def generate_veo3_prompt():
    if not model:
        return jsonify({'error': 'Modelo Gemini não foi configurado corretamente.'}), 500
    
    try:
        data = request.json
        # Coletando todos os dados do formulário
        scene = data.get('scene')
        style = data.get('style')
        camera = data.get('camera')
        lighting = data.get('lighting')
        audio = data.get('audio')

        if not scene:
            return jsonify({'error': 'A descrição da cena não pode estar vazia.'}), 400

        # Instrução detalhada para o Gemini, agora como um "diretor de cinema"
        instruction_prompt = f"""
        Você é um especialista em gerar prompts para IAs de vídeo como Google Veo. Sua tarefa é pegar os componentes estruturados fornecidos pelo usuário e montá-los em um prompt de vídeo coeso, detalhado e técnico em inglês.

        Componentes fornecidos pelo usuário:
        - Cena Principal: {scene}
        - Estilo Visual: {style}
        - Detalhes da Câmera: {camera}
        - Iluminação: {lighting}
        - Design de Áudio: {audio}

        Combine esses elementos em um parágrafo único e cinematográfico. Adicione detalhes técnicos relevantes que a IA de vídeo entenderia, como tipo de lente, movimento sutil, e especificidade de áudio. O resultado deve ser apenas o prompt final em inglês.
        """

        # Chamada para a API do Gemini
        response = model.generate_content(instruction_prompt)

        return jsonify({'advanced_prompt': response.text})

    except Exception as e:
        print(f"Erro durante a geração de conteúdo VEO 3: {e}")
        return jsonify({'error': f'Ocorreu um erro ao gerar o prompt de vídeo: {e}'}), 500

# --- Roda o Servidor (usado localmente) ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
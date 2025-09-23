import os
from dotenv import load_dotenv

import openai
from flask import Flask, request, jsonify
from flask_cors import CORS

load_dotenv()

# --- Configuração Inicial ---
app = Flask(__name__)
# A linha abaixo permite que o seu Frontend (que rodará em outro endereço) se comunique com o Backend.
CORS(app) 

# !! IMPORTANTE !!
# Cole aqui sua chave de API da OpenAI. Você pode obter uma no site da OpenAI.
# Lembre-se de manter esta chave em segredo.
openai.api_key = os.getenv('OPENAI_API_KEY')

# --- A Rota Principal da API ---
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
    try:
        data = request.json
        simple_idea = data.get('idea')
        style = data.get('style', 'photorealistic') # 'photorealistic' como padrão

        if not simple_idea:
            return jsonify({'error': 'A ideia não pode estar vazia.'}), 400

        # Aqui está a "mágica": o prompt que instrui a IA a criar o prompt avançado.
        system_prompt = """
        You are an advanced prompt generator for AI image models like DALL-E 3 and Midjourney.
        Your task is to transform a user's simple idea into a detailed, structured, and optimized prompt in English.
        Expand the idea by adding context, environment, lighting, atmosphere, and visual style.
        Include details about characters (appearance, expression, clothing), setting (time of day, landscape, background),
        artistic style, predominant colors, and technical camera details (camera angle, lens, focus).
        The final output must be only the generated prompt, without any introduction or explanation.
        """

        # O prompt do usuário, formatado para a IA
        user_prompt = f"Idea: '{simple_idea}'. Style: '{style}'."

        # Chamada para a API da OpenAI
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7 # Um valor que controla a criatividade
        )

        advanced_prompt = response.choices[0].message.content.strip()

        return jsonify({'advanced_prompt': advanced_prompt})

    except Exception as e:
        print(f"Erro: {e}")
        return jsonify({'error': 'Ocorreu um erro ao gerar o prompt.'}), 500

# --- Roda o Servidor ---
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
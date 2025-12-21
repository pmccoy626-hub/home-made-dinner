from flask import Flask, render_template, request, jsonify, send_file
import os
import io
import base64
import requests
from dotenv import load_dotenv
from openai import OpenAI
import tempfile

load_dotenv()

app = Flask(__name__)

# Initialize clients
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_STT_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# System prompt for cooking assistant
COOKING_SYSTEM_PROMPT = """You are a helpful cooking assistant. You provide clear, concise, and practical cooking advice. 
When answering questions about recipes, cooking times, temperatures, or techniques, be specific and actionable.
Keep responses brief (2-3 sentences max) and focus on the essential information the user needs.
If the user says goodbye or indicates they're done, acknowledge it politely."""

# Keywords that indicate the user wants to end the conversation
GOODBYE_KEYWORDS = ['goodbye', 'good bye', 'bye', 'see you', 'thanks', 'thank you', 'that\'s all', 'that is all', 'done', 'finished', 'stop']


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/transcribe', methods=['POST'])
def transcribe():
    """Convert speech to text using Deepgram REST API"""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        
        # Prepare headers
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
        }
        
        # Prepare query parameters
        params = {
            "model": "nova-2",
            "smart_format": "true"
        }
        
        # Send audio file to Deepgram
        files = {
            'audio': (audio_file.filename, audio_file.stream, audio_file.content_type)
        }
        
        response = requests.post(
            DEEPGRAM_STT_URL,
            headers=headers,
            params=params,
            files=files
        )
        
        response.raise_for_status()
        result = response.json()
        
        # Extract transcript
        transcript = result.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0].get('transcript', '')
        
        if not transcript:
            return jsonify({'error': 'No speech detected'}), 400
        
        return jsonify({'transcript': transcript})
                
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Deepgram API error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/ask', methods=['POST'])
def ask():
    """Send question to OpenAI and get response"""
    try:
        data = request.json
        question = data.get('question', '')
        
        if not question:
            return jsonify({'error': 'No question provided'}), 400
        
        # Get response from OpenAI
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": COOKING_SYSTEM_PROMPT},
                {"role": "user", "content": question}
            ],
            max_tokens=150,
            temperature=0.7
        )
        
        answer = response.choices[0].message.content
        
        return jsonify({'answer': answer})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/synthesize', methods=['POST'])
def synthesize():
    """Convert text to speech using Deepgram REST API"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
        
        # Prepare headers
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Prepare query parameters
        params = {
            "model": "aura-2-thalia-en"
        }
        
        # Prepare request body
        payload = {
            "text": text
        }
        
        # Send request to Deepgram TTS API
        response = requests.post(
            DEEPGRAM_TTS_URL,
            headers=headers,
            params=params,
            json=payload
        )
        
        response.raise_for_status()
        
        # Get audio data
        audio_buffer = io.BytesIO(response.content)
        audio_buffer.seek(0)
        
        return send_file(
            audio_buffer,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name='response.mp3'
        )
        
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Deepgram API error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/process_voice', methods=['POST'])
def process_voice():
    """Complete flow: STT -> OpenAI -> TTS"""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        
        # Step 1: Transcribe audio using Deepgram REST API
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
        }
        
        params = {
            "model": "nova-2",
            "smart_format": "true"
        }
        
        files = {
            'audio': (audio_file.filename, audio_file.stream, audio_file.content_type)
        }
        
        stt_response = requests.post(
            DEEPGRAM_STT_URL,
            headers=headers,
            params=params,
            files=files
        )
        
        stt_response.raise_for_status()
        stt_result = stt_response.json()
        
        transcript = stt_result.get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0].get('transcript', '')
        
        if not transcript:
            return jsonify({'error': 'No speech detected'}), 400
        
        # Step 2: Get answer from OpenAI
        openai_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": COOKING_SYSTEM_PROMPT},
                {"role": "user", "content": transcript}
            ],
            max_tokens=150,
            temperature=0.7
        )
        
        answer = openai_response.choices[0].message.content
        
        # Step 3: Synthesize speech using Deepgram REST API
        tts_headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "application/json"
        }
        
        tts_params = {
            "model": "aura-2-thalia-en"
        }
        
        tts_payload = {
            "text": answer
        }
        
        tts_response = requests.post(
            DEEPGRAM_TTS_URL,
            headers=tts_headers,
            params=tts_params,
            json=tts_payload
        )
        
        tts_response.raise_for_status()
        
        # Check if user said goodbye
        transcript_lower = transcript.lower()
        is_goodbye = any(keyword in transcript_lower for keyword in GOODBYE_KEYWORDS)
        
        # Convert to base64 for frontend
        audio_base64 = base64.b64encode(tts_response.content).decode('utf-8')
        
        return jsonify({
            'transcript': transcript,
            'answer': answer,
            'audio': f'data:audio/mpeg;base64,{audio_base64}',
            'is_goodbye': is_goodbye
        })
                
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Deepgram API error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)


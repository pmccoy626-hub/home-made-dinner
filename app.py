from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import os
import asyncio
import threading
import queue
import base64
import json
import websockets
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# API Keys
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# System prompt for cooking assistant
COOKING_SYSTEM_PROMPT = """You are a helpful cooking assistant. You provide clear, concise, and practical cooking advice. 
When answering questions about recipes, cooking times, temperatures, or techniques, be specific and actionable.
Keep responses brief (2-3 sentences max) and focus on the essential information the user needs.
IMPORTANT: When speaking, do NOT read out formatting symbols, markdown, asterisks, or special characters. Speak naturally as if having a conversation.
If the user says goodbye or indicates they're done, acknowledge it politely."""

# Keywords that indicate the user wants to end the conversation
GOODBYE_KEYWORDS = ['goodbye', 'good bye', 'bye', 'see you', 'thanks', 'thank you', 'that\'s all', 'that is all', 'done', 'finished', 'stop']

# Store active agent connections per session
active_agents = {}
# Store audio queues for each session (to pass audio from SocketIO to agent)
audio_queues = {}
# Store WebSocket connections per session
ws_connections = {}


@app.route('/')
def index():
    return render_template('index.html')


def create_agent_settings():
    """Create the agent configuration settings as a dictionary"""
    return {
        "type": "Settings",
        "audio": {
            "input": {
                "encoding": "linear16",
                "sample_rate": 44100
            }
        },
        "agent": {
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": "nova-2"
                }
            },
            "think": {
                "provider": {
                    "type": "open_ai",
                    "model": "gpt-4o-mini"
                },
                "prompt": COOKING_SYSTEM_PROMPT
            },
            "speak": {
                "provider": {
                    "type": "deepgram",
                    "model": "aura-2-asteria-en"
                }
            }
        }
    }


async def sender(ws, audio_queue, session_id):
    """Send audio chunks to Deepgram"""
    try:
        print(f'[Agent {session_id}] Audio sender started')
        while session_id in active_agents:
            try:
                # Get audio from queue (blocking with timeout)
                try:
                    audio_data = await asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: audio_queue.get(timeout=0.1)
                    )
                    if audio_data and ws:
                        await ws.send(audio_data)
                except queue.Empty:
                    continue
            except Exception as e:
                if session_id in active_agents:  # Only log if still active
                    print(f'[Agent {session_id}] Error in sender: {e}')
                break
    except Exception as e:
        print(f'[Agent {session_id}] Sender error: {e}')


async def receiver(ws, session_id):
    """Receive messages from Deepgram"""
    try:
        print(f'[Agent {session_id}] Receiver started')
        async for message in ws:
            if isinstance(message, str):
                # JSON message
                try:
                    message_json = json.loads(message)
                    message_type = message_json.get("type")
                    
                    if message_type == "Welcome":
                        session_id_from_msg = message_json.get("session_id")
                        print(f'[Agent {session_id}] Connected with session ID: {session_id_from_msg}')
                    
                    elif message_type == "ConversationText":
                        # Emit conversation text to client
                        content = message_json.get("content", "")
                        role = message_json.get("role", "user")
                        print(f'[Agent {session_id}] ConversationText - {role}: {content[:100]}')
                        
                        if role == "user":
                            socketio.emit("transcript", {
                                "text": content,
                                "is_final": True,
                                "role": "user"
                            }, room=session_id)
                        elif role == "assistant":
                            socketio.emit("agent_response", {
                                "text": content
                            }, room=session_id)
                        
                        # Check for goodbye keywords
                        content_lower = content.lower()
                        if any(keyword in content_lower for keyword in GOODBYE_KEYWORDS):
                            socketio.emit('goodbye_detected', {
                                'message': 'Goodbye detected. Ending conversation.'
                            }, room=session_id)
                    
                    elif message_type == "UserStartedSpeaking":
                        print(f'[Agent {session_id}] User started speaking')
                    
                    elif message_type == "AgentStartedSpeaking":
                        print(f'[Agent {session_id}] Agent started speaking')
                    
                    elif message_type == "CloseConnection":
                        print(f'[Agent {session_id}] CloseConnection received')
                        break
                    
                    else:
                        print(f'[Agent {session_id}] Received message type: {message_type}')
                
                except json.JSONDecodeError as e:
                    print(f'[Agent {session_id}] Error parsing JSON: {e}')
            
            elif isinstance(message, bytes):
                # Audio data from agent (TTS)
                # Only log occasionally to reduce noise
                if not hasattr(receiver, '_audio_count'):
                    receiver._audio_count = {}
                if session_id not in receiver._audio_count:
                    receiver._audio_count[session_id] = 0
                receiver._audio_count[session_id] += 1
                if receiver._audio_count[session_id] % 100 == 0:
                    print(f'[Agent {session_id}] Received {receiver._audio_count[session_id]} audio chunks')
                
                audio_base64 = base64.b64encode(message).decode('utf-8')
                socketio.emit('agent_audio', {
                    'audio': audio_base64,
                    'format': 'audio/pcm',
                    'sampleRate': 24000  # Deepgram Aura TTS uses 24kHz
                }, room=session_id)
    
    except Exception as e:
        print(f'[Agent {session_id}] Receiver error: {e}')
    finally:
        if session_id in active_agents:
            del active_agents[session_id]
        if session_id in ws_connections:
            del ws_connections[session_id]


async def run_agent(session_id):
    """Main agent async function"""
    audio_queue = queue.Queue()
    audio_queues[session_id] = audio_queue
    active_agents[session_id] = True
    
    try:
        settings = create_agent_settings()
        print(f'[Agent {session_id}] Connecting to Deepgram...')
        
        # Connect to Deepgram WebSocket
        ws = await websockets.connect(
            "wss://agent.deepgram.com/v1/agent/converse",
            additional_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
        )
        ws_connections[session_id] = ws
        print(f'[Agent {session_id}] Connected to Deepgram')
        
        # Send settings
        await ws.send(json.dumps(settings))
        print(f'[Agent {session_id}] Settings sent')
        
        # Emit agent_ready to frontend
        socketio.emit('agent_ready', {'status': 'connected'}, room=session_id)
        print(f'[Agent {session_id}] Emitted agent_ready event')
        
        # Run sender and receiver concurrently
        await asyncio.gather(
            sender(ws, audio_queue, session_id),
            receiver(ws, session_id),
        )
    
    except Exception as e:
        print(f'[Agent {session_id}] Error in run_agent: {e}')
        import traceback
        traceback.print_exc()
        socketio.emit('agent_error', {'error': str(e)}, room=session_id)
    finally:
        # Cleanup
        if session_id in active_agents:
            del active_agents[session_id]
        if session_id in audio_queues:
            del audio_queues[session_id]
        if session_id in ws_connections:
            try:
                await ws_connections[session_id].close()
            except:
                pass
            del ws_connections[session_id]
        print(f'[Agent {session_id}] Connection closed and cleaned up')


def run_agent_in_thread(session_id):
    """Run the async agent in a new event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_agent(session_id))
    except Exception as e:
        print(f'[Agent {session_id}] Error in thread: {e}')
        import traceback
        traceback.print_exc()
    finally:
        loop.close()


@socketio.on('connect')
def handle_connect():
    session_id = request.sid
    print(f'[SocketIO] Client connected: {session_id}')
    emit('connected', {'status': 'ok'})


@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    print(f'[SocketIO] Client disconnected: {session_id}')
    # Cleanup
    if session_id in active_agents:
        del active_agents[session_id]
    if session_id in audio_queues:
        del audio_queues[session_id]


@socketio.on('start_conversation')
def handle_start_conversation():
    session_id = request.sid
    print(f'[SocketIO] start_conversation received from {session_id}')
    
    if session_id in active_agents:
        emit('error', {'message': 'Conversation already active'})
        return
    
    print(f'[SocketIO] Starting agent thread for {session_id}')
    emit('conversation_started', {'status': 'starting'}, room=session_id)
    
    # Start agent in a separate thread
    thread = threading.Thread(target=run_agent_in_thread, args=(session_id,), daemon=True)
    thread.start()


@socketio.on('audio_chunk')
def handle_audio_chunk(data):
    session_id = request.sid
    
    if session_id not in audio_queues:
        return
    
    try:
        # Decode base64 audio
        audio_base64 = data.get('audio', '')
        audio_bytes = base64.b64decode(audio_base64)
        
        # Put audio in queue
        audio_queues[session_id].put(audio_bytes)
    except Exception as e:
        print(f'[SocketIO] Error processing audio chunk: {e}')


@socketio.on('end_conversation')
def handle_end_conversation():
    session_id = request.sid
    print(f'[SocketIO] end_conversation received from {session_id}')
    
    # Cleanup
    if session_id in active_agents:
        del active_agents[session_id]
    if session_id in audio_queues:
        del audio_queues[session_id]
    
    emit('conversation_ended', {'status': 'ended'}, room=session_id)


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🚀 Home-made Dinner Voice Assistant Starting!")
    print("=" * 60)
    print("\nOpen http://127.0.0.1:5000 in your browser\n")
    print("=" * 60 + "\n")
    socketio.run(app, debug=True)

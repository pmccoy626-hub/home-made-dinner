# Home-made Dinner 🍳

A voice-powered cooking assistant that answers your cooking questions using:
- **Deepgram Speech-to-Text** - Converts your voice questions to text
- **OpenAI GPT** - Provides intelligent cooking answers
- **Deepgram Text-to-Speech** - Speaks the answer back to you

## Features

- 🎤 Voice input - Ask questions naturally by speaking
- 🤖 AI-powered responses - Get helpful cooking advice
- 🔊 Voice output - Hear answers spoken back to you
- 🎨 Beautiful, modern UI

## Setup

### 1. Clone or navigate to the project directory

```powershell
cd "Home-made Dinner"
```

### 2. Create a virtual environment

```powershell
python -m venv venv
```

### 3. Activate the virtual environment

**PowerShell:**
```powershell
.\venv\Scripts\Activate.ps1
```

**Command Prompt:**
```cmd
venv\Scripts\activate.bat
```

### 4. Install dependencies

```powershell
pip install -r requirements.txt
```

### 5. Set up environment variables

Copy the example environment file:
```powershell
Copy-Item env.example .env
```

Edit `.env` and add your API keys:
- Get your Deepgram API key from [https://console.deepgram.com/](https://console.deepgram.com/)
- Get your OpenAI API key from [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)

Your `.env` file should look like:
```
DEEPGRAM_API_KEY=your_actual_deepgram_key_here
OPENAI_API_KEY=your_actual_openai_key_here
```

**Important:** Do not use quotes around the API key values.

### 6. Run the application

```powershell
python app.py
```

The app will be available at [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Usage

1. Open the app in your browser
2. Click the "Click to Ask" button
3. Speak your cooking question (e.g., "How long should I grill hamburgers?")
4. Click the button again to stop recording
5. Wait for the AI to process and respond
6. Listen to the spoken answer!

## Example Questions

- "How long should I grill hamburgers?"
- "What temperature should I cook chicken at?"
- "How do I make perfect scrambled eggs?"
- "What's the best way to season a steak?"

## Technology Stack

- **Flask** - Web framework
- **Deepgram REST API** - Speech-to-text and text-to-speech
- **OpenAI API** - Natural language processing
- **HTML5 MediaRecorder API** - Browser audio recording

## License

MIT


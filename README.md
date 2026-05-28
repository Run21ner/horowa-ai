# HOROWA AI
A sci-fi voice assistant for Windows with Gemini, ChatGPT, and Claude support.

## Features
- **Voice Activation:** Hands-free control using the hotword ("Hey Horowa").
- **Multi-Model Support:** Native integration with Gemini, OpenAI, Claude, and local models via Ollama.
- **Immersive 3-Panel GUI:** Features a live logging terminal, hardware resource tracking, a code viewer with custom syntax highlighting, and an animated desktop sphere UI.
- **Skills Plugin System:** Automation tools that allow the AI to control apps, manage web tasks, and execute OS utilities.

## Setup
1. **Install Dependencies:**
```bash
   pip install -r requirements.txt
```

2. Create the Skills Folder (Crucial Step):
You must manually create a folder named skills for your automation tools to function properly:

If running from source: Create the skills folder directly inside your project directory (next to main.py).

If running the compiled .exe: Create the skills folder in the exact same directory where your .exe file sits.
```bash
📂 Your_Folder/
   ├── 📄 Horowa_AI_v1.0.exe  (or your main.py source files)
   └── 📁 skills/             <-- Create this empty folder!
```
3. Launch:
Run main.py (or launch your executable) — the built-in walkthrough setup wizard will guide you through adding your API keys and configuration settings.

# NOVA

A Python-based, voice-controlled AI assistant for Windows. NOVA listens to your voice, converts speech to text, uses an LLM "brain" to understand the command, and carries it out through a structured tool layer.

> Formerly known as Jarvis / LAM.

## Features

- **Voice input**: speech-to-text so you can talk to your PC
- **LLM command processing**: the model turns natural language into structured JSON tool calls
- **Tool layer**: actions are executed through defined tools instead of free-form code
- **Web and apps**: open websites and applications, search Google and YouTube
- **System control**: volume, screenshots, restart, sleep, shutdown
- **Utilities**: calculator, timezone handling, email reading
- **File management**: delete files by name or by date
- **App indexing**: scans installed apps so NOVA can launch them by name
- **UI**: a graphical interface for interacting with the assistant

## Architecture

```
Microphone -> Speech-to-Text -> LLM Brain -> JSON Tool Call -> Tool Layer -> Action
                                                  ^                            |
                                                  +------- Result / Memory ----+
```

1. **Speech-to-text** captures and transcribes what you say.
2. **The LLM brain** interprets the transcript and decides which tool to call.
3. **The tool layer** validates the JSON call and executes the matching action.
4. **Results** are returned to the user (and to memory, where supported).

## Requirements

- Windows 11
- Python 3.11
- A working microphone
- API key(s) for the LLM and speech services you use (e.g. Gemini, Deepgram)

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/<adonishdi99-ops>/nova.git
cd nova

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your environment variables
copy .env.example .env
# then open .env and add your API keys
```

## Configuration

Create a `.env` file in the project root (see `.env.example`):

```env
GEMINI_API_KEY=your_key_here
DEEPGRAM_API_KEY=your_key_here
```

Never commit your `.env` file. It is already listed in `.gitignore`.

## Usage

```bash
python main.py
```

Then try saying things like:

- "Open YouTube"
- "Search Google for Python tutorials"
- "Take a screenshot"
- "Turn the volume up"
- "What is 245 times 18?"

> Replace `main.py` with your actual entry file if it is named differently.

## Project Structure

```
nova/
├── main.py              # Entry point
├── requirements.txt     # Python dependencies
├── .env.example         # Template for environment variables
├── .gitignore
├── LICENSE
└── README.md
```

> Update this tree to match your real folders (brain, tools, UI, etc.).

## Safety Notes

NOVA can run system actions (shutdown, restart, file deletion). Review the tools you enable, and be careful with delete commands.

## Roadmap

- [ ] Full AI-agent architecture with autonomous task handling
- [ ] Persistent memory support
- [ ] RAG capabilities
- [ ] More tools and integrations

## Contributing

Issues and pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

Released under the [MIT License](LICENSE).

## Author

**Adonis**, Software Engineering student at FUNAAB, Nigeria.
Vosk Speech Recognition & LLM Integration GUI
This project is a Python-based GUI application that uses Vosk for real-time speech recognition and integrates with a Language Model (LLM) API for processing transcribed text. The application provides an intuitive interface for selecting the input microphone and recognition model, starting/stopping audio processing, manually dumping the recognized text to an LLM, and monitoring the API endpoints used.

Table of Contents
Features
Prerequisites
Project Structure
Installation
Configuration
Usage
API Endpoints Testing
License
Features
Real-Time Speech Recognition: Uses Vosk models to convert audio from a selected microphone into text.
Model Selection: Choose from multiple Vosk models stored in a dedicated directory.
Automatic & Manual Dumping: Accumulated transcription is periodically (or manually) sent to an LLM endpoint for processing.
LLM Integration: Send the transcribed text to an LLM API (for example, an endpoint running locally) and display the response.
API Health Checks: Background tests on several API endpoints provide real-time status updates.
User-Friendly GUI: Built using PyQt5 for an interactive experience.
Prerequisites
Before running the application, ensure you have the following installed:

Python 3.7+
PyQt5: For the GUI
bash
Copy
pip install PyQt5
Vosk: For speech recognition
bash
Copy
pip install vosk
sounddevice: For capturing audio from your microphone
bash
Copy
pip install sounddevice
Requests: For making HTTP requests to the LLM API and testing endpoints
bash
Copy
pip install requests
You will also need a working LLM API endpoint (for example, running locally at http://localhost:1234/v1/chat/completions). Adjust the LLM_API_URL in the code if necessary.

Project Structure
The project directory should have the following structure:

bash
Copy
/project-directory
│
├── config.json          # (Optional) Configuration file for saving settings.
├── icon.png             # Application icon (optional).
├── log.txt              # Log file for recording application events.
├── main.py              # Main Python script (contains the GUI and logic).
├── extract_info.py      # (Optional) Script for extracting useful info via the LLM.
└── model/               # Directory containing Vosk model subdirectories.
    ├── model1/          # Example Vosk model directory.
    ├── model2/          # Another example model directory.
    └── ...              # Additional model directories as needed.
Important Notes on the Directory Structure
Model Directory (model/):
Place your Vosk models in this folder. Each model must be in its own subdirectory. For example:

Copy
model/
  ├── small_model/
  └── large_model/
The program automatically scans this folder and populates the model selection combo box with the names of the subdirectories.

Configuration File (config.json):
The program saves and loads user preferences (such as the selected microphone and model) from config.json. This file will be created in the project directory if it does not already exist.

Installation
Clone the repository or copy the project files to your local machine.
Install the required Python packages using pip:
bash
Copy
pip install -r requirements.txt
(Alternatively, install each package individually as shown in the Prerequisites section.)
Download or prepare your Vosk models and place them in the model/ directory as described above.
Configuration
LLM API URL:
By default, the code is set to use http://localhost:1234/v1/chat/completions. If your API endpoint is different, update the LLM_API_URL variable in the code.

Audio Settings:
The default sample rate (SAMPLERATE) is set to 16,000 Hz and the block size (BLOCKSIZE) to 8000. These values can be modified in the source code if your setup requires different settings.

Timer Settings:
The application automatically dumps accumulated text to the LLM every 120 seconds (adjustable via self.dump_interval in the code). You can disable this timer using the GUI toggle button.

Usage
Run the Application:
Start the application by running:
bash
Copy
python main.py
Select Input Devices:
In the GUI, use the dropdown menus to select:
The desired microphone (input device).
The Vosk model from the list of model subdirectories in the model/ folder.
Start Listening:
Click the "Start Listening" button to begin audio capture and transcription.
Manual Dump:
The recognized text is continuously accumulated in the GUI.
Use the "Manually Dump" button to immediately send the accumulated text to the LLM.
Timer Control:
The timer (which automatically dumps text every set interval) can be toggled on/off using the "Disable Timer"/"Enable Timer" button.
API Status:
The application automatically tests several API endpoints and displays their status in the GUI.
API Endpoints Testing
The program includes a mechanism to test multiple API endpoints:

Models Endpoint: Retrieves available models from the LLM API.
Chat Completions Endpoint: Sends a test chat message.
Completions Endpoint: Sends a test completion request.
Embeddings Endpoint: Tests embedding functionality.
Each endpoint is tested in a separate thread upon startup, and the status is updated every 10 minutes.

Extending the Program
Extracting Useful Information:
The extract_info.py script demonstrates how to use the LLM API to extract useful information from text. This runs the API call in a separate thread and calls a callback function with the result.

Logging:
Logging is configured to write events (except routine recognition messages) to log.txt for debugging or audit purposes.
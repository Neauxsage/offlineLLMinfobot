import os
import json
import queue
import threading
import time
import requests
import logging
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QLineEdit, QFrame, QScrollArea, QSpinBox
from PyQt5.QtCore import QTimer
from PyQt5.QtCore import Qt, QTimer as PyQtTimer
from PyQt5.QtGui import QIcon
import sounddevice as sd
from vosk import Model, KaldiRecognizer

# Global constants
CONFIG_FILE = "config.json"
BASE_MODEL_DIR = "model"
LOG_FILE = "log.txt"
SAMPLERATE = 16000      # Default sample rate (Hz)
BLOCKSIZE = 8000        # Default block size
TIMEOUT = 0.1           # Timeout for queue get
LLM_API_URL = "http://localhost:1234/v1/chat/completions"  # LLM endpoint URL

# API endpoints to test independently.
API_ENDPOINTS = [
    {
        "name": "Models",
        "method": "GET",
        "url": "http://localhost:1234/v1/models"
    },
    {
        "name": "Chat Completions",
        "method": "POST",
        "url": "http://localhost:1234/v1/chat/completions",
        "json": {"messages": [{"role": "user", "content": "Test"}]}
    },
    {
        "name": "Completions",
        "method": "POST",
        "url": "http://localhost:1234/v1/completions",
        "json": {"prompt": "Test", "max_tokens": 5}
    },
    {
        "name": "Embeddings",
        "method": "POST",
        "url": "http://localhost:1234/v1/embeddings",
        "json": {"input": "Test"}
    }
]

# Configure logging to a file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s: %(message)s',
    filename=LOG_FILE,
    filemode='a'
)

class SpeechRecognitionGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vosk Speech Recognition GUI")
        self.setGeometry(100, 100, 800, 750)
        self.setWindowIcon(QIcon("icon.png"))

        # Variables for device/model selection and fine-tuning
        self.selected_mic = None
        self.selected_model = None
        self.sample_rate = SAMPLERATE
        self.block_size = BLOCKSIZE
        self.timeout = TIMEOUT

        # New variable: dump interval for sending text to LLM (in seconds)
        self.dump_interval = 120
        self.time_remaining = self.dump_interval  # seconds until next dump
        self.timer_running = False
        self.timer_enabled = True  # Determines if the timer is active

        # Flags and threads
        self.listening = False
        self.audio_thread = None

        # Queue for incoming audio data
        self.audio_queue = queue.Queue(maxsize=20)
        self.transcribed_text = ""  # Holds accumulated recognized text

        # Dictionary to hold API LED widget references keyed by endpoint index.
        self.api_widgets = {}

        self.create_widgets()
        self.load_config()

        # Start the timer updates for LLM dump if enabled
        if self.timer_enabled:
            self.timer_running = True
            self.update_timer()

        # Start API tests for each endpoint immediately.
        for index, ep in enumerate(API_ENDPOINTS):
            self.test_endpoint(index, ep)

    def log(self, message):
        """Thread-safe logging to the log file, only for LLM responses."""
        if not message.startswith("Recognized:"):
            logging.info(message)

    def get_input_devices(self):
        """Returns a list of available input devices with index and name."""
        devices = sd.query_devices()
        input_devices = []
        for idx, dev in enumerate(devices):
            if dev['max_input_channels'] > 0:
                input_devices.append(f"{idx}: {dev['name']}")
        return input_devices

    def get_model_list(self):
        """Returns a list of subdirectories in the model folder."""
        models = []
        if not os.path.isdir(BASE_MODEL_DIR):
            self.log(f"Model directory '{BASE_MODEL_DIR}' not found.")
            QApplication.instance().quit()  # Correct way to exit in PyQt5
        else:
            for entry in os.listdir(BASE_MODEL_DIR):
                full_path = os.path.join(BASE_MODEL_DIR, entry)
                if os.path.isdir(full_path):
                    models.append(entry)
            if not models:
                self.log(f"No model subdirectories found in '{BASE_MODEL_DIR}'.")
                QApplication.instance().quit()  # Exit if no models are found
        return models



    def manual_dump(self):
        """Manually trigger the dump to the LLM and reset the timer."""
        self.dump_text_to_llm()
        if self.timer_enabled:
            self.timer_running = True
            self.time_remaining = self.dump_interval

    def create_widgets(self):
        """Create the GUI layout and widgets."""
        layout = QVBoxLayout()

        # Top frame: device and model selection, plus start/stop, manual dump, and timer toggle buttons.
        top_frame = QHBoxLayout()
        layout.addLayout(top_frame)

        # Microphone selection
        top_frame.addWidget(QLabel("Select Microphone:"))
        self.mic_combo = QComboBox()
        self.mic_combo.addItems(self.get_input_devices())
        top_frame.addWidget(self.mic_combo)

        # Model selection
        top_frame.addWidget(QLabel("Select Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(self.get_model_list())
        top_frame.addWidget(self.model_combo)

        # Buttons: Start/Stop Listening and Manual Dump
        self.start_stop_btn = QPushButton("Start Listening")
        self.start_stop_btn.clicked.connect(self.toggle_listening)
        top_frame.addWidget(self.start_stop_btn)

        self.manual_dump_btn = QPushButton("Manually Dump")
        self.manual_dump_btn.clicked.connect(self.manual_dump)
        top_frame.addWidget(self.manual_dump_btn)

        # Timer toggle button
        self.timer_toggle_btn = QPushButton("Disable Timer")
        self.timer_toggle_btn.clicked.connect(self.toggle_timer)
        top_frame.addWidget(self.timer_toggle_btn)

        # Timer display
        self.timer_label = QLabel(f"Next dump in: {self.time_remaining} seconds")
        layout.addWidget(self.timer_label)

        # API Status Section
        api_frame = QVBoxLayout()
        layout.addLayout(api_frame)
        for index, ep in enumerate(API_ENDPOINTS):
            row_layout = QHBoxLayout()
            api_frame.addLayout(row_layout)
            row_layout.addWidget(QLabel(f"{ep.get('name')}:"))

            status_label = QLabel("Checking...")
            row_layout.addWidget(status_label)
            self.api_widgets[index] = status_label

        # Transcribed text area
        self.transcribed_text_area = QScrollArea()
        layout.addWidget(self.transcribed_text_area)

        # LLM Response area
        self.llm_response_area = QScrollArea()
        layout.addWidget(self.llm_response_area)

        self.setLayout(layout)
        
        
    def test_endpoint(self, index, ep):
        """Test a single API endpoint in a separate thread and update its status label."""
        def run_test():
            success = True
            error_msg = ""
            method = ep.get("method")
            url = ep.get("url")

            try:
                if method == "GET":
                    response = requests.get(url, timeout=5)
                elif method == "POST":
                    response = requests.post(url, json=ep.get("json", {}), timeout=5)
                else:
                    success = False
                    error_msg = f"Unsupported method: {method}"
                    response = None

                if response is not None and response.status_code != 200:
                    success = False
                    error_msg = f"Status {response.status_code}"
            except Exception as e:
                success = False
                error_msg = str(e)

            # Update the status label on the main thread
            self.update_api_status(index, success, error_msg)
            
            # Schedule the next test for this endpoint in 10 minutes (600,000 ms)
            PyQtTimer.singleShot(600000, lambda: self.test_endpoint(index, ep))

        threading.Thread(target=run_test, daemon=True).start()

    def update_api_status(self, index, success, error_msg):
        """Update the API status label for a specific endpoint."""
        if index in self.api_widgets:
            status_label = self.api_widgets[index]
            if success:
                status_label.setText("OK")
            else:
                status_label.setText(f"Error: {error_msg}")


    def load_config(self):
        """Load saved configuration from a file if it exists."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                saved_mic = config.get("microphone", "")
                saved_model = config.get("models", "")
                if saved_mic in self.mic_combo:
                    self.selected_mic = saved_mic
                if saved_model in self.model_combo:
                    self.selected_model = saved_model
                self.log("Configuration loaded.")
            except Exception as e:
                self.log(f"Error loading config: {e}")
        else:
            if self.mic_combo:
                self.selected_mic = self.mic_combo[0]
            if self.model_combo:
                self.selected_model = self.model_combo[0]

    def save_config(self):
        """Save the current configuration to a file."""
        config = {
            "microphone": self.selected_mic,
            "model": self.selected_model
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)
            self.log("Configuration saved.")
        except Exception as e:
            self.log(f"Error saving config: {e}")

    def toggle_listening(self):
        """Toggle between starting and stopping the listening process."""
        if not self.listening:
            self.save_config()
            self.listening = True
            self.start_stop_btn.setText("Stop Listening")
            self.audio_thread = threading.Thread(target=self.audio_processing, daemon=True)
            self.audio_thread.start()
            self.log("Started listening.")
        else:
            self.listening = False
            self.start_stop_btn.setText("Start Listening")
            self.log("Stopping listening...")

    def audio_callback(self, indata, frames, time_info, status):
        """Callback function that gets called for each audio block."""
        if status:
            self.log(f"Audio input status: {status}")
        try:
            if not self.audio_queue.full():
                self.audio_queue.put(bytes(indata))
        except Exception as e:
            self.log(f"Error in audio callback: {e}")

    def audio_processing(self):
        """Background thread that initializes the recognizer and processes audio."""
        mic_value = self.selected_mic
        try:
            mic_index = int(mic_value.split(":")[0])
            self.log(f"Selected microphone index: {mic_index}")
        except Exception as e:
            self.log(f"Error parsing microphone selection: {e}")
            self.listening = False
            return

        model_dir = os.path.join(BASE_MODEL_DIR, self.selected_model)
        if not os.path.exists(model_dir):
            self.log(f"Selected model directory '{model_dir}' does not exist.")
            self.listening = False
            return

        try:
            self.log(f"Loading model from '{model_dir}' ...")
            model = Model(model_dir)
            recognizer = KaldiRecognizer(model, self.sample_rate)
            self.log("Model loaded successfully.")
        except Exception as e:
            self.log(f"Error loading model: {e}")
            self.listening = False
            return

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                dtype='int16',
                channels=1,
                callback=self.audio_callback,
                device=mic_index
            ):
                self.log("Microphone initialized. Listening for speech...")
                while self.listening:
                    try:
                        data = self.audio_queue.get(timeout=self.timeout)
                    except queue.Empty:
                        continue

                    if recognizer.AcceptWaveform(data):
                        result_json = recognizer.Result()
                        result_dict = json.loads(result_json)
                        text = result_dict.get("text", "")
                        if text:
                            self.transcribed_text += text + "\n"
                            self.transcribed_text_area.append(f"Recognized: {text}\n")
        except Exception as e:
            self.log(f"Audio processing error: {e}")
        finally:
            self.log("Audio processing stopped.")
            self.listening = False
            self.start_stop_btn.setText("Start Listening")

    def request_llm_in_thread(self, data):
        """Runs the LLM API call in a separate thread to avoid blocking the UI."""
        def make_request():
            try:
                response = requests.post(LLM_API_URL, json=data)
                if response.status_code == 200:
                    result = response.json()
                    useful_info = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    self.log(f"Useful information extracted:\n{useful_info}")
                    self.llm_response_area.append(f"LLM Response: {useful_info}\n")
                else:
                    self.log("Error in LLM API request.")
            except Exception as e:
                self.log(f"Error sending to LLM: {e}")

        thread = threading.Thread(target=make_request, daemon=True)
        thread.start()

    def dump_text_to_llm(self):
        """Dumps the accumulated transcribed text to the LLM for processing."""
        if self.transcribed_text.strip():
            data = {
                "messages": [{"role": "user", "content": self.transcribed_text}],
            }
            self.request_llm_in_thread(data)
            self.transcribed_text = ""  # Clear text after dump
        self.time_remaining = self.dump_interval  # Reset the timer based on the current interval
        if self.timer_enabled:
            self.timer_running = True
            self.update_timer()

    def update_timer(self):
        """Updates the countdown timer for the next LLM dump."""
        if self.timer_running and self.timer_enabled:
            self.time_remaining -= 1
            self.timer_label.setText(f"Next dump in: {self.time_remaining} seconds")
            if self.time_remaining <= 0:
                self.dump_text_to_llm()
            else:
                PyQtTimer.singleShot(1000, self.update_timer)

    def toggle_timer(self):
        """Toggle automatic LLM dump timer on/off."""
        if self.timer_enabled:
            # Disable the timer
            self.timer_enabled = False
            self.timer_running = False
            self.timer_toggle_btn.setText("Enable Timer")
            self.timer_label.setText("Timer disabled")
            self.log("LLM dump timer disabled.")
        else:
            # Enable the timer and reset the countdown
            self.timer_enabled = True
            self.time_remaining = self.dump_interval
            self.timer_running = True
            self.timer_toggle_btn.setText("Disable Timer")
            self.update_timer()
            self.log("LLM dump timer enabled.")

    def create_widgets(self):
        layout = QVBoxLayout()

        # Top frame: device and model selection, plus start/stop, manual dump, and timer toggle buttons.
        top_frame = QHBoxLayout()
        layout.addLayout(top_frame)

        # Microphone selection
        top_frame.addWidget(QLabel("Select Microphone:"))
        self.mic_combo = QComboBox()
        self.mic_combo.addItems(self.get_input_devices())
        top_frame.addWidget(self.mic_combo)

        # Model selection
        top_frame.addWidget(QLabel("Select Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(self.get_model_list())
        top_frame.addWidget(self.model_combo)

        # Buttons: Start/Stop Listening and Manual Dump
        self.start_stop_btn = QPushButton("Start Listening", self)
        self.start_stop_btn.clicked.connect(self.toggle_listening)
        top_frame.addWidget(self.start_stop_btn)

        self.manual_dump_btn = QPushButton("Manually Dump", self)
        self.manual_dump_btn.clicked.connect(self.manual_dump)
        top_frame.addWidget(self.manual_dump_btn)

        # Timer toggle button to enable/disable the LLM dump timer
        self.timer_toggle_btn = QPushButton("Disable Timer", self)
        self.timer_toggle_btn.clicked.connect(self.toggle_timer)
        top_frame.addWidget(self.timer_toggle_btn)

        # Fine-tuning settings
        self.timer_label = QLabel(f"Next dump in: {self.time_remaining} seconds")
        layout.addWidget(self.timer_label)

        # API LED indicators
        api_frame = QVBoxLayout()
        layout.addLayout(api_frame)
        for index, ep in enumerate(API_ENDPOINTS):
            row_layout = QHBoxLayout()
            api_frame.addLayout(row_layout)
            row_layout.addWidget(QLabel(f"{ep.get('name')}:"))

            status_label = QLabel("Checking...")
            row_layout.addWidget(status_label)
            self.api_widgets[index] = status_label

        # Transcribed text area
        self.transcribed_text_area = QScrollArea()
        layout.addWidget(self.transcribed_text_area)

        # LLM Response area
        self.llm_response_area = QScrollArea()
        layout.addWidget(self.llm_response_area)

        self.setLayout(layout)

    def on_closing(self):
        """Handles cleanup when the window is closed."""
        if self.listening:
            self.listening = False
            self.close()

if __name__ == '__main__':
    app = QApplication([])
    gui = SpeechRecognitionGUI()
    gui.show()
    app.exec_()

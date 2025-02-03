import requests
import threading

LLM_API_URL = "http://localhost:1234/v1/chat/completions"

def extract_useful_info(text, callback=None):
    """
    Extract useful information from the given text using the LLM.
    If a callback is provided, it will be called with the result.
    This function runs the API call in a separate thread.
    """
    # System message to instruct the model to be concise
    system_message = {
        "role": "system",
        "content": (
            ""

        )
    }


    data = {
        "messages": [
            system_message,
            {"role": "user", "content": text},
        ],
    }

    def make_request():
        try:
            response = requests.post(LLM_API_URL, json=data)
            if response.status_code == 200:
                result = response.json()
                useful_info = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if callback:
                    callback(useful_info)
            else:
                if callback:
                    callback("Error in LLM API request.")
        except Exception as e:
            if callback:
                callback(f"Error sending to LLM: {e}")

    thread = threading.Thread(target=make_request, daemon=True)
    thread.start()

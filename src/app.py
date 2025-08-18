from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import os
import uuid
import datetime
import threading
from .utils import call_function
from .models import generate_response
import json

from .core.auth_middleware import (
    extract_otp_from_message,
    pending_function_calls,
    find_pending_emp_id_for_user,
    get_auth_stats,
    authenticated_employee_mapping,
)
from .core.auth import (
    verify_otp,
    is_authenticated,
    pending_otps,
    get_authenticated_employee,
)
from .constants import system_call_llama, system_call_openai
from .watch_inbox import watch_inbox

load_dotenv()

# Check for ngrok auth token
NGROK_AUTH_TOKEN = os.environ.get("NGROK_AUTH_TOKEN")
NGROK_PATH = os.environ.get("NGROK_PATH")  # Allow users to specify custom path
USE_NGROK = NGROK_AUTH_TOKEN is not None

# Initialize ngrok if token is available
if USE_NGROK:
    try:
        import pyngrok.ngrok as ngrok
        from pyngrok.conf import PyngrokConfig

        # Build config with optional custom path
        ngrok_config = PyngrokConfig(ngrok_version="v3")
        if NGROK_PATH:
            ngrok_config.ngrok_path = NGROK_PATH
            print(f"📂 Using custom ngrok path: {NGROK_PATH}")

        # Set auth token with config
        ngrok.set_auth_token(NGROK_AUTH_TOKEN, pyngrok_config=ngrok_config)
        print(f"✅ Ngrok authentication configured")
    except ImportError:
        print(
            "⚠️ Pyngrok not installed. Run 'pip install pyngrok' to enable ngrok tunneling."
        )
        print("   Add it to your project: pip install pyngrok")
        USE_NGROK = False
    except Exception as e:
        print(f"⚠️ Failed to initialize ngrok: {e}")
        print("   Try setting a custom path with NGROK_PATH environment variable")
        print("   Or download ngrok manually from https://ngrok.com/download")
        USE_NGROK = False

# Store conversation history per user
conversation_history = {}
# Dictionary to store user session data
user_sessions = {}

use_local_model = True
MODEL_ID = os.getenv("HF_MODEL_ID")
if not MODEL_ID:
    print("MODEL_ID is not set, using OpenAI")
    use_local_model = False


system_call = system_call_llama if use_local_model else system_call_openai

app = Flask(
    __name__,
    static_folder="static",  # Explicitly define static folder
    template_folder="templates",
)  # Explicitly define templates folder


def process_message(message, user_id):
    """Main chat function - handles normal conversation"""
    print(f"📨 Received message: '{message}'")

    # Initialize conversation history
    if user_id not in conversation_history:
        conversation_history[user_id] = [{"role": "system", "content": system_call}]

    user_conv_history = conversation_history[user_id]

    # Debug commands
    if message == "debug_auth":
        authenticated_emp = get_authenticated_employee(user_id)
        return {
            "message": f"User: {user_id[:8]}...\nAuthenticated as Employee: {authenticated_emp or 'None'}",
            "require_auth": False,
        }

    if message == "reset_all":
        from .core.auth import clear_authentication

        clear_authentication(user_id)
        if user_id in pending_function_calls:
            del pending_function_calls[user_id]
        if user_id in conversation_history:
            conversation_history[user_id] = [{"role": "system", "content": system_call}]
        return {
            "message": "🧹 All session data reset",
            "require_auth": False,
        }

    user_conv_history.append({"role": "user", "content": message})

    # Generate response
    # while True:
    tool_call, response = generate_response(user_conv_history, use_local_model)
    executed_tool = False
    assistant_message = ""

    if tool_call:
        print(f"🔧 Calling function: {response.name}")

        if use_local_model:
            call_result = call_function(
                response.name, response.parameters.model_dump_json(), user_id
            )
            callID = None
        else:
            call_result = call_function(response.name, response.arguments, user_id)
            callID = response.call_id

        # Check if authentication is required
        if call_result.get("auth_required"):
            auth_message = call_result["message"]
            # Show popup flow for OTP (NOT an error)
            if "Access denied" in auth_message or "🚫" in auth_message:
                # Hard deny -> just show it
                user_conv_history.append({"role": "assistant", "content": auth_message})
                return {"message": auth_message, "require_auth": False}
            return {"message": auth_message, "require_auth": True}

        if call_result.get("is_file_search"):
            if use_local_model:
                # If using local model, include file search results in context
                user_conv_history.append(
                    {
                        "role": "user",
                        "content": "Here is the context from the tool-call:\n"
                        + call_result["message"],
                    }
                )
            else:
                user_conv_history.append(response)  # the function_call
                user_conv_history.append(
                    {
                        "type": "function_call_output",
                        "call_id": callID if callID else None,
                        "output": call_result["message"],
                    }
                )

            tool_call, response2 = generate_response(user_conv_history, use_local_model)
            user_conv_history.append({"role": "assistant", "content": response2})
            return {"message": response2, "require_auth": False}

        # Normal function execution
        user_conv_history.append(
            {"role": "assistant", "content": call_result["message"]}
        )
        return {"message": call_result["message"], "require_auth": False}
    else:
        user_conv_history.append({"role": "assistant", "content": response})

        assistant_message = response
        return {
            "message": assistant_message,
            "require_auth": False,
        }


def handle_otp_submission(otp_input, user_id):
    """Handle OTP submission from popup"""
    if not otp_input or len(otp_input.strip()) != 6:
        return {"success": False, "message": "❌ Please enter a valid 6-digit OTP"}

    # Find pending employee ID
    emp_id = find_pending_emp_id_for_user(user_id)
    if not emp_id:
        return {"success": False, "message": "❌ No pending authentication found"}

    # Verify OTP
    result = verify_otp(user_id, emp_id, otp_input.strip())

    if not result["authenticated"]:
        return {"success": False, "message": f"❌ {result['message']}"}

    # Execute pending function call (if any)
    pending_call = pending_function_calls.get(user_id)
    if not pending_call:
        return {"success": True, "message": "✅ Authentication successful!"}

    print(f"🔄 Executing pending function: {pending_call}")

    call_result = call_function(
        pending_call["func_name"],
        json.dumps(pending_call["func_args"]),
        user_id,
    )

    # Add to conversation history
    user_conv_history = conversation_history[user_id]

    # Normal function execution
    user_conv_history.append(
        {"role": "assistant", "content": call_result.get("message", "")}
    )

    # Clear pending call
    pending_function_calls.pop(user_id, None)

    # Bubble up any error from the function call in a user-friendly way
    if not call_result.get("ok", False):
        return {
            "success": False,
            "message": call_result.get("message", "❌ Something went wrong."),
        }

    return {"success": True, "message": call_result.get("message", "")}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    session_id = data.get("session_id", "")

    # Create session if not exists
    if not session_id:
        session_id = str(uuid.uuid4())

    if session_id not in user_sessions:
        user_sessions[session_id] = {"user_id": str(uuid.uuid4())}

    user_id = user_sessions[session_id]["user_id"]

    response = process_message(message, user_id)

    return jsonify(
        {
            "message": response["message"],
            "require_auth": response["require_auth"],
            "session_id": session_id,
        }
    )


@app.route("/api/verify-otp", methods=["POST"])
def verify_otp_endpoint():
    data = request.json
    otp = data.get("otp", "")
    session_id = data.get("session_id", "")

    if session_id not in user_sessions:
        return jsonify({"success": False, "message": "Invalid session"})

    user_id = user_sessions[session_id]["user_id"]

    result = handle_otp_submission(otp, user_id)

    return jsonify(result)


def start_ngrok():
    """Start ngrok tunnel"""
    port = 5000
    public_url = ngrok.connect(port)
    print(f"🌐 NGrok Public URL: {public_url}")


if __name__ == "__main__":
    print("🔄 Starting inbox watcher thread...")
    threading.Thread(target=watch_inbox, daemon=True).start()

    # Start ngrok if available
    if USE_NGROK:
        try:
            # Start ngrok in a thread to get the public URL
            threading.Thread(target=start_ngrok, daemon=True).start()
        except Exception as e:
            print(f"❌ Failed to start ngrok: {e}")

    print("🚀 Starting HR-Bot...")
    print(f"💻 Local URL: http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)

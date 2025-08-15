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
    while True:
        tool_call, response = generate_response(user_conv_history, use_local_model)
        executed_tool = False
        assistant_message = ""

        if tool_call:
            print(f"🔧 Calling function: {response.name}")

            if use_local_model:
                result, isFileSearch = call_function(
                    response.name, response.parameters.model_dump_json(), user_id
                )
            else:
                result, isFileSearch = call_function(
                    response.name, response.arguments, user_id
                )
                callID = response.call_id

            # Check if authentication is required
            if isinstance(result, dict) and result.get("auth_required", False):
                # Check if this is an access denied message (not OTP needed)
                auth_message = result["message"]
                if "Access denied" in auth_message or "🚫" in auth_message:
                    # This is access denied, not OTP required - show in chat only
                    user_conv_history.append(
                        {"role": "assistant", "content": auth_message}
                    )
                    return {
                        "message": auth_message,
                        "require_auth": False,
                    }
                else:
                    # This requires OTP popup - DON'T add to conversation history
                    if user_id in pending_function_calls:
                        pending_function_calls[user_id]["original_message"] = message
                    return {
                        "message": auth_message,
                        "require_auth": True,
                    }

            if isFileSearch:
                user_conv_history.append(
                    {"role": "assistant", "content": str(response)}
                )
                user_conv_history.append(
                    {
                        "type": "function_call_output",
                        "call_id": callID,
                        "output": json.dumps(result),
                    }
                )
                tool_call, response = generate_response(
                    user_conv_history, use_local_model
                )
                user_conv_history.append({"role": "assistant", "content": response})
                return {"message": response, "require_auth": False}

            # Normal function execution
            user_conv_history.append({"role": "assistant", "content": result})
            return {
                "message": result,
                "require_auth": False,
            }
        else:
            user_conv_history.append({"role": "assistant", "content": response})

            assistant_message = response
            return {
                "message": assistant_message,
                "require_auth": False,
            }

        # if not executed_tool:
        #     break

    # return assistant_message
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

    if result["authenticated"]:
        # Execute pending function call
        if user_id in pending_function_calls:
            pending_call = pending_function_calls[user_id]
            print(f"🔄 Executing pending function: {pending_call}")

            # Execute the function
            func_result = call_function(
                pending_call["func_name"],
                json.dumps(pending_call["func_args"]),
                user_id,
            )

            # Add to conversation history with proper format
            user_conv_history = conversation_history[user_id]

            # Generate a unique call ID
            call_id = f"call_{str(uuid.uuid4())[:8]}"

            # user_conv_history.append(
            #     {
            #         "type": "function_call",
            #         "name": pending_call["func_name"],
            #         "arguments": json.dumps(pending_call["func_args"]),
            #         "call_id": call_id,
            #     }
            # )
            user_conv_history.append({"role": "assistant", "content": func_result})

            # # Generate LLM response
            # try:
            #     response = generate_response(user_conv_history)
            #     assistant_message = ""
            #     for output in response.output:
            #         if output.type == "message":
            #             user_conv_history.append(
            #                 {"role": "assistant", "content": output.content}
            #             )
            #             assistant_message = output.content[0].text
            #             break

            # Clear pending call
            if user_id in pending_function_calls:
                del pending_function_calls[user_id]

            return {"success": True, "message": func_result}

            # except Exception as e:
            #     print(f"❌ Error generating response: {e}")
            #     error_message = f"✅ Authentication successful! Your leave balance data was retrieved, but I encountered an error generating the response. Employee {emp_id} data: {func_result}"

            #     # Clear pending call safely
            #     if user_id in pending_function_calls:
            #         del pending_function_calls[user_id]

            #     return {"success": True, "message": error_message}
        else:
            return {"success": True, "message": "✅ Authentication successful!"}
    else:
        return {"success": False, "message": f"❌ {result['message']}"}


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

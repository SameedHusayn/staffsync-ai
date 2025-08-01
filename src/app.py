from openai import OpenAI
import json
import gradio as gr
from dotenv import load_dotenv
import os
import uuid
from .hr_policy_vault import (
    search_policy,
    load_policies,
    get_or_create_policy_collection,
)
from .utils import generate_response, call_function
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

load_dotenv()

# Store conversation history per user
conversation_history = {}
hr_docs = get_or_create_policy_collection()
load_policies(hr_docs)

# Dictionary to store user session data
user_sessions = {}


def gradio_chat(message, history):
    """Main chat function - handles normal conversation"""
    print(f"📨 Received message: '{message}'")

    # Simple session management
    session_id = "main_session"
    if session_id not in user_sessions:
        user_sessions[session_id] = {"user_id": str(uuid.uuid4())}

    user_id = user_sessions[session_id]["user_id"]
    print(f"👤 User ID: {user_id}")

    # Initialize conversation history
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    user_conv_history = conversation_history[user_id]

    # Debug commands
    if message == "debug_auth":
        authenticated_emp = get_authenticated_employee(user_id)
        return f"User: {user_id[:8]}...\nAuthenticated as Employee: {authenticated_emp or 'None'}"

    if message == "reset_all":
        from .core.auth import clear_authentication

        clear_authentication(user_id)
        if user_id in pending_function_calls:
            del pending_function_calls[user_id]
        if user_id in conversation_history:
            conversation_history[user_id] = []
        return "🧹 All session data reset"

    # Process normal message
    contextful_message = search_policy(
        message, n_results=3, collection=hr_docs, extract_relevant=True
    )

    if contextful_message:
        context_text = "\n".join(
            [f"{doc} (from {meta['source']})" for doc, meta in contextful_message]
        )
        user_message_with_context = f"{message}\n\nContext:\n{context_text}"
    else:
        user_message_with_context = message

    user_conv_history.append({"role": "user", "content": user_message_with_context})

    # Generate response
    while True:
        response = generate_response(user_conv_history)
        executed_tool = False
        assistant_message = ""

        for output in response.output:
            if output.type == "function_call":
                print(f"🔧 Function call detected: {output.name}")

                # Call function with authentication check
                result = call_function(output.name, output.arguments, user_id)

                # Check if authentication is required
                if isinstance(result, dict) and result.get("auth_required", False):
                    # Check if this is an access denied message (not OTP needed)
                    auth_message = result["message"]
                    if "Access denied" in auth_message or "🚫" in auth_message:
                        # This is access denied, not OTP required - show in chat only
                        user_conv_history.append(
                            {"role": "assistant", "content": auth_message}
                        )
                        return auth_message
                    else:
                        # This requires OTP popup
                        if user_id in pending_function_calls:
                            pending_function_calls[user_id][
                                "original_message"
                            ] = message
                        return "AUTH_REQUIRED:" + auth_message

                # Normal function execution
                user_conv_history.append(output)
                user_conv_history.append(
                    {
                        "type": "function_call_output",
                        "call_id": output.call_id,
                        "output": json.dumps(result),
                    }
                )
                executed_tool = True

            elif output.type == "message":
                user_conv_history.append(
                    {"role": "assistant", "content": output.content}
                )
                assistant_message = output.content[0].text

        if not executed_tool:
            break

    return assistant_message


def handle_otp_submission(otp_input, chat_history):
    """Handle OTP submission from popup"""
    if not otp_input or len(otp_input.strip()) != 6:
        return (
            "❌ Please enter a valid 6-digit OTP",
            gr.update(visible=True),
            chat_history,
        )

    # Get current user
    session_id = "main_session"
    if session_id not in user_sessions:
        return "❌ Session expired", gr.update(visible=True), chat_history

    user_id = user_sessions[session_id]["user_id"]

    # Find pending employee ID
    emp_id = find_pending_emp_id_for_user(user_id)
    if not emp_id:
        return (
            "❌ No pending authentication found",
            gr.update(visible=True),
            chat_history,
        )

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

            user_conv_history.append(
                {
                    "type": "function_call",
                    "name": pending_call["func_name"],
                    "arguments": json.dumps(pending_call["func_args"]),
                    "call_id": call_id,
                }
            )
            user_conv_history.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(func_result),
                }
            )

            # Generate LLM response
            try:
                response = generate_response(user_conv_history)
                assistant_message = ""
                for output in response.output:
                    if output.type == "message":
                        user_conv_history.append(
                            {"role": "assistant", "content": output.content}
                        )
                        assistant_message = output.content[0].text
                        break

                # Update chat history display
                chat_history = chat_history or []
                chat_history.append({"role": "assistant", "content": assistant_message})

                # Clear pending call
                if user_id in pending_function_calls:
                    del pending_function_calls[user_id]

                # Return success and hide popup
                return "", gr.update(visible=False), chat_history

            except Exception as e:
                print(f"❌ Error generating response: {e}")
                error_message = f"✅ Authentication successful! Your leave balance data was retrieved, but I encountered an error generating the response. Employee {emp_id} data: {func_result}"
                chat_history = chat_history or []
                chat_history.append({"role": "assistant", "content": error_message})
                # Clear pending call safely
                if user_id in pending_function_calls:
                    del pending_function_calls[user_id]
                return "", gr.update(visible=False), chat_history
        else:
            chat_history = chat_history or []
            chat_history.append(
                {"role": "assistant", "content": "✅ Authentication successful!"}
            )
            return "", gr.update(visible=False), chat_history
    else:
        return f"❌ {result['message']}", gr.update(visible=True), chat_history


def close_otp_popup():
    """Close the OTP popup"""
    return "", gr.update(visible=False)


# Custom CSS for better OTP popup
css = """
.otp-popup {
    position: fixed !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    z-index: 1000 !important;
    background: white !important;
    border-radius: 16px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3) !important;
    padding: 30px !important;
    min-width: 400px !important;
    border: 2px solid #e1e5e9 !important;
}

.otp-input input {
    font-size: 28px !important;
    text-align: center !important;
    letter-spacing: 12px !important;
    padding: 15px !important;
    border: 3px solid #667eea !important;
    border-radius: 12px !important;
    background: #f8f9fa !important;
    font-weight: bold !important;
    color: #2d3748 !important;
    width: 280px !important;
    margin: 10px auto !important;
    display: block !important;
}

.otp-input input:focus {
    border-color: #4c51bf !important;
    box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.5) !important;
    outline: none !important;
}

.otp-title {
    font-size: 24px !important;
    font-weight: bold !important;
    color: #2d3748 !important;
    margin-bottom: 20px !important;
    text-align: center !important;
}

.otp-message {
    font-size: 16px !important;
    color: #4a5568 !important;
    margin-bottom: 25px !important;
    text-align: center !important;
    line-height: 1.5 !important;
}

.otp-buttons {
    display: flex !important;
    gap: 15px !important;
    justify-content: center !important;
    margin-top: 25px !important;
}

.otp-submit {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    border: none !important;
    padding: 12px 30px !important;
    border-radius: 8px !important;
    font-size: 16px !important;
    font-weight: 600 !important;
    cursor: pointer !important;
    transition: all 0.3s ease !important;
}

.otp-submit:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
}

.otp-cancel {
    background: #e2e8f0 !important;
    color: #4a5568 !important;
    border: 2px solid #cbd5e0 !important;
    padding: 12px 30px !important;
    border-radius: 8px !important;
    font-size: 16px !important;
    font-weight: 600 !important;
    cursor: pointer !important;
    transition: all 0.3s ease !important;
}

.otp-cancel:hover {
    background: #cbd5e0 !important;
    transform: translateY(-1px) !important;
}
"""

# Create the Gradio interface
with gr.Blocks(css=css, title="HR-Bot") as demo:
    gr.Markdown("# 🤖 HR-Bot")
    gr.Markdown(
        "Ask me about your leave balances, company policies, or submit leave requests!"
    )

    # Main chat interface
    chatbot = gr.Chatbot(height=400, type="messages")
    msg = gr.Textbox(placeholder="Type your message here...", container=False, scale=7)

    # OTP Popup (initially hidden)
    with gr.Group(visible=False, elem_classes=["otp-popup"]) as otp_popup:
        gr.Markdown("### 🔐 Authentication Required", elem_classes=["otp-title"])
        otp_message = gr.Markdown(
            "Please enter the 6-digit code sent to your email:",
            elem_classes=["otp-message"],
        )
        otp_input = gr.Textbox(
            placeholder="000000",
            max_lines=1,
            elem_classes=["otp-input"],
            container=False,
        )
        with gr.Row(elem_classes=["otp-buttons"]):
            otp_submit = gr.Button(
                "Submit", variant="primary", elem_classes=["otp-submit"]
            )
            otp_cancel = gr.Button(
                "Cancel", variant="secondary", elem_classes=["otp-cancel"]
            )
        otp_status = gr.Markdown("")

    # Chat submission
    def submit_message(message, history):
        if not message.strip():
            return history, ""

        # Add user message to history (messages format)
        history = history or []
        history.append({"role": "user", "content": message})

        # Get bot response
        bot_response = gradio_chat(message, history)

        # Check if authentication is required
        if bot_response.startswith("AUTH_REQUIRED:"):
            auth_message = bot_response[14:]  # Remove "AUTH_REQUIRED:" prefix
            history.append({"role": "assistant", "content": auth_message})
            # Show OTP popup
            return history, "", gr.update(visible=True), auth_message
        else:
            history.append({"role": "assistant", "content": bot_response})
            return history, "", gr.update(visible=False), ""

    # Event handlers
    msg.submit(submit_message, [msg, chatbot], [chatbot, msg, otp_popup, otp_message])

    otp_submit.click(
        handle_otp_submission, [otp_input, chatbot], [otp_status, otp_popup, chatbot]
    )

    otp_cancel.click(close_otp_popup, [], [otp_input, otp_popup])

    # Example buttons
    gr.Examples(
        examples=[
            "What's my annual leave balance? I am employee 1",
            "What's our company's dress code policy?",
            "I want to request 3 days of annual leave",
        ],
        inputs=msg,
    )

if __name__ == "__main__":
    print("🚀 Starting HR-Bot...")
    demo.launch(share=True, debug=True)

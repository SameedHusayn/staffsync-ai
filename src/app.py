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
)
from .core.auth import verify_otp, is_authenticated

load_dotenv()

# Store conversation history per user
conversation_history = {}
hr_docs = get_or_create_policy_collection()
load_policies(hr_docs)

# Dictionary to store user session data
user_sessions = {}


def gradio_chat(user_message, history):
    """
    Main chat function for Gradio interface

    Args:
        user_message: The message from the user
        history: The chat history

    Returns:
        str: The assistant's response
    """
    # Generate a user ID based on the history object's id if not already present
    chat_id = str(id(history))
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {"user_id": str(uuid.uuid4())}

    user_id = user_sessions[chat_id]["user_id"]

    # Initialize conversation history for this user if needed
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    user_conv_history = conversation_history[user_id]

    if user_message == "print_history":
        print(f"Conversation history for {user_id}:", user_conv_history)
        return "Debug: History printed to console"

    # Check if this message contains an OTP
    otp = extract_otp_from_message(user_message)
    if otp:
        # This might be an OTP response
        emp_id = find_pending_emp_id_for_user(user_id)
        if emp_id:
            result = verify_otp(user_id, emp_id, otp)
            if result["authenticated"]:
                # If the user has a pending function call, we'll resume it in the next exchange
                if user_id in pending_function_calls:
                    user_conv_history.append({"role": "user", "content": user_message})
                    user_conv_history.append(
                        {"role": "assistant", "content": result["message"]}
                    )
                    # Next message will trigger the pending function call
                    return result["message"]
                else:
                    # No pending call, but authentication succeeded
                    message = f"{result['message']} What would you like to know about your HR information?"
                    user_conv_history.append({"role": "user", "content": user_message})
                    user_conv_history.append({"role": "assistant", "content": message})
                    return message
            else:
                # Authentication failed
                user_conv_history.append({"role": "user", "content": user_message})
                user_conv_history.append(
                    {"role": "assistant", "content": result["message"]}
                )
                return result["message"]

    # Process the user message normally
    contextful_message = search_policy(
        user_message, n_results=3, collection=hr_docs, extract_relevant=True
    )
    if contextful_message:
        context_text = "\n".join(
            [f"{doc} (from {meta['source']})" for doc, meta in contextful_message]
        )
        user_message_with_context = f"{user_message}\n\nContext:\n{context_text}"
    else:
        user_message_with_context = user_message

    user_conv_history.append({"role": "user", "content": user_message_with_context})

    while True:
        response = generate_response(user_conv_history)
        executed_tool = False
        assistant_message = ""

        for output in response.output:
            if output.type == "function_call":
                user_conv_history.append(output)

                # Call function with authentication check
                result = call_function(output.name, output.arguments, user_id)

                # Check if this was an auth response
                if isinstance(result, dict) and result.get("auth_required", False):
                    # Authentication message - return directly to user
                    auth_message = result["message"]
                    user_conv_history.append(
                        {"role": "assistant", "content": auth_message}
                    )
                    return auth_message

                # Normal function response
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


demo = gr.ChatInterface(
    fn=gradio_chat,
    title="HR-Bot",
    description="Ask me about your annual, sick or casual leave balance.",
    examples=[
        "What's my annual leave balance? I am employee 123",
        "What's our company's dress code policy?",
    ],
    analytics_enabled=False,
    cache_examples=False,
)

if __name__ == "__main__":
    demo.launch(share=True)

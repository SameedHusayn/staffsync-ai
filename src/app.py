from openai import OpenAI
import json
import gradio as gr
from dotenv import load_dotenv
import os
from hr_policy_vault import (
    search_policy,
    load_policies,
    get_or_create_policy_collection,
)
from utils import generate_response, call_function

load_dotenv()

conversation_history = []
hr_docs = get_or_create_policy_collection()
load_policies(hr_docs)


def gradio_chat(user_message, history):
    global conversation_history

    if user_message == "print_history":
        print(conversation_history)
    contextful_message = search_policy(
        user_message, n_results=3, collection=hr_docs, extract_relevant=True
    )
    if contextful_message:
        context_text = "\n".join(
            [f"{doc} (from {meta['source']})" for doc, meta in contextful_message]
        )
        user_message = f"{user_message}\n\nContext:\n{context_text}"

    conversation_history.append({"role": "user", "content": user_message})

    while True:
        response = generate_response(conversation_history)
        executed_tool = False
        assistant_message = ""

        for output in response.output:
            if output.type == "function_call":
                conversation_history.append(output)
                result = call_function(output.name, output.arguments)
                conversation_history.append(
                    {
                        "type": "function_call_output",
                        "call_id": output.call_id,
                        "output": json.dumps(result),
                    }
                )
                executed_tool = True
            elif output.type == "message":
                conversation_history.append(
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
        "What's my annual leave balance?",
        "What's our company's dress code policy?",
    ],
)

demo.launch(share=True)

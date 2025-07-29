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

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is not set. "
        "Copy .env.example → .env and put your OpenAI API key."
    )

client = OpenAI(api_key=OPENAI_API_KEY)

tools = [
    {
        "type": "function",
        "name": "get_leave_balance",
        "description": "Return how many days of leave an employee still has available.",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_id": {
                    "type": "string",
                    "description": "The employee’s unique ID (e.g. 113654)",
                },
                "leave_type": {
                    "type": "string",
                    "enum": ["annual", "sick", "casual"],
                    "description": "Kind of leave the employee is asking about",
                },
            },
            "required": ["employee_id", "leave_type"],
            "additionalProperties": False,
        },
    },
    {
        "type": "file_search",
        "vector_store_ids": ["vs_68760ff6437081918e25d70393c7f53e"],
    },
]


def get_leave_balance(employee_id, leave_type):
    """
    Pretend this hits your HR database and looks up the balance.
    For the demo we simply hard‑code something.
    """
    dummy_db = {
        "12345": {"annual": 9, "sick": 5, "casual": 2},
        "67890": {"annual": 17, "sick": 8, "casual": 4},
    }
    balance = dummy_db.get(employee_id, {}).get(leave_type, 0)
    return {"remaining_days": balance}


def call_function(name, raw_args):
    args = json.loads(raw_args)
    if name == "get_leave_balance":
        return get_leave_balance(**args)


def generate_response(input_messages):
    tools = [
        {
            "type": "function",
            "name": "get_leave_balance",
            "description": "Return how many days of leave an employee still has available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "The employee’s unique ID (e.g. 113654)",
                    },
                    "leave_type": {
                        "type": "string",
                        "enum": ["annual", "sick", "casual"],
                        "description": "Kind of leave the employee is asking about",
                    },
                },
                "required": ["employee_id", "leave_type"],
                "additionalProperties": False,
            },
        }
    ]

    response = client.responses.create(
        model="gpt-4.1", input=input_messages, tools=tools
    )
    return response


conversation_history = []
hr_docs = get_or_create_policy_collection()
load_policies(hr_docs)


def gradio_chat(user_message, history):
    global conversation_history

    if user_message == "print_history":
        return "\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in conversation_history]
        )
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

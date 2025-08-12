from openai import OpenAI
import os
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import time
import json
from dotenv import load_dotenv
from pydantic import ValidationError
import textwrap
from .constants import tools
from .validation import ToolCall, extract_response, MAX_REPAIR_TRIES

load_dotenv()

MODEL_ID = os.getenv("HF_MODEL_ID")
if MODEL_ID:
    cache_dir = r"D:\LLMs"
    model_id = MODEL_ID
    print("Loading model:", model_id)
    tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)
    model = AutoModelForCausalLM.from_pretrained(model_id, cache_dir=cache_dir)
    print("Model loaded successfully.")


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is not set. "
        "Copy .env.example → .env and put your OpenAI API key."
    )


client = OpenAI(api_key=OPENAI_API_KEY)


def generate_response(input_messages, use_local_model, tools=tools):
    if not use_local_model:
        print("Generating response with input:", input_messages)
        response = client.responses.create(
            model="gpt-4.1", input=input_messages, tools=tools
        )
        print("Generated response:", response)
        for output in response.outputs:
            if output.type == "function_call":
                return True, output
            elif output.type == "message":
                return False, output.content

    else:
        for attempt in range(1, MAX_REPAIR_TRIES + 1):
            # generate
            inputs = tokenizer.apply_chat_template(
                input_messages, add_generation_prompt=True, return_tensors="pt"
            ).to(model.device)

            ids = model.generate(
                inputs,
                max_new_tokens=256,  # Increased to allow for longer responses
                eos_token_id=[
                    tokenizer.convert_tokens_to_ids("<|eot_id|>"),
                    tokenizer.convert_tokens_to_ids("<|eom_id|>"),
                ],
                pad_token_id=tokenizer.eos_token_id,
            )
            raw_reply = tokenizer.decode(
                ids[0][inputs.shape[-1] :], skip_special_tokens=False
            )
            print("Raw Reply:", raw_reply)

            # Extract response content
            is_tool_call, content = extract_response(raw_reply)

            if not is_tool_call:
                # Text response, just return it
                return False, content

            # Process tool call
            if not content:
                err = "No JSON object found."
            else:
                try:
                    tool_call = ToolCall.model_validate_json(content)
                    return True, tool_call  # 🎉 success with tool call
                except ValidationError as e:
                    err = f"Schema errors: {e.errors()}"

            # ask the model to repair
            repair_prompt = textwrap.dedent(
                f"""\
                Your previous reply contained a tool call that did not follow the required schema.

                Error details:
                {err}

                Please note:
                1. Employee ID must be an actual ID, not a placeholder like "your_employee_id"
                2. If you don't have the employee ID, you should ASK the user for it first, don't call the function

                Please reply again with **exactly one** valid JSON object that satisfies
                the schema you were given, or respond with a normal text message if a tool call is not needed or information is missing.
            """
            )

            input_messages.extend(
                [
                    {"role": "assistant", "content": raw_reply},
                    {"role": "system", "content": repair_prompt},
                ]
            )

        # Exhausted attempts, return an error message
        return (
            False,
            "I apologize, but I'm having trouble processing your request. Could you please rephrase or try again?",
        )

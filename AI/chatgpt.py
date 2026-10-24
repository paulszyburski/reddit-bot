import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("CHATGPT_API_KEY"))

SELECTION_MODEL = os.getenv("CHATGPT_SELECTION_MODEL") or "gpt-5-nano"


def generate_response(prompt, *, model="gpt-5.6-luna"):
    response = client.responses.create(
        model=model,
        input=prompt,
    )

    return response.output_text


def generate_selection_response(prompt):
    return generate_response(prompt, model=SELECTION_MODEL)

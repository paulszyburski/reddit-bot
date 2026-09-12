from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()


API = os.getenv("CHATGPT_API_KEY")

client = OpenAI(api_key=API)

SELECTION_MODEL = os.getenv("CHATGPT_SELECTION_MODEL") or "gpt-5-nano"


def generate_response(prompt, *, model="gpt-5.6-luna"):
    response = client.responses.create(
        model=model,
        input=prompt
    )

    return response.output_text


def generate_selection_response(prompt):
    """Use the cheaper model only for ranking candidate post titles."""
    return generate_response(prompt, model=SELECTION_MODEL)

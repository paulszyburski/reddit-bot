from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()


API = os.getenv("CHATGPT_API_KEY")

client = OpenAI(api_key=API)


def generate_response(prompt):
    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )

    return response.output_text
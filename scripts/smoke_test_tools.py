"""
Smoke test: verifica que el modelo de oMLX sea capaz de hacer tool calling.
Define una sola herramienta falsa (get_weather) y le pide al modelo que la use.
Imprime la respuesta cruda para inspección manual.
"""

import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_URL = os.environ["OMLX_BASE_URL"]
API_KEY = os.environ["OMLX_API_KEY"]
MODEL_ID = os.environ["MODEL_ID"]

GET_WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Devuelve el clima actual de una ciudad.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Nombre de la ciudad, e.g. 'Santiago'",
                }
            },
            "required": ["city"],
        },
    },
}

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

response = client.chat.completions.create(
    model=MODEL_ID,
    messages=[{"role": "user", "content": "¿Qué tiempo hace en Santiago?"}],
    tools=[GET_WEATHER_TOOL],
    tool_choice="auto",
)

print("=== Respuesta cruda ===")
print(response.model_dump_json(indent=2))

choice = response.choices[0]
tool_calls = choice.message.tool_calls

if tool_calls:
    call = tool_calls[0]
    args = json.loads(call.function.arguments)
    assert call.function.name == "get_weather", f"Nombre inesperado: {call.function.name}"
    assert "city" in args, f"Falta el campo 'city' en los argumentos: {args}"
    print(f"\n✓ Tool call correcto — función: {call.function.name}, ciudad: {args['city']}")
else:
    print("\n✗ El modelo NO generó un tool_call. Respuesta de texto:", choice.message.content)
    sys.exit(1)

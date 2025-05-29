import re 
from groq import AsyncGroq, GroqError
from bot_config import GROQ_MAX_TOKENS

async def validate_groq_api_key(api_key: str) -> tuple[bool, str | None]:
    if not api_key:
        return False, "API Key is empty."
    try:
        client = AsyncGroq(api_key=api_key)
        await client.models.list() 
        return True, None
    except GroqError as e:
        error_message = f"Type: {e.type if hasattr(e, 'type') else 'N/A'}, Message: {e.message if hasattr(e, 'message') else str(e)}"
        print(f"Groq API Key validation failed: {error_message}")
        return False, error_message
    except Exception as e:
        print(f"Unexpected error during Groq API Key validation: {repr(e)}")
        return False, repr(e)

# --- DEFINISI FUNGSI parse_ai_response DI SINI (SEBELUM get_groq_completion) ---
def parse_ai_response(raw_response: str) -> dict:
    """
    Memisahkan konten <think>...</think> dari respons utama.
    Mengembalikan dictionary dengan "main_response" dan "thoughts".
    Thoughts akan berisi gabungan semua konten think, atau None jika tidak ada.
    """
    thoughts_list = []
    # Pola regex untuk menemukan <think>...</think> (non-greedy)
    # re.DOTALL membuat . cocok dengan newline juga
    pattern = r"<think>(.*?)</think>"

    # Ekstrak semua blok <think>
    for match in re.finditer(pattern, raw_response, re.DOTALL):
        thoughts_list.append(match.group(1).strip())

    # Hapus semua blok <think> dari respons utama
    main_response = re.sub(pattern, "", raw_response, flags=re.DOTALL).strip()

    # Gabungkan semua thoughts jika ada
    all_thoughts = "\n---\n".join(thoughts_list) if thoughts_list else None

    return {"main_response": main_response, "thoughts": all_thoughts}
# --- AKHIR DEFINISI FUNGSI parse_ai_response ---

async def get_groq_completion(
    api_key: str, 
    model: str, 
    system_prompt_for_call: str, # Tetap ada untuk kompatibilitas jika full_messages_list tidak disediakan
    user_prompt_for_call: str,   # atau jika ingin override system prompt
    full_messages_list: list[dict] | None = None # Argumen baru
) -> dict | None:
    if not api_key:
        print("Groq API key is missing.")
        return {"main_response": "Groq API key is missing.", "thoughts": None}

    try:
        client = AsyncGroq(api_key=api_key)

        messages_to_send: list[dict]
        if full_messages_list:
            messages_to_send = full_messages_list
        else:
            # Fallback jika full_messages_list tidak disediakan (seharusnya tidak terjadi dengan logika baru)
            messages_to_send = [
                {"role": "system", "content": system_prompt_for_call if system_prompt_for_call else "You are a helpful assistant."},
                {"role": "user", "content": user_prompt_for_call}
            ]

        chat_completion = await client.chat.completions.create(
            messages=messages_to_send, # Gunakan list pesan yang sudah dirakit
            model=model,
            max_tokens=GROQ_MAX_TOKENS,
        )
        raw_response_content = chat_completion.choices[0].message.content

        parsed_response = parse_ai_response(raw_response_content)
        return parsed_response

    except GroqError as e:
        error_message = f"Type: {e.type if hasattr(e, 'type') else 'N/A'}, Message: {e.message if hasattr(e, 'message') else str(e)}"
        print(f"Groq API Error: {error_message}")
        return {"main_response": f"GROQ_API_ERROR: {error_message}", "thoughts": None}
    except Exception as e:
        print(f"An unexpected error occurred while calling Groq API: {repr(e)}")
        return {"main_response": f"UNEXPECTED_GROQ_ERROR: {repr(e)}", "thoughts": None}

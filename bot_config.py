DEFAULT_LANGUAGE = "en"
AVAILABLE_LANGUAGES = {
    "en": "English",
    "ru": "Русский",
    "id": "Bahasa Indonesia"
}
LOCALES_DIR = "locales"

AVAILABLE_GROQ_MODELS = [
    {
        "display_name": "Llama 3 (70B)", 
        "id": "llama3-70b-8192"
    },
    {
        "display_name": "Mixtral (8x7B)", 
        "id": "mixtral-8x7b-32768"
    },
    {
        "display_name": "Gemma 2 (9B IT)", 
        "id": "gemma2-9b-it"
    },
    {
        "display_name": "Deepseek R1 distill llama 70b", # Nama tampilan bisa lebih deskriptif
        "id": "deepseek-r1-distill-llama-70b"
    },
    {
        "display_name": "Llama 4 Scout (17B Alpha)", # Nama tampilan
        "id": "meta-llama/Llama-4-scout-17B-Chat-alpha-v0.1" 
    }
    # Tambahkan model lain di sini dengan format yang sama jika perlu
]

# DEFAULT_GROQ_MODEL tetap menyimpan ID model
DEFAULT_GROQ_MODEL = "llama3-70b-8192" 
# --- AKHIR PERUBAHAN ---

def get_model_display_name(model_id_to_find: str) -> str:
    for model_info in AVAILABLE_GROQ_MODELS:
        if model_info["id"] == model_id_to_find:
            return model_info["display_name"]
    return model_id_to_find 


GROQ_MAX_TOKENS = 512
CONVERSATION_HISTORY_LIMIT = 10
PRIVACY_POLICY_URL = "https://t.me/botaralabs/16" 
START_COMMAND_IMAGE_FILE_ID = "AgACAgUAAxkBAAIB0Gg1ROrJzEJPqk3XbYlyiWmuU0R6AAKZyTEbvRepVWq-f_fK236MAQADAgADeQADNgQ" 

MODERATION_LEVELS = {
    "disabled": "Disabled",
    "low": "Low",
    "normal": "Normal",
    "aggressive": "Aggressive",
    "very_aggressive": "Very Aggressive"
}
DEFAULT_MODERATION_LEVEL = "disabled"

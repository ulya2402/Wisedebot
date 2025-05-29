from aiogram.fsm.state import State, StatesGroup

class AISetupStates(StatesGroup):
    awaiting_groq_key = State()
    awaiting_system_prompt = State()
    awaiting_groq_model = State()
    confirm_ai_setup = State()
    confirm_overwrite = State() 
    confirm_reset = State()    
    awaiting_trigger_prefix = State()
    awaiting_welcome_message_status = State()
    awaiting_custom_welcome_message = State()
    awaiting_moderation_settings = State()


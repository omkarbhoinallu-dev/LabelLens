import requests
from google import genai
from google.genai import types
import streamlit as st

from prompts import SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE, SUMMARY_REQUEST_PROMPT

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
DEFAULT_CHAT_ID = str(st.secrets.get("TELEGRAM_CHAT_ID", ""))  # optional default

TELEGRAM_LIMIT = 4096  # max characters Telegram allows in one message


@st.cache_resource  # cache (store) the client
def get_gemini_client():  # class
    return genai.Client(api_key=GEMINI_API_KEY)  # object


gemini_client = get_gemini_client()
MODEL_NAME = "gemini-3.8-flash"


def clean_telegram_text(text):
    if not text:
        return "No label content summary available."
    return text.strip()


def split_text(text, limit=TELEGRAM_LIMIT):
    """Split long text into chunks under Telegram's limit, preferring line breaks."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def send_telegram(chat_id, user_name, summary):
    try:
        full_text = f"Hi {user_name}! Here's your LabelLens summary:\n\n{clean_telegram_text(summary)}"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        for chunk in split_text(full_text):
            response = requests.post(
                url,
                json={"chat_id": chat_id, "text": chunk},  # plain text, no parse_mode
                timeout=20,
            )
            data = response.json()
            if not data.get("ok"):
                return False, data.get("description", "Unknown Telegram error")
        return True, "sent"
    except Exception as error:
        return False, str(error)


def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.write(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"])


def add_message(role, kind, content):
    st.session_state.messages.append({"role": role, "kind": kind, "content": content})
    render_message(st.session_state.messages[-1])


def ask_gemini(parts):
    try:
        return st.session_state.chat.send_message(parts).text
    except Exception as error:
        return f"Sorry, something went wrong: {error}"


# step 1: onboarding (username and Telegram chat ID)

if 'onboarded' not in st.session_state:
    st.title("🏷️ LabelLens")
    st.caption("Snap it. Check the contents. Get the results on Telegram.")

    with st.form("onboarding_form"):
        name = st.text_input("Your name")
        telegram_chat_id = st.text_input(
            "Telegram chat ID",
            value=DEFAULT_CHAT_ID,
            placeholder="123456789",
            help="Open the LabelLens bot in Telegram and press Start first. "
                 "Your chat ID is the number LabelLens will message you on.",
        )
        submitted = st.form_submit_button("Let's go 🚀")
    if submitted:
        chat_id_clean = telegram_chat_id.strip()
        if not name.strip() or not chat_id_clean:  # if name and chat ID are not provided
            st.warning("Please fill in your name and Telegram chat ID.")
        elif not chat_id_clean.lstrip("-").isdigit():
            st.warning("Chat ID should be a number, like 123456789.")
        else:
            st.session_state.name = name.strip()
            st.session_state.telegram_chat_id = chat_id_clean

            # activate my ai
            st.session_state.chat = gemini_client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            st.session_state.messages = []
            st.session_state.onboarded = True
            st.rerun()
    st.stop()

# Create a chat interface

header_col, button_col = st.columns([5, 2], vertical_alignment="center")

with header_col:
    st.title("LabelLens")
with button_col:
    send_disabled = len(st.session_state.messages) <= 1
    if st.button("Send to Telegram", disabled=send_disabled, use_container_width=True):
        with st.spinner("Summarizing your labels..."):
            summary = ask_gemini([SUMMARY_REQUEST_PROMPT])
        success, info = send_telegram(
            st.session_state.telegram_chat_id,
            st.session_state.name,
            summary,
        )
        if success:
            st.success("Sent! Check your Telegram")
        else:
            st.error(f"Couldn't send that: {info}")
st.caption(f"Logged in as {st.session_state.name} - updates go to Telegram chat {st.session_state.telegram_chat_id}")

if not st.session_state.messages:
    add_message("assistant", "text", WELCOME_MESSAGE_TEMPLATE.format(name=st.session_state.name))
else:
    for message in st.session_state.messages:
        render_message(message)

user_input = st.chat_input(
    "Ask a question, or attach a photo of your label",
    accept_file=True,
    file_type=["jpg", "jpeg", "png"],
)

if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text
    parts = []

    if photo is not None:
        photo_bytes = photo.getvalue()
        add_message("user", "image", photo_bytes)
        parts.append(types.Part.from_bytes(data=photo_bytes, mime_type=photo.type))
    if text:
        add_message("user", "text", text)
        parts.append(text)
    elif photo is not None:
        parts.append("What is this label? Give me the name of the product.")

    with st.spinner("Fetching the label content..."):
        answer = ask_gemini(parts)
    add_message("assistant", "text", answer)

    # Rerun so the Send to Telegram button becomes enabled right away.
    st.rerun()

from google import genai
from google.genai import types
import streamlit as st
from twilio.rest import Client as TwilioClient
from prompt import SYSTEM_PROMPT, WELCOME_MESSAGE_TEMPLATE, SUMMARY_REQUEST_PROMPT
import json 


GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
TWLIO_ACCOUNT_SID = st.secrets["TWLIO_ACCOUNT_SID"]
TWLIO_TOKEN = st.secrets["TWLIO_TOKEN"]
Twil_ID_WHATSAPP_FORM=st.secrets["Twil_ID_WHATSAPP_FORM"]
TWIL_ID_CONTENT_SID=st.secrets["TWIL_ID_CONTENT_SID"]

@st.cache_resource #cache (store) the client
def get_gemini_client(): #class
    return genai.Client(api_key = GEMINI_API_KEY) #object

@st.cache_resource #cache (store) the client
def get_twilio_client(): #class
    return TwilioClient(TWLIO_ACCOUNT_SID, TWLIO_TOKEN) #object

gemini_client = get_gemini_client()
MODEL_NAME = "gemini-3.8-flash"
twilio_client=get_twilio_client()

def send_message(whatsapp, user_name, summary):
    try:
        content_variables = json.dumps(
            {"1": user_name, "2": clean_whatsapp_text(summary)}, ensure_ascii=False
        )
        message = twilio_client.messages.create(
            from_ = Twil_ID_WHATSAPP_FORM,
            to=f"whatsapp:{to_number}",
            content_sid = TWIL_ID_CONTENT_SID,
            content_variables = content_variables,
          )
        return True, message.sid
    except Exception as error:
        return False, str(error)
def clean_whatsapp_text(text):
    if not text:
        return "No label content summary available."
    text = " ".join(text.split()) #collapse whitespace/newlines
    return text[:1500] + "..." if len(text) > 1500 else text


def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"]=="text":
            st.write(message["content"])
        elif message["kind"]=="image":
            st.image(message["content"])

def add_message(role, kind, content):
    st.session_state.messages.append({"role":role, "kind":kind, "content":content})
    render_message(st.session_state.messages[-1])

def ask_gemini(parts):
    try:
        return st.session_state.chat.send_message(parts).text
    except Exception as error:
        return f"Sorry, something went wrong: {error}"
#step 1: onboarding (username and phone)

if('onboarded' not in st.session_state):
    st.title("🏷️ LabelLens")
    st.caption("Snap it. Check the contents. Text yourself the results.")

    with st.form("onboarding_form"):
        name = st.text_input("Your name")
        whatsapp_number = st.text_input(
            "Whatsapp number (with country code)",
            placeholder = "+91XXXXXXXXXX",
            help="This is the number LabelLens will text you on."
        )
        submitted = st.form_submit_button("Let's go 🚀")
    if submitted:
        if not name.strip() or not whatsapp_number.strip(): #if name and number is not provided
            st.warning("Please fill in your name and number.")
        else:
            st.session_state.name = name.strip()
            st.session_state.whatsapp_number = whatsapp_number.strip()

            #activate my ai
            st.session_state.chat = gemini_client.chats.create(
                model = MODEL_NAME,
                config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT)
            )
            st.session_state.messages = []
            st.session_state.onboarded = True
            st.rerun()
    st.stop()

#Create a chat interface

header_col, button_col = st.columns([5,2], vertical_alignment = "center")

with header_col:
    st.title("LabelLens")
with button_col:
    send_disabled = len(st.session_state.messages)<=1
    if st.button("Send to WhatsApp", disabled = send_disabled, use_container_width=True):
        with st.spinner("Summarizing your day..."):
            summary = ask_gemini(["SUMMARY_REQUEST_PROMPT"])
        success, info = send_whatsapp(st.session_state)
        if success:
            st.success("Sent! Check your WhatsApp")
        else:
            st.error(f"Couldn't send that: {info}")
st.caption(f"Logged in as {st.session_state.name} - updates go to {st.session_state.whatsapp_number}")

if not st.session_state.messages:
    add_message("assistant", "text", WELCOME_MESSAGE_TEMPLATE.format(name=st.session_state.name))

user_input = st.chat_input(
    "Ask a question, or attach a photo of your label",
    accept_file = True,
    file_type = ["jpg", "jpeg", "png"]
)

if user_input:
    photo = user_input.files[0] if user_input.files else None
    text = user_input.text
    parts = []

    if photo is not None:
        photo_bytes = photo.getvalue()
        add_message("user", "image", photo_bytes)
        parts.append(types.Part.from_bytes(data=photo_bytes, mime_type = photo.type))
    if text:
        add_message("user", "text", text)
        parts.append(text)
    elif photo is not None:
        parts.append("What is this label? Give me the name of the product.")
    
    with st.spinner("Fetching the label content..."):
        answer = ask_gemini(parts)
    add_message("assistant", "text", answer)
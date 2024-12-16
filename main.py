from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from collections import defaultdict
import requests
import time
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# 配置模板路径
templates = Jinja2Templates(directory="templates")

# Mock user conversations store
user_conversations = defaultdict(str)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "123123***"


@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    """Render the index.html template."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat")
async def chat_endpoint(chat_request: ChatRequest):
    user_input = chat_request.message
    user_id = chat_request.user_id

    conversation_id = retrieve_conversation_id(user_id)
    if not conversation_id:
        conversation_id = create_conversation(user_id)
        if not conversation_id:
            logger.error("Failed to create conversation")
            raise HTTPException(status_code=400, detail="Failed to create conversation")

    chat_id = chat_with_bot(user_input, user_id, conversation_id)
    logger.debug(f"chat_with_bot response (chat_id): {chat_id}")

    if chat_id:
        messages = retrieve_chat_messages(chat_id, conversation_id)
        logger.debug(f"Retrieved messages: {messages}")

        # Only extract messages with type 'answer'
        answer_messages = [msg for msg in messages if msg.get('type') == 'answer']
        if answer_messages:
            bot_response = answer_messages[0].get('content', 'No response from bot.')
            logger.debug(f"Bot response: {bot_response}")
            return {"message": bot_response}
        else:
            logger.error("No valid messages found")
            raise HTTPException(status_code=400, detail="No valid messages found")
    else:
        logger.error("Failed to chat with bot")
        raise HTTPException(status_code=400, detail="Failed to chat with bot")


def retrieve_conversation_id(user_id):
    """Retrieve the conversation_id for the user."""
    return user_conversations.get(user_id)


def save_conversation_id(user_id, conversation_id):
    """Save the conversation_id for the user."""
    user_conversations[user_id] = conversation_id


def create_conversation(user_id):
    """Create a new conversation and return the conversation_id."""
    api_url = 'https://api.coze.cn/v3/chat'
    headers = {
        'Authorization': 'Bearer pat_***',
        'Content-Type': 'application/json'
    }
    data = {
        "bot_id": "****",
        "user_id": user_id,
        "stream": False,
        "auto_save_history": True,
        "additional_messages": [
            {
                "role": "user",
                "content": "Start a new conversation",
                "content_type": "text"
            }
        ]
    }

    logger.debug(f"Creating conversation for user: {user_id}")
    response = requests.post(api_url, headers=headers, json=data)
    logger.debug(f"Create Conversation API Response status: {response.status_code}")
    logger.debug(f"Create Conversation API Response content: {response.text}")

    if response.status_code == 200:
        conversation_id = response.json().get('data', {}).get('conversation_id')
        if conversation_id:
            save_conversation_id(user_id, conversation_id)
        return conversation_id
    else:
        logger.error("Failed to create conversation.")
        return None


def chat_with_bot(user_input, user_id='123123***', conversation_id=None):
    """Handle chat with bot, using the provided conversation_id."""
    if not conversation_id:
        conversation_id = retrieve_conversation_id(user_id)

    if not conversation_id:
        conversation_id = create_conversation(user_id)

    if not conversation_id:
        logger.error("Failed to create or retrieve conversation_id")
        return None

    api_url = f'https://api.coze.cn/v3/chat?conversation_id={conversation_id}'
    headers = {
        'Authorization': 'Bearer *****',
        'Content-Type': 'application/json'
    }
    data = {
        "bot_id": "*****",
        "user_id": user_id,
        "stream": False,
        "auto_save_history": True,
        "additional_messages": [
            {
                "role": "user",
                "content": user_input,
                "content_type": "text"
            }
        ]
    }

    logger.debug(f"Sending request to Coze API: {data}")
    try:
        response = requests.post(api_url, headers=headers, json=data)
        logger.debug(f"Coze API Response status: {response.status_code}")
        logger.debug(f"Coze API Response content: {response.text}")

        response.raise_for_status()

        response_json = response.json()
        chat_id = response_json.get('data', {}).get('id')
        return chat_id
    except requests.exceptions.RequestException as e:
        logger.error(f"Error occurred while sending request to Coze API: {e}")
        return None


def retrieve_chat_messages(chat_id, conversation_id, max_retries=6, delay=4):
    """Retrieve messages from the chat using chat_id and conversation_id with retries."""
    api_url = f'https://api.coze.cn/v3/chat/message/list?chat_id={chat_id}&conversation_id={conversation_id}'
    headers = {
        'Authorization': 'Bearer pat_****',
        'Content-Type': 'application/json'
    }

    for attempt in range(max_retries):
        logger.debug(f"Retrieving messages for chat_id: {chat_id}, conversation_id: {conversation_id} (Attempt {attempt + 1})")
        try:
            response = requests.get(api_url, headers=headers)
            logger.debug(f"Retrieve Messages API Response status: {response.status_code}")
            logger.debug(f"Retrieve Messages API Response content: {response.text}")

            response.raise_for_status()

            response_json = response.json()
            messages = response_json.get('data', [])
            if messages:
                return messages

            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2  # Exponential backoff
        except requests.exceptions.RequestException as e:
            logger.error(f"Error occurred while retrieving messages: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2  # Exponential backoff

    logger.error("Max retries reached. Unable to retrieve messages.")
    return []


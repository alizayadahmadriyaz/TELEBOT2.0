import telebot
import os
import google.generativeai as genai
from pymongo import MongoClient
from dotenv import load_dotenv
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InputFile
import requests
import PIL.Image as PIL
# from telebot.util import escape_markdown
from io import BytesIO
# Load environment variables
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# print(TELEGRAM_BOT_TOKEN)
# Initialize APIs
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
users_col = db["users"]
chats_col = db["chats"]
files_col = db["files"]
genai.configure(api_key=GEMINI_API_KEY)

GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

def escape_markdown(text):
    special_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{char}" if char in special_chars else char for char in text)


def google_search(query):
    """Fetches top search results from Google Custom Search API."""
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_SEARCH_API_KEY}&cx={SEARCH_ENGINE_ID}"
    response = requests.get(url)
    if response.status_code != 200:
        return None, "Error fetching search results."
    data = response.json()
    results = data.get("items", [])
    
    if not results:
        return None, "No search results found."
    
    top_results = [f"{item['title']} - {item['link']}" for item in results[:5]]
    return top_results, "\n".join(top_results)

def summarize_results(results):
    """Uses Gemini AI to summarize search results."""
    model = genai.GenerativeModel("gemini-pro")
    try:
        response = model.generate_content(f"Summarize these search results:\n{results}")
        escaped_text = response.text
        return escaped_text
    except Exception as e:
        return "Error summarizing results."

@bot.message_handler(commands=['websearch'])
def web_search(message):
    chat_id = message.chat.id
    query = message.text.replace("/websearch", "").strip()
    
    if not query:
        bot.send_message(chat_id, "Please provide a search query. Example: /websearch Python programming")
        return
    
    bot.send_message(chat_id, f"Searching the web for: {query}...")
    
    search_results, formatted_results = google_search(query)
    print(search_results)
    if not search_results:
        bot.send_message(chat_id, formatted_results)
        return
    
    summary = summarize_results(formatted_results)
    response_message = f"🔎 **Search Summary:**\n{summary}\n\n🌐 **Top Links:**\n{formatted_results}"
    bot.send_message(chat_id, response_message)

def register_user(message):
    print(message)
    chat_id = message.chat.id
    user = message.from_user
    existing_user = users_col.find_one({"chat_id": chat_id})
    if not existing_user:
        users_col.insert_one({
            "chat_id": chat_id,
            "first_name": user.first_name,
            "username": user.username,
            "phone_number": None
        })
        bot.send_message(chat_id, "Welcome! Please share your phone number.", reply_markup=request_phone())
    else:
        bot.send_message(chat_id, "You're already registered!")

def request_phone():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    button = KeyboardButton("Share Contact", request_contact=True)
    markup.add(button)
    return markup

@bot.message_handler(content_types=['contact'])
def save_phone(message):
    chat_id = message.chat.id
    phone_number = message.contact.phone_number
    users_col.update_one({"chat_id": chat_id}, {"$set": {"phone_number": phone_number}})
    bot.send_message(chat_id, "Phone number saved successfully!")

@bot.message_handler(commands=['chat'])
def chat_with_gemini(message):
    chat_id = message.chat.id
    user_input = message.text
    
    model = genai.GenerativeModel("gemini-pro")  # Correct model usage
    response = model.generate_content(user_input)  # Get AI response
    escaped_text = response.text
    bot.send_message(chat_id, escaped_text)  # Send response text only
    chats_col.insert_one({"chat_id": chat_id, "user_input": user_input, "bot_response": escaped_text})

@bot.message_handler(content_types=['photo', 'document'])
def handle_files(message):
    chat_id = message.chat.id
    
    # Get File ID
    file_id = message.document.file_id if message.document else message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    
    # Download File
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_info.file_path}"
    response = requests.get(file_url)

    # Open Image with PIL
    image = PIL.open(BytesIO(response.content))
    image.show()
    # Use Gemini API to Analyze Image
    model = genai.GenerativeModel("gemini-1.5-pro")
    gemini_response = model.generate_content([image, "Describe this image."])
    
    # Send AI's Response
    bot.send_message(chat_id, f"Analysis: {gemini_response.text}")

    # Save to MongoDB
    files_col.insert_one({
        "chat_id": chat_id,
        "file_url": file_url,
        "description": gemini_response.text
    })

@bot.message_handler(commands=['start'])
def start_command(message):
    # print(message)
    register_user(message)
    chat_id = message.chat.id
    bot.send_message(chat_id, "/chat for chatting with bot   /websearch for searching to get your answer")
bot.polling()
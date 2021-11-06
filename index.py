import os
import string
from flask import Flask, request
from .local_cubacrypt import decypher
from dotenv import find_dotenv, load_dotenv
from pymongo import MongoClient

load_dotenv(find_dotenv())
mongoclient = MongoClient(os.getenv("MONGO"))
mongodb = mongoclient['database']
session = mongodb['sessions']
temp = mongodb['temp']

session_increment = []

web = Flask(__name__)

def generate_token(size=8, chars=string.ascii_uppercase + string.ascii_lowercase + string.digits):
	return ''.join(random.choice(chars) for _ in range(size))

def generate_message_id(size=8, chars=string.digits):
	return ''.join(random.choice(chars) for _ in range(size))

def connected_users(token):
    for session in session.find({ "token": token }):
        return session["connected_users"]

def validate_username(username):
    if len(username) >= 20 or len(username) <= 3:
        return False

    else:
        return True

def _create_session(username):
    if not validate_username(username):
        return { "complete": False, "reason": "Bad name", "code": "B01" }

    token = generate_token()
    token = f"{token}"
    payload = {
        "_id": len(session_increment),
        "token": token,
        "username": username,
        "connected_users": [username]
    }

    session.insert_one(payload)
    if len(session_increment) == 0:
        session_increment.append(0)
    else:
        session_increment.append(len(session_increment))
    return { "complete": True }

def _send_message(username, token, esm):
    if session.count_documents({ "token": token }) == 0:
        return { "complete": False, "reason": "Invalid token.", "code": "I01" }

    query = {
        "token": token
    }
    if username in connected_users(token):

        message_id = generate_message_id()
        message_id = f"{message_id}"
        payload = {
            "_id": message_id,
            "session": token
            "esm": esm,
            "users": {}
        }

        for user in data["connected_users"]:
            template = {
                "_id": message_id,
                "users": {
                    f"{user}": False
                }
            }
            payload.update(template)

        temp.insert_one(payload)
        return { "complete": True }

    else:
        return { "complete": False, "reason": "User not in session.", "code": "I02" }

def is_sent_before(username, token, message_id):
    for data in temp.find({ "message_id": message_id, "session": token }):
        if data["users"][username] == False:
            return False

        else:
            return True

def add_user_to_session(token, username):
    query = {
        "token": token
    }
    payload = {
        "$addToSet": {
            "connected_users": username
        }
    }
    session.update_one(query, payload)

def remove_user_from_session(token, username):
    query = {
        "token": token
    }
    payload = {
        "$pull": {
            "connected_users": username
        }
    }
    session.update_one(quey, payload)

def _fetch_messages(username, token):
    if username in connected_users(token):
        for message in temp.find({}):
            if message["session"] == token and is_sent_before(username, token, message["message_id"]):
                query = {
                    "_id": message["message_id"],
                    "session": token,
                    "esm": message["esm"]
                }

                update_payload = {
                    "$set": {
                        "_id": message["message_id"],
                        "users": {
                            f"{username}": True
                        }
                    }
                }
                temp.update_one(query, update_payload)

                payload = {
                    "esm": message["esm"]
                }

        await asyncio.sleep(5)
        add_user_to_session(token, username)
        await asyncio.sleep(5)
        remove_user_from_session(token, username)

    else:
        add_user_to_session(token, username)

@web.route("/create-session", methods=["POST"])
def create_session():
    data = request.get_json(force=True)
    return _create_session(username=data["username"])

@web.route("/send-message", methods=["POST"])
def send_message():
    data = request.get_json(force=True)
    return _send_message(username=data["username"], token=data["token"], esm=data["esm"])

@web.route("/fetch-messages", methods=["POST"])
def fetch_messages():
    data = request.get_json(force=True)
    return _fetch_messages(data["username"], data["token"])

@web.route("/decypher", methods=["POST"])
def decypher_esm():
    data = request.get_json(force=True)
    return decypher(data["esm"])

web.run(host="0.0.0.0", port=8080, debug=True)

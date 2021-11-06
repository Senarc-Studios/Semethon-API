import os
from flask import Flask, request
from dotenv import find_dotenv, load_dotenv
from pymongo import MongoClient

load_dotenv(find_dotenv())
mongoclient = MongoClient(os.getenv("MONGO"))
mongodb = mongoclient['database']
session = mongodb['sessions']

session_increment = []

web = Flask(__name__)

def generate_token(size=8, chars=string.ascii_uppercase + string.ascii_lowercase + string.digits):
	return ''.join(random.choice(chars) for _ in range(size))

def validate_username(username):
    if len(username) >= 20 or len(username) <= 3:
        return False

    else:
        return True

def _create_session(username):
    if not validate_username(username):
        return { "complete": False, "reason": "Bad name", "code": 01 }

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

@web.route("/create-session", methods=["POST"])
def create_session():
    data = request.get_json(force=True)
    return _create_session(username=data["username"])

@web.route("/send-message", methods=["POST"])
def send_message():
    data = request.get_json(force=True)
    return _send_message(username=data["username"], token=data["token"], esm=data["esm"])

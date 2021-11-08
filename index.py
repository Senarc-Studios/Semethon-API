import os
import json
import flask
import string
import random
from utils import get_data
from flask import Flask, request
from local_cubacrypt import decypher
from dotenv import find_dotenv, load_dotenv
from pymongo import MongoClient

load_dotenv(find_dotenv())
mongoclient = MongoClient(get_data("config", "MONGO"))
mongodb = mongoclient['database']
session = mongodb['sessions']
temp = mongodb['temp']

session_increment = []

web = Flask(__name__)

async def auto_purge_message(message_id):
    await asyncio.sleep(5)
    temp.delete_one({ "_id": message_id })

def generate_token(size=8, chars=string.ascii_uppercase + string.ascii_lowercase + string.digits):
	return ''.join(random.choice(chars) for _ in range(size))

def generate_message_id(size=8, chars=string.digits):
	return ''.join(random.choice(chars) for _ in range(size))

def connected_users(token):
    for sessions in session.find({ "token": token }):
        return sessions["connected_users"]

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

def validate_username(username):
    if len(username) >= 20 or len(username) <= 3:
        return False

    else:
        return True

def _create_session(username):
    if not validate_username(username):
        return json.dumps({ "complete": False, "reason": "Bad name", "code": "B01" }), 400

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
    return json.dumps({ "token": token }), 200, {'content-type': 'application/json'}

def _join_session(username, token):
    if not validate_username(username):
        return json.dumps({ "complete": False, "reason": "Bad name", "code": "B01" }), 400

    add_user_to_session(token, username)
    return json.dumps({ "complete": True }), 200, {'content-type': 'application/json'}

def _validate_session(token):
    if session.count_documents({ "token": token }) == 0:
        return json.dumps({ "found": False }), 400, {'content-type': 'application/json'}

    else:
        return json.dumps({ "found": True }), 200, {'content-type': 'application/json'}

def _send_message(username, token, esm):
    if session.count_documents({ "token": token }) == 0:
        return json.dumps({ "complete": False, "reason": "Invalid token.", "code": "I01" }), 400, {'content-type': 'application/json'}

    query = {
        "token": token
    }
    if username in connected_users(token):

        message_id = generate_message_id()
        message_id = f"{message_id}"
        payload = {
            "_id": message_id,
            "session": token,
            "author": username,
            "esm": esm,
            "users": {}
        }

        for user in connected_users(token):
            template = {
                "_id": message_id,
                "users": {
                    f"{user}": False
                }
            }
            payload.update(template)

        temp.insert_one(payload)
        return 200, json.dumps({ "complete": True }), {'content-type': 'application/json'}

    else:
        return json.dumps({ "complete": False, "reason": "User not in session.", "code": "I02" }), 400, {'content-type': 'application/json'}

def is_sent_before(username, token, message_id):
    for data in temp.find({ "_id": message_id, "session": token }):
        if data["users"][username] == False:
            return False

        else:
            return True

async def _fetch_messages(username, token):
    if username in connected_users(token):
        for message in temp.find({}):
            if message["session"] == token and is_sent_before(username, token, message["_id"]):
                query = {
                    "_id": message["_id"],
                    "session": token,
                    "esm": message["esm"]
                }

                update_payload = {
                    "$set": {
                        "_id": message["_id"],
                        "users": {
                            f"{username}": True
                        }
                    }
                }
                temp.update_one(query, update_payload)

                payload = {
                    "author": message["author"],
                    "esm": message["esm"]
                }

        await asyncio.sleep(5)
        add_user_to_session(token, username)
        await asyncio.sleep(5)
        remove_user_from_session(token, username)

    else:
        add_user_to_session(token, username)

    return json.dumps(payload), 200, {'content-type': 'application/json'}

@web.route("/create-session", methods=["POST"])
def create_session():
    data = request.get_json(force=True)
    return _create_session(username=data["username"])

@web.route("/join-session", methods=["POST"])
def join_session():
    data = request.get_json(force=True)
    return _join_session(data["username"], data["token"])

@web.route("/send-message", methods=["POST"])
def send_message():
    data = request.get_json(force=True)
    return _send_message(username=data["username"], token=data["token"], esm=data["esm"])

@web.route("/fetch-messages", methods=["POST"])
def fetch_messages():
    data = request.get_json(force=True)
    loop = asyncio.get_event_loop()
    output = loop.run_until_complete(_fetch_messages(data["username"], data["token"]))
    loop.close()
    return output

@web.route("/decrypt", methods=["POST"])
def decypher_esm():
    data = request.get_json(force=True)
    return json.dumps({
        decypher(data["esm"])
    }), 200, {'content-type': 'application/json'}

@web.route("/validate-session", methods=["POST"])
def validate_session():
    data = request.get_json(force=True)
    return _validate_session(data["token"])

web.run(host="1.1.1.2", port=8080, debug=True)

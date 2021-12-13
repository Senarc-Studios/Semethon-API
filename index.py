import os
import json
import string
import random
import asyncio
from typing import Optional
from cool_utils import get_data
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket
from fastapi.reponses import JSONResponse
from local_cubacrypt import decypher, cypher
from dotenv import find_dotenv, load_dotenv
from pymongo import MongoClient

load_dotenv(find_dotenv())
mongoclient = MongoClient(get_data("config", "MONGO"))
mongoclient.drop_database('database')
mongodb = mongoclient['database']
users = mongodb['users']
session = mongodb['sessions']
temp = mongodb['temp']

web = FastAPI()

def validate_user(
	username,
	password,
	token = None
	):
	query = {
		"username": username,
		"password": password,
		"token": token
	}
	if users.count_documents(query) == 1:
		return True
	return False

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
	session.update_one(query, payload)

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
		"token": token,
		"username": username,
		"connected_users": [username]
	}

	session.insert_one(payload)
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

def is_sent_before(username, token, message_id):
	for data in temp.find({ "_id": message_id, "session": token }):
		if data["users"][username] == False:
			return False

		else:
			return True

def process_message(data: dict):
	token = data['token']
	username = data['username']
	esm = data['esm']

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
		return json.dumps({ "complete": True }), 200, {'content-type': 'application/json'}

	else:
		return json.dumps({ "complete": False, "reason": "User not in session.", "code": "I02" }), 400, {'content-type': 'application/json'}

def send_new_messages(username, token):
	if username in connected_users(token):
		for message in temp.find({}):
			if temp.count_documents({ "session": token }) == 0:
				return "No new messages", 404
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
			else:
				return "No new messages", 404 

	else:
		return add_user_to_session(token, username)

	return json.dumps(payload), 200, {'content-type': 'application/json'}

def _delete_session(token, username, password):
	if not validate_user(username, password, token):
		return json.dumps({'complete': False}), 401, {'content-type': 'application/json'}

	else:
		payload = {
			"token": token,
			"username": username
		}
		session.delete_one(payload)
		return json.dumps({'complete': True}), 200, {'content-type': 'application/json'}

class CreateSession(BaseModel):
	username: str
	password: str

class Session(BaseModel):
	username: str
	password: str
	token: Optional[str]

class Message(BaseModel):
	token: str
	password: str
	esm: str
	username: str

class User(BaseModel):
	token: str
	password: str
	username: str

class EncryptedMessage(BaseModel):
	esm: str

@web.create("/create-session")
async def create_session(data: CreateSession):
	return _create_session(username=data["username"])

@web.post("/join-session")
async def join_session(data: Session):
	return _join_session(data["username"], data["token"])

@web.websocket("/message-sync")
async def message_sync(websocket: WebSocket):
	await websocket.accept()
	while True:
		data = await websocket.receive_json()
		process_message(data)
		return send_new_messages(data['username'], data['token'])

@web.post("/decrypt")
async def decypher_esm(data: EncryptedMessage):
	return json.dumps({
		"message": decypher(data["esm"])
	}), 200, {'content-type': 'application/json'}

@web.post("/validate-session")
async def validate_session(data: Session):
	return _validate_session(data["token"])

@web.delete("delete-session")
async def delete_session(data: Session):
	return _delete_session(data['token', data['username']], data['password'])

web.run(host="127.0.0.1", port=8080, debug=True)

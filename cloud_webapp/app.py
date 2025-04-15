from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import secrets
import logging # Optional: Better logging

# Basic Logging Setup (Optional)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
# Use the environment variable you set, or a default for dev
# Ensure FLASK_SECRET_KEY is set in your environment for production!
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a-very-strong-dev-secret-key-change-me!')
# Configure CORS - Be more restrictive in production (e.g., specify your frontend domain)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Simple Storage for Agent Tokens (Replace with Database in Real App) ---
# Stores { user_id: agent_token }
# WARNING: This is temporary! Resets every time the Flask app restarts.
valid_agent_tokens = {}
logging.info("Initialized temporary agent token storage.")
# ---

# --- Authentication ---
# Route to generate/retrieve agent credentials
@app.route('/get_agent_token')
def get_agent_token():
    # If user already has a session/token, return existing one
    if 'user_id' in session and session['user_id'] in valid_agent_tokens:
        user_id = session['user_id']
        agent_token = valid_agent_tokens[user_id]
        logging.info(f"Returning existing token for user {user_id}")
        return jsonify({
            "status": "ok",
            "user_id": user_id,
            "agent_token": agent_token,
            "message": "Use these details in your local agent's config.yaml"
        })

    # Generate new ID and token for a new "session"
    user_id = 'user_' + secrets.token_hex(8)
    agent_token = 'agent_token_' + secrets.token_hex(16)
    session['user_id'] = user_id # Store user_id in browser session

    # Store the token server-side associated with the user_id
    valid_agent_tokens[user_id] = agent_token
    # You might not strictly need it in the session anymore if only agent uses it
    # session['agent_token'] = agent_token

    logging.info(f"Generated new token for user {user_id}. Token: {agent_token}")
    logging.info(f"Current valid tokens (DEBUG): {valid_agent_tokens}") # Avoid logging tokens in production

    return jsonify({
        "status": "ok",
        "user_id": user_id,
        "agent_token": agent_token,
        "message": "Copy these NEW details into your local agent's config.yaml and restart the agent."
    })

# Main page route
@app.route('/')
def index():
    # Check if user is "logged in" via session - meaning they visited /get_agent_token
    if 'user_id' not in session:
        logging.warning(f"Access attempt to / from {request.remote_addr} without session/user_id.")
        # Redirect or instruct user to visit /get_agent_token first
        return """Please <a href="/get_agent_token">click here</a> first
                  to get your agent credentials. Then refresh this page or return here.""" , 401
    logging.info(f"Serving index page to user {session['user_id']}")
    return render_template('index.html')

# --- Agent Connection Handling ---
connected_agents = {} # Store mapping: user_id -> agent_sid

@socketio.on('connect')
def handle_connect():
    logging.info(f'Client connected: SID={request.sid}, IP={request.remote_addr}')
    # Agent needs to authenticate immediately after connecting

@socketio.on('disconnect')
def handle_disconnect():
    logging.info(f'Client disconnected: SID={request.sid}')
    # Clean up agent mapping if an agent disconnects
    disconnected_user_id = None
    for user_id, sid in connected_agents.items():
        if sid == request.sid:
            disconnected_user_id = user_id
            break
    if disconnected_user_id:
        if disconnected_user_id in connected_agents: # Check existence before deleting
             del connected_agents[disconnected_user_id]
             logging.info(f"Removed agent SID mapping for user {disconnected_user_id}.")
        # Optional: Invalidate/remove token from valid_agent_tokens if it should expire on disconnect
        # Requires careful thought - agent might reconnect legitimately.
        # if disconnected_user_id in valid_agent_tokens:
        #     del valid_agent_tokens[disconnected_user_id]
        #     logging.info(f"Invalidated token for disconnected user {disconnected_user_id}.")


# --- Agent Authentication Handling ---
@socketio.on('authenticate_agent')
def handle_authenticate_agent(data):
    token_from_agent = data.get('token')
    user_id_from_agent = data.get('user_id')
    sid = request.sid
    logging.info(f"Agent auth attempt from SID {sid} for user '{user_id_from_agent}' with token '{token_from_agent[:5]}...'") # Log only prefix
    # logging.debug(f"Currently known valid tokens: {valid_agent_tokens}") # Avoid logging full tokens often

    # --- Check against server-side storage ---
    stored_token = valid_agent_tokens.get(user_id_from_agent)

    # Use secrets.compare_digest for timing-attack resistance
    if stored_token and isinstance(token_from_agent, str) and secrets.compare_digest(token_from_agent, stored_token):
        logging.info(f"Agent for user '{user_id_from_agent}' authenticated successfully. SID: {sid}")
        connected_agents[user_id_from_agent] = sid
        join_room(user_id_from_agent) # Put agent in a room specific to the user

        # Notify agent of success
        emit('authentication_result', {'status': 'success'}, room=sid)

        # Notify browser associated with this user_id (if any are connected via the main page)
        emit('agent_status', {'status': 'connected', 'message': f'Agent for {user_id_from_agent} connected & ready.'}, room=user_id_from_agent)

    else:
        logging.warning(f"Agent authentication failed for user '{user_id_from_agent}'. Token mismatch or user_id not found. SID: {sid}")
        emit('authentication_result', {'status': 'failed', 'message': 'Invalid credentials provided.'}, room=sid) # Notify agent of failure
        # Consider disconnecting agent after failed attempt:
        # socketio.disconnect(sid)

# --- Project Creation Logic ---
@socketio.on('create_project_request')
def handle_create_project(data):
    # Find the user_id associated with the requesting agent's SID
    authenticated_user_id = None
    requesting_sid = request.sid
    for uid, agent_sid in connected_agents.items():
        if agent_sid == requesting_sid:
            authenticated_user_id = uid
            break

    if not authenticated_user_id:
         emit('project_status', {'status': 'error', 'message': 'Agent is not authenticated.'}, room=requesting_sid) # Notify requesting agent SID
         logging.warning(f"Project creation denied. Requesting Agent SID {requesting_sid} is not authenticated.")
         return

    # Proceed with the authenticated user_id
    user_id = authenticated_user_id
    project_name = data.get('projectName')
    project_type = data.get('projectType')
    base_path = data.get('basePath') # Agent must validate this path strictly

    # Basic Input Validation (Example)
    if not all([project_name, project_type, base_path]):
        logging.error(f"Missing parameters in create_project_request from user {user_id}.")
        emit('project_status', {'status': 'error', 'message': 'Missing project parameters.'}, room=user_id) # Notify browser
        # Optionally notify agent too: emit('command_error', {'message': '...'}, room=requesting_sid)
        return

    logging.info(f"Received project creation request via agent for user '{user_id}' for '{project_name}' ({project_type}) at '{base_path}'")

    agent_sid = connected_agents[user_id] # We know this exists from the check above

    logging.info(f"Sending 'create_project' command to agent SID: {agent_sid}")

    command_data = {
        'command': 'create_project',
        'payload': {
            # Sanitize inputs further if necessary before sending
            'project_name': project_name,
            'project_type': project_type,
            'base_path': base_path
        }
    }
    # Emit directly to the specific agent's SID
    socketio.emit('execute_command', command_data, room=agent_sid)
    logging.info(f"Command sent to agent for user {user_id}.")
    # Notify browser(s) associated with this user
    emit('project_status', {'status': 'pending', 'message': f'Command sent to agent for project {project_name}.'}, room=user_id)


# --- Agent Response Handling ---
@socketio.on('agent_response')
def handle_agent_response(data):
    # Find user_id based on the agent's SID sending the response
    responding_user_id = None
    responding_sid = request.sid
    for uid, sid in connected_agents.items():
        if sid == responding_sid:
            responding_user_id = uid
            break

    if responding_user_id:
        logging.info(f"Received response from agent for user '{responding_user_id}' (SID {responding_sid}): {data}")
        # Forward response to the user's browser session(s) in the same room
        emit('project_status', data, room=responding_user_id)
    else:
        logging.warning(f"Received response from unknown/unauthenticated agent SID {responding_sid}: {data}")


if __name__ == '__main__':
    logging.info("Starting Flask server with SocketIO...")
    # For development, debug=True is fine. Ensure it's False in production.
    # Use Gunicorn + Eventlet/Gevent for production deployment instead of socketio.run
    # Example (conceptual): gunicorn --worker-class eventlet -w 1 app:app
    socketio.run(app, debug=True, host='0.0.0.0', port=5000) # Port 5000 used in example
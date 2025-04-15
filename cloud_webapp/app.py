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
    # This handles connections from BOTH browser and agent initially
    logging.info(f'Client connected: SID={request.sid}, IP={request.remote_addr}')

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
    sid = request.sid # This SID belongs to the agent connection
    logging.info(f"Agent auth attempt from SID {sid} for user '{user_id_from_agent}' with token '{token_from_agent[:5]}...'") # Log only prefix
    # logging.debug(f"Currently known valid tokens: {valid_agent_tokens}") # Avoid logging full tokens often

    # --- Check against server-side storage ---
    stored_token = valid_agent_tokens.get(user_id_from_agent)

    # Use secrets.compare_digest for timing-attack resistance
    if stored_token and isinstance(token_from_agent, str) and secrets.compare_digest(token_from_agent, stored_token):
        logging.info(f"Agent for user '{user_id_from_agent}' authenticated successfully. SID: {sid}")
        connected_agents[user_id_from_agent] = sid # Map user_id to the AGENT'S SID
        join_room(user_id_from_agent, sid=sid) # Put agent in its user-specific room

        # Notify agent of success
        emit('authentication_result', {'status': 'success'}, room=sid)

        # Notify browser(s) associated with this user_id (if any are connected via the main page)
        # Browsers should also join the user_id room
        emit('agent_status', {'status': 'connected', 'message': f'Agent for {user_id_from_agent} connected & ready.'}, room=user_id_from_agent) # Send to user room

    else:
        logging.warning(f"Agent authentication failed for user '{user_id_from_agent}'. Token mismatch or user_id not found. SID: {sid}")
        emit('authentication_result', {'status': 'failed', 'message': 'Invalid credentials provided.'}, room=sid) # Notify agent of failure
        # Consider disconnecting agent after failed attempt:
        # socketio.disconnect(sid)


# --- Project Creation Logic (CORRECTED) ---
@socketio.on('create_project_request')
def handle_create_project(data):
    # This event comes from the BROWSER (request.sid is browser's SID)
    browser_sid = request.sid

    # Get user_id FROM THE BROWSER'S SESSION
    if 'user_id' not in session:
        # This should ideally not happen if the '/' route requires login, but check anyway
        emit('project_status', {'status': 'error', 'message': 'User session not found. Please refresh or re-authenticate.'}, room=browser_sid)
        logging.warning(f"create_project_request received from Browser SID {browser_sid} but no user_id in session.")
        return

    user_id_from_session = session['user_id']
    logging.info(f"Project creation request received from browser session for user '{user_id_from_session}' (Browser SID: {browser_sid})")

    # Check if THIS user has an authenticated agent connected in our mapping
    if user_id_from_session not in connected_agents:
        emit('project_status', {'status': 'error', 'message': 'Your local agent is not connected or not authenticated.'}, room=browser_sid) # Notify specific browser
        logging.warning(f"No authenticated agent found for user '{user_id_from_session}' when project creation requested.")
        return

    # User has a session AND an authenticated agent. Get the AGENT'S SID from the mapping.
    agent_sid = connected_agents[user_id_from_session]

    # Proceed with the validated user_id and agent_sid
    project_name = data.get('projectName')
    project_type = data.get('projectType')
    base_path = data.get('basePath') # Agent must validate this path strictly

    # Basic Input Validation (Example)
    if not all([project_name, project_type, base_path]):
        logging.error(f"Missing parameters in create_project_request from user {user_id_from_session}.")
        # Notify the specific browser that made the request
        emit('project_status', {'status': 'error', 'message': 'Missing project parameters.'}, room=browser_sid)
        return

    logging.info(f"Request validated for user '{user_id_from_session}'. Sending command to Agent SID: {agent_sid}")

    command_data = {
        'command': 'create_project',
        'payload': {
            # Sanitize inputs further if necessary before sending
            'project_name': project_name,
            'project_type': project_type,
            'base_path': base_path
        }
    }
    # Emit command ONLY to the specific AGENT'S SID
    socketio.emit('execute_command', command_data, room=agent_sid)
    logging.info(f"Command sent to agent {agent_sid} for user {user_id_from_session}.")

    # Notify the specific browser that made the request
    emit('project_status', {'status': 'pending', 'message': f'Command sent to your local agent for project {project_name}.'}, room=browser_sid)


# --- Agent Response Handling ---
@socketio.on('agent_response')
def handle_agent_response(data):
    # This event comes from the AGENT (request.sid is agent's SID)
    agent_sid = request.sid
    # Find user_id based on the agent's SID sending the response
    responding_user_id = None
    for uid, connected_agent_sid in connected_agents.items():
        if connected_agent_sid == agent_sid:
            responding_user_id = uid
            break

    if responding_user_id:
        logging.info(f"Received response from agent for user '{responding_user_id}' (Agent SID {agent_sid}): {data}")
        # Forward response to potentially multiple browser sessions belonging to this user
        # Ensure browsers join the room user_id_from_session when they connect/load the page
        emit('project_status', data, room=responding_user_id) # Send to the user's room
    else:
        # This shouldn't happen if agent authenticated correctly
        logging.warning(f"Received response from unmapped/unauthenticated agent SID {agent_sid}: {data}")


# --- Optional: Handle Browser Joining User Room ---
# You might need logic for the browser client to explicitly join its user room
# once the main page loads, so it receives agent_response broadcasts.
# Example (add this handler):
@socketio.on('join_user_room')
def handle_join_user_room():
    browser_sid = request.sid
    if 'user_id' in session:
        user_id = session['user_id']
        join_room(user_id, sid=browser_sid)
        logging.info(f"Browser SID {browser_sid} joined room for user '{user_id}'.")
        # Optionally send current agent status upon joining
        if user_id in connected_agents:
             emit('agent_status', {'status': 'connected', 'message': f'Agent for {user_id} connected & ready.'}, room=browser_sid)
        else:
             emit('agent_status', {'status': 'disconnected', 'message': 'Agent not currently connected.'}, room=browser_sid)

    else:
        logging.warning(f"Browser SID {browser_sid} tried to join user room without session user_id.")

if __name__ == '__main__':
    logging.info("========================================")
    logging.info("Starting Flask server with SocketIO...")
    logging.info(f"Flask Secret Key Loaded: {'Yes' if app.config['SECRET_KEY'] != 'a-very-strong-dev-secret-key-change-me!' else 'No (Using Default - Insecure!)'}")
    logging.info("Mode: Development (Debug=True)") # Change debug=False for production
    logging.info("Ensure this is run behind a production WSGI server (like Gunicorn+eventlet) in production.")
    logging.info("========================================")
    # Use Gunicorn + Eventlet/Gevent for production deployment instead of socketio.run
    socketio.run(app, debug=True, host='0.0.0.0', port=5000) # Port 5000 used in example
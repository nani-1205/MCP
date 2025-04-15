from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import secrets

app = Flask(__name__)
# IMPORTANT: Use a strong, environment-variable-based secret key in production
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key!')
# TODO: Configure CORS appropriately for production
socketio = SocketIO(app, cors_allowed_origins="*") # Be more specific in production

# --- Authentication ---
# Replace with a proper user login system (e.g., Flask-Login, OAuth)
# This example uses a simple session concept
@app.route('/login', methods=['POST']) # Example placeholder
def login():
    # Validate user credentials here...
    session['user_id'] = 'user_' + secrets.token_hex(8) # Simple session ID
    # Generate or retrieve a unique token for this user's agent
    agent_token = 'agent_token_' + secrets.token_hex(16)
    session['agent_token'] = agent_token
    # Store this token securely, associate it with the user_id
    # Maybe store in a database: user_agents[session['user_id']] = agent_token
    print(f"User {session['user_id']} logged in. Agent token: {agent_token}")
    return jsonify({"status": "ok", "agent_token": agent_token}) # Return token for agent config

@app.route('/')
def index():
    # Check if user is logged in
    if 'user_id' not in session:
        return "Please login", 401 # Or redirect to a login page
    return render_template('index.html')

# --- Agent Connection Handling ---
connected_agents = {} # Store mapping: user_id -> agent_sid

@socketio.on('connect')
def handle_connect():
    print('Client connected:', request.sid)
    # Agent needs to authenticate immediately after connecting

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected:', request.sid)
    # Clean up agent mapping if an agent disconnects
    disconnected_user_id = None
    for user_id, sid in connected_agents.items():
        if sid == request.sid:
            disconnected_user_id = user_id
            break
    if disconnected_user_id:
        del connected_agents[disconnected_user_id]
        print(f"Agent for user {disconnected_user_id} disconnected.")

@socketio.on('authenticate_agent')
def handle_authenticate_agent(data):
    token = data.get('token')
    user_id = data.get('user_id') # User ID from browser session, passed to agent config
    print(f"Agent authentication attempt for user {user_id} with token {token}")

    # TODO: Securely verify the token against the stored token for the user_id
    # Example: stored_token = get_agent_token_for_user(user_id)
    # if token and stored_token and secrets.compare_digest(token, stored_token):
    # For this demo, we assume the token passed during login is manually configured in agent
    # In reality, need a DB lookup based on user_id provided by agent config
    expected_token = session.get('agent_token') # Simplistic: assumes browser and agent are linked by same session

    if user_id and token and user_id in session.get('user_id', '') and secrets.compare_digest(token, session.get('agent_token', '')): # Very basic check
        print(f"Agent for user {user_id} authenticated successfully. SID: {request.sid}")
        connected_agents[user_id] = request.sid
        join_room(user_id) # Put agent in a room specific to the user
        emit('agent_status', {'status': 'connected', 'message': 'Agent authenticated and ready.'}, room=user_id) # Notify browser
    else:
        print(f"Agent authentication failed for user {user_id}.")
        emit('agent_status', {'status': 'error', 'message': 'Agent authentication failed.'})
        # Consider disconnecting the agent socketio.disconnect(request.sid)

# --- Project Creation Logic ---
@socketio.on('create_project_request')
def handle_create_project(data):
    if 'user_id' not in session:
        emit('project_status', {'status': 'error', 'message': 'User not authenticated.'})
        return

    user_id = session['user_id']
    project_name = data.get('projectName')
    project_type = data.get('projectType') # e.g., 'python-basic', 'react-app'
    base_path = data.get('basePath') # e.g., '/Users/you/Development' - VERY SENSITIVE

    print(f"Received project creation request from user {user_id} for '{project_name}' ({project_type}) at '{base_path}'")

    if user_id not in connected_agents:
        print(f"No authenticated agent found for user {user_id}")
        emit('project_status', {'status': 'error', 'message': 'Local agent is not connected or authenticated.'}, room=user_id) # Send to browser
        return

    agent_sid = connected_agents[user_id]
    print(f"Sending command to agent SID: {agent_sid}")

    # SECURITY: Sanitize inputs before sending!
    # Ideally, only send predefined identifiers, not raw paths directly if possible.
    command_data = {
        'command': 'create_project',
        'payload': {
            'project_name': project_name,
            'project_type': project_type,
            'base_path': base_path # Agent needs to validate this path carefully!
        }
    }
    # Emit directly to the specific agent's SID
    socketio.emit('execute_command', command_data, room=agent_sid)
    print(f"Command sent to agent for user {user_id}.")
    emit('project_status', {'status': 'pending', 'message': f'Command sent to agent for project {project_name}.'}, room=user_id) # Notify browser


@socketio.on('agent_response')
def handle_agent_response(data):
    # Assume agent includes user_id or we find it via SID mapping
    # For simplicity, we just broadcast for now, but should target specific user room
    user_id = None
    for uid, sid in connected_agents.items():
        if sid == request.sid:
            user_id = uid
            break

    if user_id:
        print(f"Received response from agent for user {user_id}: {data}")
        # Forward response to the user's browser session
        emit('project_status', data, room=user_id) # Send status to browser
    else:
        print(f"Received response from unknown agent SID {request.sid}: {data}")


if __name__ == '__main__':
    print("Starting Flask server with SocketIO...")
    # Use environment variables for host/port in production
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
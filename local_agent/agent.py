import socketio
import os
import subprocess
import time
import yaml
import sys
from pathlib import Path
import logging

# Basic Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
CONFIG_FILE = 'config.yaml'
BASE_DEV_PATH = None # Will be loaded from config

def load_config():
    global BASE_DEV_PATH
    try:
        with open(CONFIG_FILE, 'r') as f:
            cfg = yaml.safe_load(f)
            if not cfg:
                 raise ValueError("Config file is empty or invalid.")

            cloud_url = cfg.get('cloud_url')
            agent_token = cfg.get('agent_token')
            user_id = cfg.get('user_id')
            base_dev_path_str = cfg.get('base_dev_path')

            if not all([cloud_url, agent_token, user_id, base_dev_path_str]):
                raise ValueError("'cloud_url', 'agent_token', 'user_id', and 'base_dev_path' must be set in config.yaml")

            # Validate and set BASE_DEV_PATH
            BASE_DEV_PATH = Path(base_dev_path_str).resolve()
            logging.info(f"Resolved base development path: {BASE_DEV_PATH}")

            # Ensure base path exists or can be created safely
            try:
                BASE_DEV_PATH.mkdir(parents=True, exist_ok=True)
                logging.info(f"Base development path accessible: {BASE_DEV_PATH}")
                # Security Check Example (adjust as needed)
                home_dir = Path.home()
                if not str(BASE_DEV_PATH).startswith(str(home_dir)):
                    logging.warning(f"Configured base path '{BASE_DEV_PATH}' is outside the home directory '{home_dir}'. Ensure this is intended and secure.")
            except PermissionError as e:
                 logging.error(f"Permission denied accessing/creating base path '{BASE_DEV_PATH}': {e}")
                 raise # Reraise permission errors
            except Exception as e:
                logging.error(f"Error accessing/creating base path '{BASE_DEV_PATH}': {e}")
                raise # Reraise other filesystem errors

            return cloud_url, agent_token, user_id

    except FileNotFoundError:
        logging.error(f"Configuration file '{CONFIG_FILE}' not found.")
        logging.error("Please create it with 'cloud_url', 'user_id', 'agent_token', and 'base_dev_path'.")
        sys.exit(1)
    except (yaml.YAMLError, ValueError) as e:
        logging.error(f"Error parsing or validating configuration file '{CONFIG_FILE}': {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error loading config: {e}")
        sys.exit(1)

# Load configuration at startup
CLOUD_URL, AGENT_TOKEN, USER_ID = load_config()

# --- Socket.IO Client ---
# Increased reconnection delay, added timeout
sio = socketio.Client(reconnection_delay=5, reconnection_delay_max=30, request_timeout=10)
agent_authenticated = False # Track authentication status

@sio.event
def connect():
    global agent_authenticated
    agent_authenticated = False # Reset on connect/reconnect
    logging.info(f"Connected to cloud server: {CLOUD_URL} (SID: {sio.sid}). Authenticating...")
    try:
        # Send credentials from config
        sio.emit('authenticate_agent', {'token': AGENT_TOKEN, 'user_id': USER_ID})
        logging.info("Authentication request sent.")
    except Exception as e:
        logging.error(f"Error sending authentication details: {e}")

@sio.event
def connect_error(data):
    logging.error(f"Connection failed: {data}")
    # No need to set authenticated = False here, it's false until success

@sio.event
def disconnect():
    global agent_authenticated
    agent_authenticated = False # Ensure state is false on disconnect
    logging.warning("Disconnected from cloud server.")

# --- Handle Authentication Result from Server ---
@sio.on('authentication_result')
def handle_auth_result(data):
    global agent_authenticated
    status = data.get('status')
    message = data.get('message', '')
    if status == 'success':
        agent_authenticated = True
        logging.info("Agent successfully authenticated by server.")
    else:
        agent_authenticated = False
        logging.error(f"Agent authentication failed by server: {message}")
        logging.error("Please check token/user_id in config.yaml and ensure server has matching credentials.")
        # Optional: Stop the agent after failed auth?
        # sio.disconnect()
        # sys.exit(1)

# --- Command Execution Logic ---
@sio.on('execute_command')
def handle_command(data):
    # Check if authenticated before executing any command
    if not agent_authenticated:
        logging.warning("Received command, but agent is not authenticated. Ignoring.")
        try:
             sio.emit('agent_response', {'status': 'error', 'message': 'Agent not authenticated.'})
        except Exception as e:
             logging.error(f"Failed to send 'not authenticated' response: {e}")
        return

    command = data.get('command')
    payload = data.get('payload')
    logging.info(f"Received command: '{command}'")
    logging.debug(f"Command payload: {payload}") # Debug level for potentially sensitive paths

    if command == 'create_project':
        try:
            project_name = payload.get('project_name')
            project_type = payload.get('project_type')
            # Path requested by the user via the web interface
            relative_base_path_str = payload.get('base_path', '')

            # ** Perform Validation and Security Checks **
            if not all([project_name, project_type, relative_base_path_str]):
                 raise ValueError("Missing required parameters (project_name, project_type, base_path) in payload.")

            # Validate project name (basic example: avoid path traversal)
            if '/' in project_name or '\\' in project_name or '..' in project_name:
                 raise ValueError(f"Invalid characters or path traversal attempt in project name: '{project_name}'")

            # Normalize and resolve the path *requested* in the payload
            # This resolves it relative to the current working directory initially
            requested_path_resolved = Path(relative_base_path_str).resolve()
            logging.debug(f"Resolved path from payload: {requested_path_resolved}")

            # ** CRITICAL SECURITY CHECK **:
            # Ensure the fully resolved requested path is *within* the allowed BASE_DEV_PATH from config.
            # This prevents the web UI directing the agent to write outside the configured safe zone.
            if BASE_DEV_PATH != requested_path_resolved and BASE_DEV_PATH not in requested_path_resolved.parents:
                 logging.error(f"Security Violation: Requested path '{requested_path_resolved}' is outside the allowed base directory '{BASE_DEV_PATH}'.")
                 raise PermissionError(f"Requested path is outside the allowed base directory.")

            # Construct the final project path using the validated base and project name
            project_path = requested_path_resolved / project_name
            logging.info(f"Validated path for project '{project_name}': {project_path}")

            # Execute the actual creation logic
            create_local_project(project_path, project_type)

            # Send success response
            success_msg = f"Project '{project_name}' created successfully at '{project_path}'"
            logging.info(success_msg)
            sio.emit('agent_response', {'status': 'success', 'message': success_msg})

        except (ValueError, PermissionError, FileExistsError) as e:
             err_msg = f"Project creation failed: {e}"
             logging.error(err_msg)
             sio.emit('agent_response', {'status': 'error', 'message': err_msg})
        except Exception as e:
            # Catch unexpected errors during project creation
            err_msg = f"An unexpected error occurred during project creation: {e}"
            logging.exception(err_msg) # Log full traceback for unexpected errors
            sio.emit('agent_response', {'status': 'error', 'message': err_msg})
    else:
        warn_msg = f"Received unknown command: '{command}'"
        logging.warning(warn_msg)
        sio.emit('agent_response', {'status': 'error', 'message': warn_msg})

# --- Helper Function to Create Projects ---
def create_local_project(project_path: Path, project_type: str):
    """Creates the project directory and runs setup based on type."""
    if project_path.exists():
        # Check if it's a file or directory - be specific
        if project_path.is_file():
             raise FileExistsError(f"A file with the name '{project_path.name}' already exists at this location.")
        elif project_path.is_dir() and any(project_path.iterdir()):
             # Optionally allow overwriting empty dirs, or always raise?
             raise FileExistsError(f"Directory '{project_path}' already exists and is not empty.")
        # If dir exists but is empty, we can proceed. mkdir(exist_ok=True) handles this.

    logging.info(f"Creating directory structure: {project_path}")
    try:
        project_path.mkdir(parents=True, exist_ok=True) # exist_ok handles race conditions and empty dirs
    except Exception as e:
        logging.error(f"Failed to create directory {project_path}: {e}")
        raise # Reraise to be caught by the main handler

    # --- Add Project Template Logic Here ---
    if project_type == 'python-basic':
        logging.info(f"Applying template 'python-basic' to {project_path}")
        (project_path / 'main.py').write_text("# Basic Python Project\n\nprint('Hello, World!')\n", encoding='utf-8')
        (project_path / 'requirements.txt').write_text("# Add Python dependencies here\n", encoding='utf-8')
        # Example: Initialize git (requires git installed and in PATH)
        # try:
        #     run_command(['git', 'init'], cwd=project_path)
        #     run_command(['git', 'add', '.'], cwd=project_path)
        #     run_command(['git', 'commit', '-m', 'Initial commit by MCP Agent'], cwd=project_path)
        # except Exception as git_err:
        #     logging.warning(f"Failed to initialize git repository: {git_err}")

    elif project_type == 'node-simple':
        logging.info(f"Applying template 'node-simple' to {project_path}")
        (project_path / 'index.js').write_text("// Basic Node.js Project\n\nconsole.log('Hello, World!');\n", encoding='utf-8')
        package_json_content = f'''{{
  "name": "{project_path.name}",
  "version": "1.0.0",
  "description": "",
  "main": "index.js",
  "scripts": {{
    "start": "node index.js",
    "test": "echo \\"Error: no test specified\\" && exit 1"
  }},
  "keywords": [],
  "author": "",
  "license": "ISC"
}}
'''
        (project_path / 'package.json').write_text(package_json_content, encoding='utf-8')
        # Example: Run npm install (requires Node.js/npm installed and in PATH)
        # try:
        #    run_command(['npm', 'install'], cwd=project_path)
        # except Exception as npm_err:
        #    logging.warning(f"Failed to run 'npm install': {npm_err}")

    # Add more elif blocks for other project types (e.g., copying from template folders)
    # elif project_type == 'react-basic':
    #   try:
    #      run_command(['npx', 'create-react-app', '.'], cwd=project_path) # Example, takes time
    #   except Exception as cra_err:
    #      logging.error(f"Failed to run create-react-app: {cra_err}")
    #      raise # Reraise the error to send failure response

    else:
        logging.warning(f"Unknown project type '{project_type}'. Only created directory.")
        # Decide if unknown type should be an error or just a warning
        # raise ValueError(f"Unknown project type specified: {project_type}")


# --- Helper Function to Run Commands ---
def run_command(command_list, cwd=None, timeout_seconds=60):
    """Helper to run shell commands safely with timeout."""
    if not cwd:
        cwd = Path.cwd()
    logging.info(f"Running command: '{' '.join(command_list)}' in directory '{cwd}'")
    try:
        # Use check=True to raise CalledProcessError on non-zero exit code
        # Use timeout to prevent hanging commands
        result = subprocess.run(
            command_list,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8', # Be explicit about encoding
            timeout=timeout_seconds
        )
        logging.info(f"Command finished successfully. Exit code: {result.returncode}")
        if result.stdout:
             logging.debug(f"Command STDOUT:\n{result.stdout.strip()}")
        if result.stderr:
             logging.warning(f"Command STDERR:\n{result.stderr.strip()}") # Log stderr even on success
        return True
    except FileNotFoundError:
        err_msg = f"Command not found: '{command_list[0]}'. Is it installed and in the system PATH?"
        logging.error(err_msg)
        raise RuntimeError(err_msg) # Raise a catchable runtime error
    except subprocess.CalledProcessError as e:
        err_msg = f"Command failed with exit code {e.returncode}: '{' '.join(command_list)}'"
        logging.error(err_msg)
        if e.stdout: logging.error(f"Failed Command STDOUT:\n{e.stdout.strip()}")
        if e.stderr: logging.error(f"Failed Command STDERR:\n{e.stderr.strip()}")
        raise RuntimeError(err_msg) from e
    except subprocess.TimeoutExpired as e:
        err_msg = f"Command timed out after {timeout_seconds}s: '{' '.join(command_list)}'"
        logging.error(err_msg)
        if e.stdout: logging.error(f"Timeout Command STDOUT:\n{e.stdout.decode(errors='ignore').strip()}")
        if e.stderr: logging.error(f"Timeout Command STDERR:\n{e.stderr.decode(errors='ignore').strip()}")
        raise TimeoutError(err_msg) from e
    except Exception as e:
        # Catch any other unexpected errors during command execution
        err_msg = f"An unexpected error occurred running command '{' '.join(command_list)}': {e}"
        logging.exception(err_msg) # Log full traceback
        raise RuntimeError(err_msg) from e


# --- Main Execution Loop ---
if __name__ == '__main__':
    logging.info("========================================")
    logging.info("Starting Local MCP Agent...")
    logging.info(f"Attempting to connect to Server: {CLOUD_URL}")
    logging.info(f"Using User ID: {USER_ID}")
    logging.info(f"Using Agent Token: {AGENT_TOKEN[:5]}...{AGENT_TOKEN[-5:]}") # Mask token in logs
    logging.info(f"Using Base Development Path: {BASE_DEV_PATH}")
    logging.info("========================================")

    while True:
        try:
            logging.info("Attempting connection...")
            # Set transports explicitly, prefer websocket
            sio.connect(CLOUD_URL, transports=['websocket'])
            logging.info("Socket connection established, client waiting for events...")
            sio.wait() # Blocks until disconnected
            # If sio.wait() returns, it means disconnection happened.
            logging.warning("sio.wait() exited, likely disconnected.")

        except socketio.exceptions.ConnectionError as e:
            logging.error(f"Connection Error: {e}. Check server URL and availability.")
        except Exception as e:
             # Catch broader exceptions during connect/wait phase
             logging.exception(f"An unexpected error occurred in the main loop: {e}")

        # Ensure cleanup and handle state before retry
        if sio.connected:
             logging.warning("Client was still marked as connected after wait() exited. Forcing disconnect.")
             sio.disconnect()
        agent_authenticated = False # Ensure auth state is reset

        retry_delay = 15 # Seconds
        logging.info(f"Will attempt reconnection in {retry_delay} seconds...")
        time.sleep(retry_delay)
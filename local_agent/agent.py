import socketio
import os
import subprocess
import time
import yaml
import sys
from pathlib import Path

# --- Configuration ---
CONFIG_FILE = 'config.yaml'

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file '{CONFIG_FILE}' not found.")
        print("Please create it with 'cloud_url', 'user_id', and 'agent_token'.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing configuration file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

config = load_config()
CLOUD_URL = config.get('cloud_url') # e.g., 'http://your-cloud-app-url.com' or 'http://localhost:5000' for local dev
AGENT_TOKEN = config.get('agent_token') # Get this after logging into the web UI
USER_ID = config.get('user_id') # Get this from the web UI session info
BASE_DEV_PATH = Path(config.get('base_dev_path', str(Path.home() / 'Development'))).resolve() # Default base path

if not CLOUD_URL or not AGENT_TOKEN or not USER_ID:
    print("Error: 'cloud_url', 'user_id', and 'agent_token' must be set in config.yaml")
    sys.exit(1)

# Make sure base dev path exists
try:
    BASE_DEV_PATH.mkdir(parents=True, exist_ok=True)
    print(f"Using base development path: {BASE_DEV_PATH}")
    # !! SECURITY !! Check if BASE_DEV_PATH is 'safe' (e.g., not root, not system dir)
    if not str(BASE_DEV_PATH).startswith(str(Path.home())):
         print(f"WARNING: Configured base path '{BASE_DEV_PATH}' is outside the home directory. Ensure this is intended and secure.")

except Exception as e:
    print(f"Error creating or accessing base development path '{BASE_DEV_PATH}': {e}")
    sys.exit(1)


# --- Socket.IO Client ---
sio = socketio.Client(reconnection_delay_max=10)

@sio.event
def connect():
    print("Connected to cloud server. Authenticating...")
    try:
        sio.emit('authenticate_agent', {'token': AGENT_TOKEN, 'user_id': USER_ID})
        print("Authentication request sent.")
    except Exception as e:
        print(f"Error sending authentication: {e}")

@sio.event
def connect_error(data):
    print(f"Connection failed: {data}")

@sio.event
def disconnect():
    print("Disconnected from cloud server.")

# --- Command Execution ---
@sio.on('execute_command')
def handle_command(data):
    command = data.get('command')
    payload = data.get('payload')
    print(f"\nReceived command: {command}")
    print(f"Payload: {payload}")

    if command == 'create_project':
        try:
            project_name = payload.get('project_name')
            project_type = payload.get('project_type')
            # IMPORTANT: Use the validated BASE_DEV_PATH from config, ignore/validate path from payload for security
            # For flexibility, let's allow a sub-path relative to BASE_DEV_PATH if sent, but validate heavily.
            relative_base_path_str = payload.get('base_path', '') # Path *from payload*

            # **SECURITY VALIDATION**
            if not project_name or not project_type or not relative_base_path_str:
                 raise ValueError("Missing required parameters in payload.")

            # Normalize and resolve the path from the payload
            requested_path = Path(relative_base_path_str).resolve()

            # **CRITICAL SECURITY CHECK**: Ensure requested path is WITHIN the configured BASE_DEV_PATH
            if BASE_DEV_PATH not in requested_path.parents and requested_path != BASE_DEV_PATH:
                 raise PermissionError(f"Requested path '{requested_path}' is outside the allowed base directory '{BASE_DEV_PATH}'.")

            # Proceed using the validated 'requested_path'
            project_path = requested_path / project_name
            print(f"Creating project '{project_name}' ({project_type}) at: {project_path}")

            # Execute the actual creation logic
            create_local_project(project_path, project_type)

            # Send success response
            sio.emit('agent_response', {'status': 'success', 'message': f'Project {project_name} created successfully at {project_path}'})
        except PermissionError as e:
             print(f"Security Error: {e}")
             sio.emit('agent_response', {'status': 'error', 'message': f'Security Error: {e}'})
        except ValueError as e:
             print(f"Input Error: {e}")
             sio.emit('agent_response', {'status': 'error', 'message': f'Input Error: {e}'})
        except Exception as e:
            print(f"Error creating project: {e}")
            sio.emit('agent_response', {'status': 'error', 'message': f'Failed to create project: {e}'})
    else:
        print(f"Unknown command: {command}")
        sio.emit('agent_response', {'status': 'error', 'message': f'Unknown command: {command}'})

def create_local_project(project_path: Path, project_type: str):
    """Creates the project directory and runs setup based on type."""
    if project_path.exists():
        raise FileExistsError(f"Directory already exists: {project_path}")

    print(f"Creating directory: {project_path}")
    project_path.mkdir(parents=True, exist_ok=True)

    # Example project types (Expand significantly)
    if project_type == 'python-basic':
        # Create a basic main.py and requirements.txt
        (project_path / 'main.py').write_text("# Basic Python Project\n\nprint('Hello, World!')\n")
        (project_path / 'requirements.txt').write_text("# Add Python dependencies here\n")
        print("Created basic Python files.")
        # Maybe initialize git?
        # run_command(['git', 'init'], cwd=project_path)
        # run_command(['git', 'add', '.'], cwd=project_path)
        # run_command(['git', 'commit', '-m', '"Initial commit"'], cwd=project_path)


    elif project_type == 'node-simple':
        # Create basic package.json and index.js
        (project_path / 'index.js').write_text("// Basic Node.js Project\n\nconsole.log('Hello, World!');\n")
        (project_path / 'package.json').write_text('{\n  "name": "' + project_path.name + '",\n  "version": "1.0.0",\n  "main": "index.js"\n}\n')
        print("Created basic Node.js files.")
        # Maybe run npm install? Requires Node/npm installed.
        # run_command(['npm', 'install'], cwd=project_path)

    # Add more project types: React, Vue, Go, Java, copy from template dirs, etc.
    # Example: Copying from a template directory
    # elif project_type == 'copy-template-X':
    #    template_dir = Path(__file__).parent / 'project_templates' / 'template-X'
    #    if template_dir.is_dir():
    #        shutil.copytree(template_dir, project_path, dirs_exist_ok=True)
    #        print(f"Copied template '{template_dir.name}' to {project_path}")
    #    else:
    #        raise FileNotFoundError(f"Template directory not found: {template_dir}")

    else:
        print(f"Warning: Unknown project type '{project_type}'. Only created directory.")


def run_command(command_list, cwd=None):
    """Helper to run shell commands safely."""
    print(f"Running command: {' '.join(command_list)} in {cwd or '.'}")
    try:
        # Use check=True to raise CalledProcessError on failure
        result = subprocess.run(command_list, cwd=cwd, check=True, capture_output=True, text=True)
        print("Command Output:", result.stdout)
        if result.stderr:
            print("Command Error Output:", result.stderr)
        return True
    except FileNotFoundError:
        print(f"Error: Command not found - {command_list[0]}. Is it installed and in PATH?")
        raise
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        print("Output:", e.stdout)
        print("Error Output:", e.stderr)
        raise
    except Exception as e:
        print(f"An unexpected error occurred running command: {e}")
        raise


# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Local Agent...")
    print(f"Attempting to connect to: {CLOUD_URL}")
    print(f"Using User ID: {USER_ID}")
    # Don't print the token here in real logs
    # print(f"Using Agent Token: {AGENT_TOKEN[:4]}...{AGENT_TOKEN[-4:]}")


    while True:
        try:
            sio.connect(CLOUD_URL, transports=['websocket'])
            print(f"Socket connected with SID: {sio.sid}")
            sio.wait() # Keep running until disconnected
        except socketio.exceptions.ConnectionError as e:
            print(f"Connection Error: {e}. Retrying in 10 seconds...")
        except Exception as e:
             print(f"An unexpected error occurred: {e}. Retrying in 10 seconds...")

        if sio.connected: # Should not happen if wait() exits cleanly, but check anyway
             sio.disconnect()
        time.sleep(10) # Wait before retrying connection